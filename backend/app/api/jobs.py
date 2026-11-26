import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import Job, JobOutput
from app.schemas import JobError
from app.schemas.jobs import GenerateRequest, JobOut, JobOutputOut
from app.services import generation
from app.services.monitor import job_monitor

router = APIRouter(tags=["jobs"])


def _serialize_output(row: JobOutput) -> JobOutputOut:
    return JobOutputOut(
        id=row.id,
        node_id=row.node_id,
        comfyui_filename=row.comfyui_filename,
        width=row.width,
        height=row.height,
        size_bytes=row.size_bytes,
        thumbnail_url=f"/media/job-thumbnails/{row.id}",
        original_url=f"/media/job-assets/{row.id}",
    )


def _serialize(job: Job) -> JobOut:
    try:
        inputs = json.loads(job.inputs_json or "{}")
    except json.JSONDecodeError:
        inputs = {}
    return JobOut(
        client_id=job.client_id,
        comfyui_prompt_id=job.comfyui_prompt_id,
        workflow_id=job.workflow_id,
        workflow_name=job.workflow_name,
        workflow_version=job.workflow_version,
        category=job.category,
        status=job.status,
        progress=job.progress,
        prompt=job.prompt,
        error=job.error,
        inputs=inputs,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        outputs=[_serialize_output(o) for o in job.outputs],
    )


@router.post("/api/generate/{workflow_id}", response_model=JobOut, status_code=202)
async def generate(
    workflow_id: str, payload: GenerateRequest, db: Session = Depends(get_db)
):
    try:
        job = await generation.submit_generation(db, workflow_id, payload.inputs)
        return _serialize(job)
    except JobError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/api/jobs", response_model=list[JobOut])
async def list_jobs(
    limit: int = 50,
    workflow_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if workflow_id:
        query = query.filter(Job.workflow_id == workflow_id)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.id.desc()).limit(min(limit, 200)).all()
    return [_serialize(job) for job in jobs]


@router.get("/api/jobs/{client_id}", response_model=JobOut)
async def get_job(client_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.client_id == client_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize(job)


@router.post("/api/jobs/{client_id}/cancel", response_model=JobOut)
async def cancel_job(client_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.client_id == client_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = await job_monitor.cancel(client_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job cannot be cancelled (status: {job.status})",
        )
    db.refresh(job)
    return _serialize(job)
