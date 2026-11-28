import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.comfyui.registry as registry
from app.comfyui import ComfyUIError, comfyui_client
from app.comfyui.adapter import WorkflowAdapter
from app.comfyui.registry import (
    WorkflowSpec,
    discover_specs,
    load_template,
)
from app.comfyui.validation import validate_workflow
from app.config import get_settings
from app.models import AssetFile, Job, JobOutput, RegisteredWorkflow
from app.schemas import JobError
from app.services import images as image_service
from app.services.settings import get_effective_settings, image_settings
from app.models.setting import utcnow


def get_specs() -> tuple[WorkflowSpec, ...]:
    # Deliberately uncached: the workflow set is tiny and reads from disk are
    # cheap, and a cache goes stale the moment a workflow/version/mapping is
    # added or changed (uploads, renames, activation). Always fresh.
    return tuple(discover_specs())


def clear_spec_cache() -> None:  # kept for backwards compatibility; no-op now
    return None


def get_spec(workflow_id: str, version: int | None = None) -> WorkflowSpec:
    # Always read from disk (never the cached active set) so freshly uploaded
    # workflows and newly switched active versions are visible immediately, and
    # a specific version can be requested. ``version=None`` means active.
    try:
        return registry.get_spec(workflow_id, version)
    except ValueError as exc:
        raise JobError(404, str(exc))


def sync_registry(db: Session) -> None:
    for spec in get_specs():
        row = db.get(RegisteredWorkflow, spec.id)
        if row is None:
            db.add(
                RegisteredWorkflow(
                    id=spec.id,
                    name=spec.name,
                    description=spec.description,
                    category=spec.category,
                    version=spec.version,
                    enabled=True,
                )
            )
        else:
            row.name = spec.name
            row.description = spec.description
            row.category = spec.category
            row.version = spec.version
    db.commit()


