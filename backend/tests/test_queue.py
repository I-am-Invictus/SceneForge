import test_assets  # noqa: F401  (sets SCENEFORGE_DATA_DIR before app import)
from test_assets import make_image  # noqa: E402
from test_generation import make_asset_file  # noqa: E402

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.comfyui import ComfyUIError, comfyui_client  # noqa: E402
from app.database.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AssetFile, Job  # noqa: E402
from app.models.setting import utcnow  # noqa: E402
from app.services import generation  # noqa: E402
from app.services import dispatcher as dispatcher_module  # noqa: E402
from app.services.dispatcher import JobDispatcher  # noqa: E402
from app.services.monitor import JobMonitor  # noqa: E402

GEN = {"prompt": "a test", "width": 512, "height": 512}
job_dispatcher = dispatcher_module.job_dispatcher


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # Start from a clean jobs table so the dispatcher never sees jobs left by
    # another test, and default ComfyUI to "unreachable" so the dispatcher task
    # that any TestClient lifespan starts in this test is a no-op (no real
    # ComfyUI interaction). Tests needing a reachable ComfyUI override the
    # client methods themselves.
    with SessionLocal() as db:
        for job in db.query(Job).all():
            db.delete(job)
        db.commit()
    monkeypatch.setattr(
        comfyui_client,
        "get_queue",
        AsyncMock(side_effect=ComfyUIError("test: comfyui off")),
    )
    yield


def _submit(db, workflow_id="qwen_image_gen_v1", values=None):
    return asyncio.run(
        generation.submit_generation(db, workflow_id, values or dict(GEN))
    )


def _mock_comfyui(monkeypatch, *, reachable=True, submit="p", submit_mock=None):
    if reachable:
        monkeypatch.setattr(
            comfyui_client,
            "get_queue",
            AsyncMock(return_value={"running": [], "pending": []}),
        )
    else:
        monkeypatch.setattr(
            comfyui_client, "get_queue", AsyncMock(side_effect=ComfyUIError("down"))
        )
    monkeypatch.setattr(
        comfyui_client, "upload_image", AsyncMock(return_value="sf_up.png")
    )
    if submit_mock is not None:
        monkeypatch.setattr(comfyui_client, "submit_prompt", submit_mock)
    else:
        monkeypatch.setattr(
            comfyui_client, "submit_prompt", AsyncMock(return_value=submit)
        )


def test_rapid_sequential_submits_are_all_accepted():
    # Submitting several jobs back-to-back must not reject any (the old
    # behaviour 503'd a second submit that arrived while a first was still
    # uploading/prompting to ComfyUI). Each job is persisted as pending.
    with TestClient(app) as client:
        ids = []
        for _ in range(6):
            res = client.post("/api/generate/qwen_image_gen_v1", json={"inputs": GEN})
            assert res.status_code == 202, res.text
            ids.append(res.json()["client_id"])
        assert len(set(ids)) == 6
    with SessionLocal() as db:
        for cid in ids:
            job = db.query(Job).filter_by(client_id=cid).first()
            assert job is not None
            assert job.status == "pending"
            assert job.comfyui_prompt_id is None


def test_submit_all_three_job_types_enqueue():
    with SessionLocal() as db:
        scene = make_asset_file(db, make_image())
        character = make_asset_file(db, make_image((64, 48), (9, 9, 9)))
        gen = _submit(db)
        mod = asyncio.run(
            generation.submit_generation(
                db,
                "qwen_image_edit_v1",
                {"source_image": {"asset_file_id": scene.id}, "prompt": "darker"},
            )
        )
        swap = asyncio.run(
            generation.submit_generation(
                db,
                "qwen_person_swap_v1",
                {
                    "scene_image": {"asset_file_id": scene.id},
                    "character_1": {"asset_file_id": character.id},
                    "composition_prompt": "the person",
                },
            )
        )
        assert gen.status == mod.status == swap.status == "pending"
        assert gen.category == "general_generation"
        assert mod.category == "image_modification"
        assert swap.category == "character_swap"
        assert len({gen.client_id, mod.client_id, swap.client_id}) == 3


