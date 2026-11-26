import asyncio
import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.comfyui.adapter import WorkflowAdapter
from app.comfyui.registry import (
    WorkflowSpec,
    discover_specs,
    load_template,
    validate_registration,
)
from app.config import get_settings
from app.models import AssetFile, Job, JobOutput, RegisteredWorkflow
from app.schemas import JobError
from app.services import images as image_service
from app.services.settings import get_effective_settings, image_settings
from app.models.setting import utcnow


@lru_cache
def get_specs() -> tuple[WorkflowSpec, ...]:
    return tuple(discover_specs())


def clear_spec_cache() -> None:
    get_specs.cache_clear()


def get_spec(workflow_id: str) -> WorkflowSpec:
    for spec in get_specs():
        if spec.id == workflow_id:
            return spec
    raise JobError(404, f"Unknown workflow: {workflow_id}")


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


async def submit_generation(
    db: Session, workflow_id: str, values: dict
) -> Job:
    spec = get_spec(workflow_id)
    sync_registry(db)
    row = db.get(RegisteredWorkflow, workflow_id)
    if row is None or not row.enabled:
        raise JobError(409, f"Workflow {workflow_id} is disabled")
    values = values or {}
    template = load_template(spec)
    adapter = WorkflowAdapter(spec, template)
    integrity = adapter.check_template_integrity()
    if integrity:
        raise JobError(500, "Workflow template error: " + "; ".join(integrity))

    urls = get_effective_settings(db)
    base_url = urls["comfyui_http_url"]

    image_filenames: dict[str, str] = {}
    source_dims: tuple[int, int] | None = None
    input_summary: dict[str, object] = {}
    for name, mapping in spec.inputs.items():
        if mapping.type != "image" or name not in values:
            continue
        data, extension, width, height = await _resolve_image_input(
            db, values[name]
        )
        upload_name = f"sf_{uuid.uuid4().hex[:12]}{extension}"
        comfyui_name = await comfyui_client.upload_image(
            base_url, upload_name, data, f"image/{extension.lstrip('.')}"
        )
        image_filenames[name] = comfyui_name
        if source_dims is None:
            source_dims = (width, height)
        input_summary[name] = {
            "asset_file_id": values[name].get("asset_file_id"),
            "uploaded_as": comfyui_name,
        }

    effective = dict(values)
    for name, mapping in spec.inputs.items():
        if mapping.auto == "source" and effective.get(name) in (None, ""):
            if source_dims is None:
                raise JobError(422, f"Input {name} needs a source image")
            effective[name] = _round_to_8(
                source_dims[0] if name.lower().endswith("width") else source_dims[1]
            )

    workflow, applied = adapter.prepare(effective, image_filenames)
    for name, value in values.items():
        if name not in spec.inputs:
            continue
        if name in image_filenames:
            continue
        input_summary[name] = value

    main_text = next(
        (
            str(applied[name])
            for name in (
                "prompt",
                "instruction",
                "composition_prompt",
            )
            if name in applied
        ),
        None,
    )

    client_id = comfyui_client.new_client_id()
    job = Job(
        client_id=client_id,
        workflow_id=workflow_id,
        workflow_version=spec.version,
        workflow_name=spec.name,
        category=spec.category,
        status="queued",
        prompt=main_text,
        inputs_json=json.dumps(input_summary, default=str),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        prompt_id = await comfyui_client.submit_prompt(base_url, workflow, client_id)
    except ComfyUIError as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = utcnow()
        db.commit()
        raise JobError(502, f"ComfyUI rejected the prompt: {exc}") from exc

    job.comfyui_prompt_id = prompt_id
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


async def test_workflow(db: Session, workflow_id: str) -> dict:
    spec = get_spec(workflow_id)
    template = load_template(spec)
    adapter = WorkflowAdapter(spec, template)
    base_url = get_effective_settings(db)["comfyui_http_url"]
    result: dict = {
        "id": workflow_id,
        "connectivity": None,
        "issues": [],
        "ok": False,
    }
    status = await comfyui_client.get_status(base_url)
    if not status.connected:
        result["connectivity"] = {"connected": False, "detail": status.detail}
        result["issues"].append("ComfyUI is unreachable")
        return result
    result["connectivity"] = {"connected": True, "version": status.version}
    result["issues"].extend(adapter.check_template_integrity())
    try:
        object_info = await comfyui_client.object_info(base_url, max_age=0)
    except ComfyUIError as exc:
        result["issues"].append(str(exc))
        return result
    result["issues"].extend(validate_registration(spec, template, object_info))
    result["ok"] = not result["issues"]
    return result
