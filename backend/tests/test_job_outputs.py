import asyncio
import uuid
from unittest.mock import AsyncMock

from app.comfyui import comfyui_client
from app.database.db import SessionLocal
from app.main import app
from app.models import Job, JobOutput
from app.schemas import JobError
from app.services import generation, job_outputs
from fastapi.testclient import TestClient

from test_assets import data_root, make_image


def make_job_with_outputs(n_outputs: int = 2, shared_path: bool = False):
    with SessionLocal() as db:
        job = Job(
            client_id=f"job-{uuid.uuid4().hex[:8]}",
            comfyui_prompt_id=f"prompt-{uuid.uuid4().hex[:8]}",
            workflow_id="qwen_image_gen_v1",
            workflow_version=1,
            workflow_name="Qwen Image Generation",
            category="general_generation",
            status="completed",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        stored_rel = None
        output_ids = []
        for i in range(n_outputs):
            if not (shared_path and i > 0):
                out_dir = data_root() / "generated" / job.client_id
                out_dir.mkdir(parents=True, exist_ok=True)
                stored = out_dir / f"13-{i + 1}-digest{i}.png"
                stored.write_bytes(make_image((64, 48), (i * 60, 30, 200)))
                stored_rel = str(stored.relative_to(data_root()))
            thumb_dir = data_root() / "thumbnails" / "generated"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_rel = f"thumbnails/generated/{job.client_id}-13-{i + 1}.jpg"
            (data_root() / thumb_rel).write_bytes(b"jpeg-bytes")
            row = JobOutput(
                job_id=job.id,
                node_id="13",
                comfyui_filename=f"file_{i}.png",
                stored_path=stored_rel,
                thumbnail_path=thumb_rel,
                width=64,
                height=48,
                size_bytes=10,
                mime="image/png",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            output_ids.append(row.id)
        return job.client_id, output_ids


def test_delete_output_removes_row_and_files():
    client_id, (out_a, out_b) = make_job_with_outputs(2)
    with SessionLocal() as db:
        row_a = db.get(JobOutput, out_a)
        row_b = db.get(JobOutput, out_b)
        stored_a, thumb_a = row_a.stored_path, row_a.thumbnail_path
        stored_b, thumb_b = row_b.stored_path, row_b.thumbnail_path
        job = job_outputs.delete_output(db, client_id, out_a)
        assert len(job.outputs) == 1
        assert db.get(JobOutput, out_a) is None
    assert not (data_root() / stored_a).exists()
    assert not (data_root() / thumb_a).exists()
    assert (data_root() / stored_b).is_file()
    assert (data_root() / thumb_b).is_file()


def test_delete_output_missing_files_graceful():
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        row = db.get(JobOutput, out_a)
        (data_root() / row.stored_path).unlink()
        (data_root() / row.thumbnail_path).unlink()
        job = job_outputs.delete_output(db, client_id, out_a)
        assert job.outputs == []
        assert db.get(JobOutput, out_a) is None


def test_delete_output_unknown_job_or_output():
    with SessionLocal() as db:
        try:
            job_outputs.delete_output(db, "no-such-job", 1)
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 404
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        other = Job(
            client_id=f"job-{uuid.uuid4().hex[:8]}",
            workflow_id="qwen_image_gen_v1",
            workflow_version=1,
            workflow_name="X",
            category="general_generation",
            status="completed",
        )
        db.add(other)
        db.commit()
        for bad_id in (out_a, 999999):
            try:
                job_outputs.delete_output(db, other.client_id, bad_id)
                assert False, "expected JobError"
            except JobError as exc:
                assert exc.status_code == 404
        assert db.get(JobOutput, out_a) is not None


def test_delete_output_refuses_path_outside_storage():
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        row = db.get(JobOutput, out_a)
        row.stored_path = "../outside.png"
        db.commit()
        try:
            job_outputs.delete_output(db, client_id, out_a)
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 400
        assert db.get(JobOutput, out_a) is not None


def test_delete_shared_path_keeps_file_while_referenced():
    client_id, (out_a, out_b) = make_job_with_outputs(2, shared_path=True)
    with SessionLocal() as db:
        shared = db.get(JobOutput, out_a).stored_path
        thumb_a = db.get(JobOutput, out_a).thumbnail_path
    with SessionLocal() as db:
        job_outputs.delete_output(db, client_id, out_a)
    assert (data_root() / shared).is_file(), "shared file must survive first delete"
    assert not (data_root() / thumb_a).exists()
    with SessionLocal() as db:
        job_outputs.delete_output(db, client_id, out_b)
    assert not (data_root() / shared).exists()


def test_delete_output_api_endpoint():
    client = TestClient(app)
    client_id, (out_a, out_b) = make_job_with_outputs(2)
    res = client.delete(f"/api/jobs/{client_id}/outputs/{out_a}")
    assert res.status_code == 200
    body = res.json()
    assert body["client_id"] == client_id
    assert [o["id"] for o in body["outputs"]] == [out_b]
    assert (
        client.delete(f"/api/jobs/{client_id}/outputs/{out_a}").status_code == 404
    )
    assert client.delete("/api/jobs/nope/outputs/1").status_code == 404


def test_retrieve_outputs_only_mapped_nodes(monkeypatch):
    # Node 6 is a PreviewImage duplicate of node 30's SaveImage in the
    # image edit workflow; only mapped node 30 may be stored.
    monkeypatch.setattr(
        comfyui_client,
        "get_history",
        AsyncMock(
            return_value={
                "outputs": {
                    "30": {
                        "images": [
                            {
                                "filename": "final.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    },
                    "6": {
                        "images": [
                            {
                                "filename": "temp.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    },
                }
            }
        ),
    )
    monkeypatch.setattr(
        comfyui_client, "view_image", AsyncMock(return_value=make_image())
    )

    async def run():
        with SessionLocal() as db:
            job = Job(
                client_id=f"job-{uuid.uuid4().hex[:8]}",
                comfyui_prompt_id="prompt-map",
                workflow_id="qwen_image_edit_v1",
                workflow_version=1,
                workflow_name="Qwen Image Edit",
                category="image_modification",
                status="completed",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            rows = await generation.retrieve_outputs(db, job)
            return [(r.node_id, r.comfyui_filename) for r in rows]

    rows = asyncio.run(run())
    assert rows == [("30", "final.png")]