def _round_to_8(value: int, minimum: int = 16) -> int:
    rounded = max(minimum, int(value) // 8 * 8)
    return rounded if rounded % 8 == 0 else rounded + 8


async def _resolve_image_input(
    db: Session, value: dict
) -> tuple[bytes, str, int, int]:
    file_id = value.get("asset_file_id") if isinstance(value, dict) else None
    if file_id is None:
        raise JobError(422, "Image inputs require {\"asset_file_id\": <id>}")
    asset_file = db.get(AssetFile, int(file_id))
    if asset_file is None:
        raise JobError(422, f"Asset file {file_id} not found")
    root = get_settings().data_dirs["base"].resolve()
    path = (root / asset_file.stored_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise JobError(500, "Stored asset file is missing")
    data = await asyncio.to_thread(path.read_bytes)
    extension = Path(asset_file.stored_path).suffix.lower()
    width, height = await asyncio.to_thread(
        image_service.validate_image_bytes, data
    )
    return data, extension, width, height


def _validate_inputs(spec: WorkflowSpec, values: dict, db: Session) -> None:
    """Fast, ComfyUI-free validation so the user gets immediate feedback.

    Catches missing required inputs and image references that no longer exist.
    Type coercion / deeper structural errors are caught later at dispatch time
    (the job then fails with the specific error), which keeps the enqueue path
    fast enough to accept rapid, concurrent submissions.
    """
    for name, mapping in spec.inputs.items():
        if not mapping.required:
            continue
        if mapping.type == "image":
            value = values.get(name)
            file_id = value.get("asset_file_id") if isinstance(value, dict) else None
            if file_id is None:
                raise JobError(422, f"Missing required input: {name}")
            asset_file = db.get(AssetFile, int(file_id))
            if asset_file is None:
                raise JobError(422, f"Image input '{name}': asset file not found")
            root = get_settings().data_dirs["base"].resolve()
            path = (root / asset_file.stored_path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise JobError(409, f"Image input '{name}': stored file is missing")
        elif mapping.auto == "source":
            continue  # resolved from the source image at dispatch time
        else:
            if values.get(name) in (None, "") and mapping.default is None:
                raise JobError(422, f"Missing required input: {name}")


def _input_summary(spec: WorkflowSpec, values: dict) -> dict:
    summary: dict[str, object] = {}
    for name, value in values.items():
        if name not in spec.inputs:
            continue
        if spec.inputs[name].type == "image" and isinstance(value, dict):
            summary[name] = {"asset_file_id": value.get("asset_file_id")}
        else:
            summary[name] = value
    return summary


def _main_text(values: dict) -> str | None:
    for name in ("prompt", "instruction", "composition_prompt"):
        value = values.get(name)
        if value:
            return str(value)
    return None


async def submit_generation(
    db: Session,
    workflow_id: str,
    values: dict,
    ignore_enabled: bool = False,
    version: int | None = None,
) -> Job:
    """Validate and enqueue a generation job.

    This is deliberately fast and makes **no** ComfyUI calls: it persists the
    job as ``pending`` and returns immediately. The :class:`JobDispatcher`
    later prepares the ComfyUI graph (uploading inputs, applying values) and
    submits the prompt, so the user is never blocked on ComfyUI and jobs
    survive a restart while still in the queue.
    """
    spec = get_spec(workflow_id, version)
    sync_registry(db)
    row = db.get(RegisteredWorkflow, workflow_id)
    if not ignore_enabled and (row is None or not row.enabled):
        raise JobError(409, f"Workflow {workflow_id} is disabled")
    values = values or {}
    template = load_template(spec)
    adapter = WorkflowAdapter(spec, template)
    integrity = adapter.check_template_integrity()
    if integrity:
        raise JobError(500, "Workflow template error: " + "; ".join(integrity))

    _validate_inputs(spec, values, db)

    job = Job(
        client_id=comfyui_client.new_client_id(),
        workflow_id=workflow_id,
        workflow_version=spec.version,
        workflow_name=spec.name,
        category=spec.category,
        status="pending",
        prompt=_main_text(values),
        inputs_json=json.dumps(_input_summary(spec, values), default=str),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def dispatch_job(db: Session, job: Job) -> Job:
    """Prepare and submit a ``pending`` job to ComfyUI.

    Called by the dispatcher for the next queued job(s). Uploads the job's
    image inputs, applies the values to a fresh copy of the workflow template,
    and submits the prompt. The job moves ``pending -> dispatching -> queued``
    (with its ``comfyui_prompt_id``) on success, or ``-> failed`` on error.
    """
    try:
        spec = get_spec(job.workflow_id, job.workflow_version)
    except JobError as exc:
        job.status = "failed"
        job.error = f"Workflow no longer available: {exc.message}"
        job.finished_at = utcnow()
        db.commit()
        return job

    try:
        template = load_template(spec)
        adapter = WorkflowAdapter(spec, template)
        integrity = adapter.check_template_integrity()
        if integrity:
            raise JobError(500, "Workflow template error: " + "; ".join(integrity))
    except JobError as exc:
        job.status = "failed"
        job.error = exc.message
        job.finished_at = utcnow()
        db.commit()
        return job

    # Crash guard: mark dispatching (committed) before the async ComfyUI work so
    # a restart mid-dispatch can tell this job apart from a never-dispatched
    # "pending" one and never re-submit it (which would run it twice).
    job.status = "dispatching"
    job.progress = 0.0
    db.commit()

    base_url = get_effective_settings(db)["comfyui_http_url"]
    values = json.loads(job.inputs_json or "{}")

    try:
        image_filenames: dict[str, str] = {}
        source_dims: tuple[int, int] | None = None
        for name, mapping in spec.inputs.items():
            if mapping.type != "image" or name not in values:
                continue
            ref = values[name]
            file_id = ref.get("asset_file_id") if isinstance(ref, dict) else None
            data, extension, width, height = await _resolve_image_input(
                db, {"asset_file_id": file_id}
            )
            upload_name = f"sf_{uuid.uuid4().hex[:12]}{extension}"
            comfyui_name = await comfyui_client.upload_image(
                base_url, upload_name, data, f"image/{extension.lstrip('.')}"
            )
            image_filenames[name] = comfyui_name
            if source_dims is None:
                source_dims = (width, height)

        effective = dict(values)
        for name, mapping in spec.inputs.items():
            if mapping.auto == "source" and effective.get(name) in (None, ""):
                if source_dims is None:
                    raise JobError(422, f"Input {name} needs a source image")
                effective[name] = _round_to_8(
                    source_dims[0]
                    if name.lower().endswith("width")
                    else source_dims[1]
                )

        workflow, _applied = adapter.prepare(effective, image_filenames)
        prompt_id = await comfyui_client.submit_prompt(
            base_url, workflow, comfyui_client.monitor_client_id
        )
    except (ComfyUIError, JobError) as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = utcnow()
        db.commit()
        return job

    job.comfyui_prompt_id = prompt_id
    job.status = "queued"
    db.commit()
    return job


async def retrieve_outputs(db: Session, job: Job) -> list[JobOutput]:
    if not job.comfyui_prompt_id:
        return []
    urls = get_effective_settings(db)
    base_url = urls["comfyui_http_url"]
    history = await comfyui_client.get_history(base_url, job.comfyui_prompt_id)
    if history is None:
        return []
    node_outputs = history.get("outputs", {})
    if not node_outputs:
        return []
    # Only capture nodes the workflow spec declares as outputs (e.g. the
    # SaveImage node). Intermediate nodes such as PreviewImage would
    # otherwise be stored as duplicate results.
    try:
        # Use the exact workflow version the job was submitted with so an
        # uploaded revision cannot change which nodes are captured.
        spec = get_spec(job.workflow_id, job.workflow_version)
        mapped = {m.node_id for mappings in spec.outputs.values() for m in mappings}
        node_outputs = {
            node_id: out
            for node_id, out in node_outputs.items()
            if node_id in mapped
        }
    except JobError:
        pass  # spec no longer on disk: keep everything
    if not node_outputs:
        return []
    settings = get_settings()
    jpeg_quality, thumb_max_dim = image_settings(db)
    out_dir = settings.data_dirs["generated"] / job.client_id
    out_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir = settings.data_dirs["thumbnails"] / "generated"
    rows: list[JobOutput] = []
    for index, (node_id, node_output) in enumerate(sorted(node_outputs.items())):
        for img_index, img in enumerate(node_output.get("images", [])):
            filename = img.get("filename", "")
            if not filename:
                continue
            data = await comfyui_client.view_image(
                base_url, filename, img.get("subfolder", ""), img.get("type", "output")
            )
            digest = hashlib.sha1(data).hexdigest()[:12]
            safe_node = node_id.replace(":", "_")
            dest = out_dir / f"{safe_node}-{img_index + 1}-{digest}{Path(filename).suffix or '.png'}"
            await asyncio.to_thread(dest.write_bytes, data)
            written = await asyncio.to_thread(dest.read_bytes)
            if hashlib.sha1(written).hexdigest()[:12] != digest:
                raise JobError(500, f"Output copy verification failed for {filename}")
            width, height = await asyncio.to_thread(
                image_service.validate_image_bytes, data
            )
            thumb_path = thumb_dir / f"{job.client_id}-{safe_node}-{img_index + 1}.jpg"
            await asyncio.to_thread(
                image_service.make_thumbnail,
                dest,
                thumb_path,
                thumb_max_dim,
                jpeg_quality,
            )
            root = settings.data_dirs["base"]
            row = JobOutput(
                job_id=job.id,
                node_id=node_id,
                comfyui_filename=filename,
                subfolder=img.get("subfolder", ""),
                source_type=img.get("type", "output"),
                stored_path=str(dest.relative_to(root)),
                thumbnail_path=str(thumb_path.relative_to(root)),
                width=width,
                height=height,
                size_bytes=len(data),
                mime=image_service.MIME_BY_EXTENSION.get(
                    Path(filename).suffix.lower(), "image/png"
                ),
            )
            db.add(row)
            rows.append(row)
    db.commit()
    return rows


async def test_workflow(
    db: Session,
    workflow_id: str,
    version: int | None = None,
    test_inputs: dict | None = None,
) -> dict:
    """Validate a workflow and, if it is valid, submit an actual test
    generation.

    The returned ``job_client_id`` lets the client poll the job through the
    normal job endpoints to completion. A workflow is only considered
    "successfully tested" once that job completes with retrievable outputs —
    this endpoint reports pre-flight validity and submission, not the final
    inference outcome.
    """
    spec = get_spec(workflow_id, version)
    template = load_template(spec)
    base_url = get_effective_settings(db)["comfyui_http_url"]
    result: dict = {
        "id": workflow_id,
        "version": spec.version,
        "connectivity": None,
        "issues": [],
        "warnings": [],
        "ok": False,
        "submitted": False,
        "job_client_id": None,
    }
    status = await comfyui_client.get_status(base_url)
    if not status.connected:
        result["connectivity"] = {"connected": False, "detail": status.detail}
        result["issues"].append("ComfyUI is unreachable")
        return result
    result["connectivity"] = {"connected": True, "version": status.version}

    object_info: dict | None = None
    try:
        object_info = await comfyui_client.object_info(base_url, max_age=0)
    except ComfyUIError as exc:
        result["issues"].append(f"could not fetch ComfyUI node info: {exc}")
    if object_info is not None:
        errors, warnings = validate_workflow(spec, template, object_info)
        result["issues"].extend(errors)
        result["warnings"].extend(warnings)
    else:
        result["issues"].extend(
            WorkflowAdapter(spec, template).check_template_integrity()
        )

    if result["issues"]:
        return result  # not eligible to run
    result["ok"] = True  # statically valid; proceed to actual inference

    try:
        job = await submit_generation(
            db, workflow_id, test_inputs or {}, ignore_enabled=True, version=version
        )
    except JobError as exc:
        result["issues"].append(f"test submission failed: {exc.message}")
        return result
    result["submitted"] = True
    result["job_client_id"] = job.client_id
    return result
