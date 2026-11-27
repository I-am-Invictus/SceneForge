import re
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.comfyui.inspection import inspect_workflow
from app.comfyui.registry import (
    CATEGORIES,
    InputMapping,
    OutputMapping,
    load_template,
)
from app.comfyui.validation import validate_workflow
import app.comfyui.registry as registry
from app.database.db import get_db
from app.models.workflow import RegisteredWorkflow
from app.services import generation
from app.services.settings import get_effective_settings
from app.schemas.jobs import (
    WorkflowInputOut,
    WorkflowMappings,
    WorkflowOut,
    WorkflowPatch,
    WorkflowTestRequest,
    WorkflowTestResult,
    WorkflowUpload,
    WorkflowVersionOut,
    WorkflowVersionUpload,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _input_out(spec):
    return {
        name: WorkflowInputOut(
            type=inp.type, required=inp.required, default=inp.default, auto=inp.auto
        )
        for name, inp in spec.inputs.items()
    }


def _outputs_out(spec):
    return {
        name: [asdict(mapping) for mapping in mappings]
        for name, mappings in spec.outputs.items()
    }


def _to_out(row: RegisteredWorkflow) -> WorkflowOut:
    try:
        spec = generation.get_spec(row.id)
        return WorkflowOut(
            id=row.id,
            name=row.name,
            description=row.description,
            category=row.category,
            version=spec.active_version,
            active_version=spec.active_version,
            enabled=row.enabled,
            inputs=_input_out(spec),
            outputs=_outputs_out(spec),
        )
    except Exception:
        return WorkflowOut(
            id=row.id,
            name=row.name,
            description=row.description,
            category=row.category,
            version=row.version,
            active_version=row.version,
            enabled=row.enabled,
        )


def _get_row(db: Session, workflow_id: str) -> RegisteredWorkflow:
    row = db.get(RegisteredWorkflow, workflow_id)
    if row is None:
        raise HTTPException(404, f"Unknown workflow: {workflow_id}")
    return row


def _spec_or_404(workflow_id: str, version: int | None = None):
    try:
        return generation.get_spec(workflow_id, version)
    except Exception:
        raise HTTPException(404, f"Unknown workflow/version: {workflow_id} v{version}")


async def _object_info(base_url: str, max_age: int) -> dict | None:
    try:
        return await comfyui_client.object_info(base_url, max_age=max_age)
    except ComfyUIError:
        return None


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db)):
    generation.sync_registry(db)
    return [
        _to_out(row)
        for row in db.query(RegisteredWorkflow).order_by(RegisteredWorkflow.id)
    ]


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    generation.sync_registry(db)
    return _to_out(_get_row(db, workflow_id))