def test_dispatcher_drains_pending_fifo(monkeypatch):
    with SessionLocal() as db:
        first = _submit(db)
        second = _submit(db)
        third = _submit(db)
        now = utcnow()
        first.created_at = now - timedelta(seconds=3)
        second.created_at = now - timedelta(seconds=2)
        third.created_at = now - timedelta(seconds=1)
        db.commit()

    counter = {"n": 0}

    async def fake_submit(url, workflow, client_id):
        counter["n"] += 1
        return f"p{counter['n']}"

    _mock_comfyui(monkeypatch, submit_mock=fake_submit)
    asyncio.run(job_dispatcher._dispatch_cycle())

    with SessionLocal() as db:
        # FIFO: oldest submitted first, so prompt ids are assigned in order.
        assert db.get(Job, first.id).comfyui_prompt_id == "p1"
        assert db.get(Job, second.id).comfyui_prompt_id == "p2"
        assert db.get(Job, third.id).comfyui_prompt_id == "p3"
        assert db.get(Job, first.id).status == "queued"


def test_dispatcher_does_not_resubmit_already_dispatched(monkeypatch):
    with SessionLocal() as db:
        job = _submit(db)
        job_id = job.id

    calls = {"n": 0}

    async def fake_submit(url, workflow, client_id):
        calls["n"] += 1
        return "p-only"

    _mock_comfyui(monkeypatch, submit_mock=fake_submit)
    asyncio.run(job_dispatcher._dispatch_cycle())
    asyncio.run(job_dispatcher._dispatch_cycle())

    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "queued"
    assert calls["n"] == 1  # submitted exactly once


def test_dispatcher_holds_jobs_when_comfyui_unavailable(monkeypatch):
    with SessionLocal() as db:
        job = _submit(db)
        job_id = job.id

    submit = AsyncMock(return_value="p")
    _mock_comfyui(monkeypatch, reachable=False, submit_mock=submit)
    asyncio.run(job_dispatcher._dispatch_cycle())

    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "pending"  # not dispatched, not failed
        assert row.error is None
    submit.assert_not_awaited()


def test_restart_reconcile_fails_interrupted_dispatch():
    with SessionLocal() as db:
        job = _submit(db)
        job.status = "dispatching"  # simulate a crash mid-dispatch, no prompt_id
        db.commit()
        job_id = job.id
    JobDispatcher().reconcile_interrupted()
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "failed"
        assert row.comfyui_prompt_id is None
        assert "twice" in (row.error or "")


def test_restart_reconcile_ignores_pending():
    with SessionLocal() as db:
        job = _submit(db)
        job_id = job.id
    JobDispatcher().reconcile_interrupted()
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "pending"


def test_remove_pending_job_and_reject_started():
    with TestClient(app) as client:
        res = client.post("/api/generate/qwen_image_gen_v1", json={"inputs": GEN})
        cid = res.json()["client_id"]
        assert client.delete(f"/api/jobs/{cid}").status_code == 204
        with SessionLocal() as db:
            assert db.query(Job).filter_by(client_id=cid).first() is None

    # A dispatched (queued) job cannot be removed — it must be cancelled.
    with SessionLocal() as db:
        job = _submit(db)
        job.status = "queued"
        job.comfyui_prompt_id = "p1"
        db.commit()
        cid = job.client_id
        job_id = job.id
    with TestClient(app) as client:
        assert client.delete(f"/api/jobs/{cid}").status_code == 409
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "queued"


def test_cancel_pending_job_interrupts():
    with SessionLocal() as db:
        job = _submit(db)
        cid = job.client_id
        job_id = job.id
    assert asyncio.run(JobMonitor().cancel(cid)) is True
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "interrupted"
        assert row.comfyui_prompt_id is None


def test_terminal_job_does_not_revert():
    with SessionLocal() as db:
        job = _submit(db)
        job.status = "completed"
        db.commit()
        job_id = job.id
    asyncio.run(
        JobMonitor()._apply_event(
            db, db.get(Job, job_id), "execution_start", {}
        )
    )
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == "completed"


def test_dispatch_fails_job_when_input_deleted_before_dispatch(monkeypatch):
    with SessionLocal() as db:
        scene = make_asset_file(db, make_image())
        job = asyncio.run(
            generation.submit_generation(
                db,
                "qwen_image_edit_v1",
                {"source_image": {"asset_file_id": scene.id}, "prompt": "x"},
            )
        )
        db.delete(scene)
        db.commit()
        job_id = job.id

    _mock_comfyui(monkeypatch)
    asyncio.run(job_dispatcher._dispatch_cycle())

    with SessionLocal() as db:
        row = db.get(Job, job_id)
        assert row.status == "failed"
        assert row.error
