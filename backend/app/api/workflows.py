from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import RegisteredWorkflow
from app.schemas.jobs import (
    WorkflowInputOut,
    WorkflowOut,
    WorkflowPatch,
    WorkflowTestResult,
)
from app.services import generation

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _to_out(row: RegisteredWorkflow) -> WorkflowOut:
    try:
        spec = generation.get_spec(row.id)
    except Exception:  # noqa: BLE001 - spec removed from disk
        return WorkflowOut(
            id=row.id,
            name=row.name,
            description=row.description,
            category=row.category,
            version=row.version,
            enabled=row.enabled,
        )
    return WorkflowOut(
        id=row.id,
        name=row.name,
        description=row.description,
        category=row.category,
        version=row.version,
        enabled=row.enabled,
        inputs={
            name: WorkflowInputOut(
                type=m.type,
                required=m.required,
                default=m.default,
                auto=m.auto,
            )
            for name, m in spec.inputs.items()
        },
        outputs={
            name: [
                {"node_id": m.node_id, "output_type": m.output_type}
                for m in mappings
            ]
            for name, mappings in spec.outputs.items()
        },
    )


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(db: Session = Depends(get_db)):
    rows = db.query(RegisteredWorkflow).order_by(RegisteredWorkflow.id).all()
    return [_to_out(row) for row in rows]


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    row = db.get(RegisteredWorkflow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown workflow")
    return _to_out(row)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def patch_workflow(
    workflow_id: str, payload: WorkflowPatch, db: Session = Depends(get_db)
):
    row = db.get(RegisteredWorkflow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown workflow")
    if payload.enabled is not None:
        row.enabled = payload.enabled
        db.commit()
        db.refresh(row)
    return _to_out(row)


@router.post("/{workflow_id}/test", response_model=WorkflowTestResult)
async def test_workflow(workflow_id: str, db: Session = Depends(get_db)):
    try:
        return await generation.test_workflow(db, workflow_id)
    except generation.JobError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
