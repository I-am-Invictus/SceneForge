import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.database.db import SessionLocal
from app.models import Job
from app.models.setting import utcnow
from app.services import generation
from app.services.monitor import JobMonitor


def make_job(db: Session, status: str, prompt_id: str) -> Job:
    job = Job(
        client_id=f"job-{uuid.uuid4().hex[:8]}",
        comfyui_prompt_id=prompt_id,
        workflow_id="qwen_image_gen_v1",
        workflow_version=1,
        workflow_name="Qwen Image Generation",
        category="general_generation",
        status=status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_resync(monkeypatch, queue: dict, history):
    monkeypatch.setattr(
        comfyui_client, "get_queue", AsyncMock(return_value=queue)
    )
    monkeypatch.setattr(
        comfyui_client,
        "get_history",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        generation, "retrieve_outputs", AsyncMock(return_value=[])
    )
    asyncio.run(JobMonitor()._resync())


def test_resync_completes_job_with_history_outputs(monkeypatch):
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job_id = job.id
    run_resync(
        monkeypatch,
        {"running": [], "pending": []},
        {"outputs": {"13": {}}, "status": {"status_str": "success"}},
    )
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "completed"


def test_resync_ignores_job_still_in_queue(monkeypatch):
    # Regression: queue items are [number, prompt_id, ...]; prompt id is at
    # index 1. A job whose prompt is still queued must not be failed.
    with SessionLocal() as db:
        job = make_job(db, "queued", "p1")
        job_id = job.id
    run_resync(
        monkeypatch,
        {"running": [[7, "p1", {}, {}, []]], "pending": []},
        None,
    )
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "queued"


def test_resync_marks_interrupted_from_history(monkeypatch):
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job_id = job.id
    run_resync(
        monkeypatch,
        {"running": [], "pending": []},
        {"outputs": {}, "status": {"status_str": "interrupted"}},
    )
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "interrupted"


def test_resync_reports_real_error_from_history(monkeypatch):
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job_id = job.id
    run_resync(
        monkeypatch,
        {"running": [], "pending": []},
        {
            "outputs": {},
            "status": {
                "status_str": "error",
                "messages": [
                    [
                        "execution_error",
                        {"exception_type": "ValueError", "exception_message": "bad node"},
                    ]
                ],
            },
        },
    )
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "failed"
        assert "ValueError" in row.error
        assert "bad node" in row.error


def test_submit_uses_stable_monitor_client_id(monkeypatch):
    monkeypatch.setattr(
        comfyui_client, "upload_image", AsyncMock(return_value="sf_x.png")
    )
    captured: dict = {}

    async def fake_submit(url, workflow, client_id):
        captured["client_id"] = client_id
        return "prompt-stable"

    monkeypatch.setattr(comfyui_client, "submit_prompt", fake_submit)

    async def run():
        with SessionLocal() as db:
            await generation.submit_generation(
                db,
                "qwen_image_gen_v1",
                {"prompt": "a lighthouse", "width": 832, "height": 1216},
            )

    asyncio.run(run())
    assert captured["client_id"] == comfyui_client.monitor_client_id


def test_get_queue_parses_comfyui_shape(monkeypatch):
    body = {
        "queue_running": [[1, "p-running", {}, {}, []]],
        "queue_pending": [[2, "p-pending", {}, {}, []]],
    }
    response = MagicMock()
    response.json.return_value = body
    monkeypatch.setattr(
        comfyui_client, "_request", AsyncMock(return_value=response)
    )

    async def run():
        return await comfyui_client.get_queue("http://x")

    result = asyncio.run(run())
    assert result["running"] == [[1, "p-running", {}, {}, []]]
    assert result["pending"] == [[2, "p-pending", {}, {}, []]]


def test_resync_skips_recent_job_without_history(monkeypatch):
    # A just-submitted prompt that isn't in queue/history yet must not be
    # marked lost (grace period).
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job_id = job.id
    run_resync(monkeypatch, {"running": [], "pending": []}, None)
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "running"


def test_resync_fails_old_job_without_history(monkeypatch):
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job.created_at = utcnow() - timedelta(seconds=120)
        db.commit()
        job_id = job.id
    run_resync(monkeypatch, {"running": [], "pending": []}, None)
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "failed"
        assert "Lost" in row.error


def test_resync_skips_cycle_when_queue_unreachable(monkeypatch):
    with SessionLocal() as db:
        job = make_job(db, "running", "p1")
        job.created_at = utcnow() - timedelta(seconds=120)
        db.commit()
        job_id = job.id
    monkeypatch.setattr(
        comfyui_client,
        "get_queue",
        AsyncMock(side_effect=ComfyUIError("unreachable")),
    )
    monkeypatch.setattr(
        generation, "retrieve_outputs", AsyncMock(return_value=[])
    )
    asyncio.run(JobMonitor()._resync())
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "running"