@router.post("", response_model=WorkflowOut, status_code=201)
def upload_workflow(payload: WorkflowUpload, db: Session = Depends(get_db)):
    if payload.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {sorted(CATEGORIES)}")
    if not _ID_RE.fullmatch(payload.id):
        raise HTTPException(422, "id must be lowercase letters, digits, underscores")
    if db.get(RegisteredWorkflow, payload.id) is not None:
        raise HTTPException(409, f"Workflow {payload.id} already exists; add a version instead")
    try:
        spec = registry.save_new_workflow(
            payload.id,
            payload.name,
            payload.category,
            payload.workflow,
            payload.inputs,
            payload.outputs,
            description=payload.description,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    row = db.get(RegisteredWorkflow, payload.id)
    if row is None:
        row = RegisteredWorkflow(
            id=payload.id,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            version=spec.active_version,
            enabled=False,
        )
        db.add(row)
    else:
        row.version = spec.active_version
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/{workflow_id}/versions", response_model=WorkflowVersionOut, status_code=201)
def upload_version(
    workflow_id: str, payload: WorkflowVersionUpload, db: Session = Depends(get_db)
):
    row = _get_row(db, workflow_id)
    try:
        saved = registry.save_new_version(
            workflow_id, payload.workflow, payload.inputs, payload.outputs
        )
        new_version = saved.version
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    row.version = new_version
    db.commit()
    db.refresh(row)
    spec = generation.get_spec(workflow_id, new_version)
    return WorkflowVersionOut(
        id=workflow_id,
        version=new_version,
        is_active=spec.active_version == new_version,
        inputs=_input_out(spec),
        outputs=_outputs_out(spec),
    )


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
def list_versions(workflow_id: str, db: Session = Depends(get_db)):
    _get_row(db, workflow_id)
    versions = []
    for info in registry.list_versions(workflow_id):
        number = info["version"]
        try:
            v_spec = registry.get_spec(workflow_id, number)
        except ValueError:
            continue
        versions.append(
            WorkflowVersionOut(
                id=workflow_id,
                version=number,
                is_active=info["is_active"],
                inputs=_input_out(v_spec),
                outputs=_outputs_out(v_spec),
            )
        )
    return versions


@router.get("/{workflow_id}/versions/{version}")
async def inspect_version(
    workflow_id: str, version: int, db: Session = Depends(get_db)
):
    _get_row(db, workflow_id)
    spec = _spec_or_404(workflow_id, version)
    base_url = get_effective_settings(db)["comfyui_http_url"]
    object_info = await _object_info(base_url, max_age=300)
    report = inspect_workflow(load_template(spec), object_info)
    return {
        "id": workflow_id,
        "version": version,
        "is_active": spec.active_version == version,
        "active_version": spec.active_version,
        "object_info_available": object_info is not None,
        "report": report,
        # Full stored mappings (node_id + input_name included) so the editor
        # can read and modify them, unlike the trimmed list/get shape.
        "inputs": {n: asdict(m) for n, m in spec.inputs.items()},
        "outputs": {n: [asdict(m) for m in v] for n, v in spec.outputs.items()},
    }


@router.get("/{workflow_id}/versions/{version}/template")
def get_template(workflow_id: str, version: int, db: Session = Depends(get_db)):
    _get_row(db, workflow_id)
    spec = _spec_or_404(workflow_id, version)
    return load_template(spec)


@router.put("/{workflow_id}/versions/{version}/mappings")
def save_mappings(
    workflow_id: str,
    version: int,
    payload: WorkflowMappings,
    db: Session = Depends(get_db),
):
    _get_row(db, workflow_id)
    _spec_or_404(workflow_id, version)
    # Validate the raw payloads (raises ValueError on a bad mapping) before
    # persisting, then hand the raw dicts to the registry which stores them.
    try:
        for name, data in (payload.inputs or {}).items():
            InputMapping.from_dict(name, data)
        for name, entries in (payload.outputs or {}).items():
            OutputMapping.from_config(name, entries)
        registry.save_mappings(workflow_id, version, payload.inputs, payload.outputs)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    spec = registry.get_spec(workflow_id, version)
    return {
        "id": workflow_id,
        "version": version,
        "inputs": {n: asdict(m) for n, m in spec.inputs.items()},
        "outputs": {n: [asdict(m) for m in v] for n, v in spec.outputs.items()},
    }


@router.post("/{workflow_id}/versions/{version}/validate")
async def validate_version(
    workflow_id: str, version: int, db: Session = Depends(get_db)
):
    _get_row(db, workflow_id)
    spec = _spec_or_404(workflow_id, version)
    base_url = get_effective_settings(db)["comfyui_http_url"]
    status = await comfyui_client.get_status(base_url)
    connectivity = {
        "connected": status.connected,
        "version": status.version,
        "detail": status.detail,
    }
    object_info = await _object_info(base_url, max_age=0)
    if object_info is None:
        return {
            "id": workflow_id,
            "version": version,
            "ok": False,
            "connectivity": connectivity,
            "errors": ["could not fetch ComfyUI node information"],
            "warnings": [],
        }
    errors, warnings = validate_workflow(spec, load_template(spec), object_info)
    return {
        "id": workflow_id,
        "version": version,
        "ok": not errors,
        "connectivity": connectivity,
        "errors": errors,
        "warnings": warnings,
    }


@router.post("/{workflow_id}/versions/{version}/activate")
def activate_version(
    workflow_id: str, version: int, db: Session = Depends(get_db)
):
    row = _get_row(db, workflow_id)
    _spec_or_404(workflow_id, version)
    registry.set_active_version(workflow_id, version)
    row.version = version
    db.commit()
    db.refresh(row)
    return {
        "id": workflow_id,
        "version": version,
        "active_version": version,
        "enabled": row.enabled,
    }


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def patch_workflow(
    workflow_id: str, payload: WorkflowPatch, db: Session = Depends(get_db)
):
    row = _get_row(db, workflow_id)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.name is not None:
        row.name = payload.name
    if payload.description is not None:
        row.description = payload.description
    try:
        registry.update_meta(
            workflow_id,
            name=row.name,
            description=row.description,
        )
    except (ValueError, OSError):
        pass  # metadata write failure is non-fatal for an enable/disable toggle
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/{workflow_id}/test", response_model=WorkflowTestResult)
async def test_workflow_endpoint(
    workflow_id: str,
    payload: WorkflowTestRequest | None = None,
    db: Session = Depends(get_db),
):
    _get_row(db, workflow_id)
    payload = payload or WorkflowTestRequest()
    return await generation.test_workflow(
        db, workflow_id, payload.version, payload.test_inputs
    )
