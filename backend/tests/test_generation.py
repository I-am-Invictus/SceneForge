import asyncio
import io
import uuid
from unittest.mock import AsyncMock

from PIL import Image
from sqlalchemy.orm import Session

from app.comfyui import comfyui_client
from app.database.db import SessionLocal
from app.main import app
from app.models import Asset, AssetFile, Job
from app.services import generation
from app.services.settings import get_effective_settings

from test_assets import data_root, make_image


def make_asset_file(db: Session, data: bytes) -> AssetFile:
    asset = Asset(
        kind="scene",
        name=f"Fixture {uuid.uuid4().hex[:6]}",
        storage_dir=f"assets/scene/test-{uuid.uuid4().hex[:8]}",
    )
    db.add(asset)
    db.commit()
    stored = f"{asset.storage_dir}/{uuid.uuid4().hex}.png"
    (data_root() / stored).parent.mkdir(parents=True, exist_ok=True)
    (data_root() / stored).write_bytes(data)
    asset_file = AssetFile(
        asset_id=asset.id,
        display_name="fixture",
        stored_path=stored,
        thumbnail_path=f"thumbnails/scene/{uuid.uuid4().hex}.jpg",
        width=64,
        height=48,
        size_bytes=len(data),
        mime="image/png",
        is_default=True,
        sort_order=0,
    )
    db.add(asset_file)
    db.commit()
    return asset_file


def test_submit_person_swap_end_to_end_mocked(monkeypatch):
    monkeypatch.setattr(
        comfyui_client,
        "upload_image",
        AsyncMock(side_effect=lambda url, name, data, ct: name),
    )
    submitted = {}

    async def fake_submit(url, workflow, client_id):
        submitted["workflow"] = workflow
        submitted["client_id"] = client_id
        return "prompt-abc"

    monkeypatch.setattr(comfyui_client, "submit_prompt", fake_submit)

    async def run():
        with SessionLocal() as db:
            scene = make_asset_file(db, make_image())
            character = make_asset_file(db, make_image((64, 48), (9, 9, 9)))
            job = await generation.submit_generation(
                db,
                "qwen_person_swap_v1",
                {
                    "scene_image": {"asset_file_id": scene.id},
                    "character_1": {"asset_file_id": character.id},
                    "composition_prompt": "the woman on the left",
                    "swap_mode": "true",
                },
            )
            db.refresh(job)
            # Submit only enqueues; dispatch performs the ComfyUI round-trip.
            assert job.status == "pending"
            assert job.comfyui_prompt_id is None
            job = await generation.dispatch_job(db, job)
            db.refresh(job)
            return job, scene.id, character.id

    job, scene_id, character_id = asyncio.run(run())
    assert job.status == "queued"
    assert job.comfyui_prompt_id == "prompt-abc"
    assert job.workflow_version == 1
    assert job.prompt == "the woman on the left"

    workflow = submitted["workflow"]
    assert workflow["2"]["inputs"]["image"] == submitted["workflow"]["2"]["inputs"]["image"]
    assert workflow["2"]["inputs"]["image"].startswith("sf_")
    assert workflow["3"]["inputs"]["image"].startswith("sf_")
    assert workflow["4"]["inputs"]["text"] == "the woman on the left"
    assert workflow["5"]["inputs"]["value"] is True
    assert workflow["53"]["inputs"]["value"] == 25
    seed = workflow["6"]["inputs"]["seed"]
    assert isinstance(seed, int)

    import json

    with SessionLocal() as db:
        row = db.get(Job, job.id)
        inputs = json.loads(row.inputs_json)
        assert inputs["scene_image"]["asset_file_id"] == scene_id
        assert inputs["character_1"]["asset_file_id"] == character_id


def test_submit_missing_required_input(monkeypatch):
    monkeypatch.setattr(
        comfyui_client, "upload_image", AsyncMock(return_value="sf_scene.png")
    )
    monkeypatch.setattr(
        comfyui_client, "submit_prompt", AsyncMock(return_value="p")
    )

    async def run():
        from app.schemas import JobError

        with SessionLocal() as db:
            scene = make_asset_file(db, make_image())
            try:
                await generation.submit_generation(
                    db,
                    "qwen_person_swap_v1",
                    {"scene_image": {"asset_file_id": scene.id}},
                )
                return None
            except JobError as exc:
                return exc

    exc = asyncio.run(run())
    assert exc is not None
    assert exc.status_code == 422
    assert "character_1" in str(exc)


def test_retrieve_outputs_saves_and_verifies(monkeypatch):
    monkeypatch.setattr(
        comfyui_client,
        "get_history",
        AsyncMock(
            return_value={
                "outputs": {
                    "18": {
                        "images": [
                            {
                                "filename": "swap_00001_.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
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
                comfyui_prompt_id="prompt-x",
                workflow_id="qwen_person_swap_v1",
                workflow_version=1,
                workflow_name="Qwen Person Swap",
                category="character_swap",
                status="completed",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            rows = await generation.retrieve_outputs(db, job)
            db.refresh(job)
            stored = rows[0].stored_path
            thumb = rows[0].thumbnail_path
        from app.models import JobOutput

        with SessionLocal() as db:
            row = db.get(JobOutput, rows[0].id)
            return stored, thumb, row

    stored, thumb, row = asyncio.run(run())
    assert (data_root() / stored).is_file()
    assert (data_root() / thumb).is_file()
    assert row.width == 640
    assert row.height == 480
    assert row.node_id == "18"
    assert row.source_type == "output"


def test_auto_source_size_for_image_edit(monkeypatch):
    monkeypatch.setattr(
        comfyui_client, "upload_image", AsyncMock(return_value="sf_src.png")
    )
    submitted = {}

    async def fake_submit(url, workflow, client_id):
        submitted["workflow"] = workflow
        return "prompt-edit"

    monkeypatch.setattr(comfyui_client, "submit_prompt", fake_submit)

    async def run():
        with SessionLocal() as db:
            source = make_asset_file(db, make_image((300, 200)))
            job = await generation.submit_generation(
                db,
                "qwen_image_edit_v1",
                {
                    "source_image": {"asset_file_id": source.id},
                    "prompt": "make it darker",
                },
            )
            await generation.dispatch_job(db, job)

    asyncio.run(run())
    workflow = submitted["workflow"]
    assert workflow["9"]["inputs"]["width"] == 300 // 8 * 8
    assert workflow["9"]["inputs"]["height"] == 200 // 8 * 8
    assert workflow["3"]["inputs"]["prompt"] == "make it darker"
    assert "30" in workflow
    assert workflow["30"]["class_type"] == "SaveImage"
