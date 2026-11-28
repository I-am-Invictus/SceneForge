import asyncio
import uuid
from unittest.mock import AsyncMock

from app.comfyui import comfyui_client
from app.database.db import SessionLocal
from app.main import app
from app.models import Asset, AssetFile, Job, JobOutput
from app.schemas import JobError
from app.services import generation, job_outputs
from fastapi.testclient import TestClient

from test_assets import data_root, make_image, upload


def make_asset(client, kind: str, name: str = "Existing") -> tuple[int, dict]:
    """Create an existing asset with one reference via the normal upload path."""
    res = upload(client, kind, files=[("base.png", make_image())], name=name)
    assert res.status_code == 201, res.text
    (asset,) = res.json()
    return asset["id"], asset


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


# --- moving generated outputs into the asset libraries --------------------


def test_move_output_to_character_library():
    client = TestClient(app)
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        row_before = db.get(JobOutput, out_a)
        old_rel = row_before.stored_path
        job = job_outputs.move_output_to_library(db, client_id, out_a, "character")
    assert job.client_id == client_id
    # Bytes were relocated, not copied: old location gone, new location has data.
    assert not (data_root() / old_rel).exists()
    with SessionLocal() as db:
        new_rel = db.get(JobOutput, out_a).stored_path
    assert new_rel.startswith("assets/character/")
    assert (data_root() / new_rel).is_file()
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200
    # The image now appears in the character library with full metadata.
    with SessionLocal() as db:
        lib_file_id = (
            db.query(AssetFile).filter(AssetFile.stored_path == new_rel).first().id
        )
    res = client.get("/api/libraries/character/assets")
    assert res.status_code == 200
    (lib_asset,) = [
        a
        for a in res.json()
        if any(f["id"] == lib_file_id for f in a["files"])
    ]
    (lib_file,) = [f for f in lib_asset["files"] if f["id"] == lib_file_id]
    assert lib_asset["kind"] == "character"
    assert lib_file["width"] == 64
    assert lib_file["height"] == 48
    assert lib_file["size_bytes"] > 0
    assert lib_file["mime"] == "image/png"
    assert lib_file["is_default"] is True
    assert client.get(lib_file["original_url"]).status_code == 200
    assert client.get(lib_file["thumbnail_url"]).status_code == 200
    # Job results still work and still list the output.
    res = client.get(f"/api/jobs/{client_id}")
    assert res.status_code == 200
    assert [o["id"] for o in res.json()["outputs"]] == [out_a]
    assert res.json()["outputs"][0]["original_url"].startswith(
        f"/media/job-assets/{out_a}?v="
    )


def test_move_output_to_scene_library():
    client = TestClient(app)
    client_id, (out_a,) = make_job_with_outputs(1)
    before = len(client.get("/api/libraries/scene/assets").json())
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "scene")
        new_rel = db.get(JobOutput, out_a).stored_path
    assert new_rel.startswith("assets/scene/")
    after = client.get("/api/libraries/scene/assets").json()
    assert len(after) == before + 1
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200


def test_move_output_twice_replaces_previous_library_entry():
    client = TestClient(app)
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "character")
        first = db.get(JobOutput, out_a).stored_path
    char_assets_before = len(client.get("/api/libraries/character/assets").json())
    scene_assets_before = len(client.get("/api/libraries/scene/assets").json())
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "scene")
        second = db.get(JobOutput, out_a).stored_path
    assert first != second
    # No orphaned character entry: the library lost the asset created by the
    # first move, and only one physical file exists.
    char_assets_after = len(client.get("/api/libraries/character/assets").json())
    assert char_assets_after == char_assets_before - 1
    assert (data_root() / second).is_file()
    assert not (data_root() / first).is_file()
    scene_assets_after = client.get("/api/libraries/scene/assets").json()
    assert len(scene_assets_after) == scene_assets_before + 1
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200


def test_move_output_preserves_source_asset():
    client = TestClient(app)
    # A source asset uploaded through the existing upload path.
    res = upload(client, "scene", files=[("source.png", make_image())], name="Source")
    assert res.status_code == 201
    (source_asset,) = res.json()
    (source_file,) = source_asset["files"]
    source_url = source_file["original_url"]
    with SessionLocal() as db:
        src_row = db.get(AssetFile, source_file["id"])
        src_rel, src_thumb_rel = src_row.stored_path, src_row.thumbnail_path
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "scene")
    # The source asset is untouched: same record, same bytes, same URL.
    with SessionLocal() as db:
        src_row = db.get(AssetFile, source_file["id"])
        assert src_row.stored_path == src_rel
        assert src_row.thumbnail_path == src_thumb_rel
    assert (data_root() / src_rel).is_file()
    assert client.get(source_url).status_code == 200
    assert client.get("/api/libraries/scene/assets").status_code == 200


def test_move_output_never_overwrites_existing_files():
    client = TestClient(app)
    client_id, (out_a, out_b) = make_job_with_outputs(2)
    before = len(client.get("/api/libraries/character/assets").json())
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "character")
        job_outputs.move_output_to_library(db, client_id, out_b, "character")
        path_a = db.get(JobOutput, out_a).stored_path
        path_b = db.get(JobOutput, out_b).stored_path
    assert path_a != path_b
    assert (data_root() / path_a).is_file()
    assert (data_root() / path_b).is_file()
    res = client.get("/api/libraries/character/assets")
    assert len(res.json()) == before + 2
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200
    assert client.get(f"/media/job-assets/{out_b}").status_code == 200


def test_move_output_refuses_path_outside_storage():
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        row = db.get(JobOutput, out_a)
        row.stored_path = "../outside.png"
        db.commit()
        try:
            job_outputs.move_output_to_library(db, client_id, out_a, "scene")
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 400
        assert db.get(JobOutput, out_a) is not None


def test_move_output_unknown_job_or_output_or_folder():
    with SessionLocal() as db:
        for kind in ("character", "scene"):
            try:
                job_outputs.move_output_to_library(db, "no-such-job", 1, kind)
                assert False, "expected JobError"
            except JobError as exc:
                assert exc.status_code == 404
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        try:
            job_outputs.move_output_to_library(db, client_id, 999999, "scene")
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 404
        try:
            job_outputs.move_output_to_library(db, client_id, out_a, "bogus")
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 422
        assert db.get(JobOutput, out_a) is not None


def test_delete_moved_output_keeps_library_image():
    # Deleting an output that was moved into a library must not unlink the
    # shared file: the asset-library record still references it.
    client = TestClient(app)
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        job_outputs.move_output_to_library(db, client_id, out_a, "scene")
        new_rel = db.get(JobOutput, out_a).stored_path
    res = client.delete(f"/api/jobs/{client_id}/outputs/{out_a}")
    assert res.status_code == 200
    assert res.json()["outputs"] == []
    # The image file and its library entry survive.
    assert (data_root() / new_rel).is_file()
    with SessionLocal() as db:
        lib_file = db.query(AssetFile).filter(AssetFile.stored_path == new_rel).first()
        assert lib_file is not None
        assert client.get(f"/media/assets/{lib_file.id}").status_code == 200


def test_move_output_api_endpoint():
    client = TestClient(app)
    client_id, (out_a, out_b) = make_job_with_outputs(2)
    res = client.post(
        f"/api/jobs/{client_id}/outputs/{out_a}/move", json={"folder": "scene"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["client_id"] == client_id
    assert [o["id"] for o in body["outputs"]] == [out_a, out_b]
    # Invalid folder, unknown output, unknown job.
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/{out_b}/move", json={"folder": "nope"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/999999/move", json={"folder": "scene"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/jobs/nope/outputs/1/move", json={"folder": "scene"}
        ).status_code
        == 404
    )
    # The moved image is listed in the destination library.
    with SessionLocal() as db:
        new_rel = db.get(JobOutput, out_a).stored_path
        lib_file_id = (
            db.query(AssetFile).filter(AssetFile.stored_path == new_rel).first().id
        )
    scene_assets = client.get("/api/libraries/scene/assets").json()
    assert any(
        any(f["id"] == lib_file_id for f in a["files"]) for a in scene_assets
    )


# --- attaching a generated output to an EXISTING asset --------------------


def _add(client_id, out_id, kind, asset_id, make_default=False):
    with SessionLocal() as db:
        return job_outputs.add_output_to_asset(
            db, client_id, out_id, kind, asset_id, make_default
        )


def test_add_output_to_existing_character_asset():
    client = TestClient(app)
    asset_id, existing = make_asset(client, "character")
    (base_file,) = existing["files"]
    client_id, (out_a,) = make_job_with_outputs(1)
    with SessionLocal() as db:
        old_rel = db.get(JobOutput, out_a).stored_path

    job = _add(client_id, out_a, "character", asset_id)
    assert job.client_id == client_id

    # Bytes were relocated into the existing asset's storage dir, not copied.
    assert not (data_root() / old_rel).exists()
    with SessionLocal() as db:
        new_rel = db.get(JobOutput, out_a).stored_path
    assert new_rel.startswith("assets/character/")
    assert (data_root() / new_rel).is_file()

    # The asset now has two references: the original (unchanged, still default)
    # and the newly attached one (not default, appended).
    res = client.get(f"/api/libraries/character/assets/{asset_id}")
    assert res.status_code == 200
    files = res.json()["files"]
    assert len(files) == 2
    by_id = {f["id"]: f for f in files}
    assert by_id[base_file["id"]]["is_default"] is True
    assert by_id[base_file["id"]]["sort_order"] == 0
    (new_file,) = [f for f in files if f["id"] != base_file["id"]]
    assert new_file["is_default"] is False
    assert new_file["sort_order"] == 1
    assert new_file["width"] == 64 and new_file["height"] == 48
    assert client.get(new_file["original_url"]).status_code == 200
    # The job result still serves the (moved) image.
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200


def test_add_output_to_existing_scene_asset():
    client = TestClient(app)
    asset_id, existing = make_asset(client, "scene")
    before = len(client.get("/api/libraries/scene/assets").json())
    client_id, (out_a,) = make_job_with_outputs(1)
    _add(client_id, out_a, "scene", asset_id)
    # No new asset is created; the existing scene just gains a reference.
    assert len(client.get("/api/libraries/scene/assets").json()) == before
    res = client.get(f"/api/libraries/scene/assets/{asset_id}")
    assert res.status_code == 200
    assert res.json()["reference_count"] == len(existing["files"]) + 1


def test_add_multiple_references_to_same_asset():
    client = TestClient(app)
    asset_id, _ = make_asset(client, "character")
    client_id, (out_a, out_b) = make_job_with_outputs(2)
    _add(client_id, out_a, "character", asset_id)
    _add(client_id, out_b, "character", asset_id)
    res = client.get(f"/api/libraries/character/assets/{asset_id}")
    files = res.json()["files"]
    assert len(files) == 3  # original + two attached
    sort_orders = sorted(f["sort_order"] for f in files)
    assert sort_orders == [0, 1, 2]
    with SessionLocal() as db:
        path_a = db.get(JobOutput, out_a).stored_path
        path_b = db.get(JobOutput, out_b).stored_path
    assert path_a != path_b
    assert (data_root() / path_a).is_file()
    assert (data_root() / path_b).is_file()


def test_add_output_can_become_new_default():
    client = TestClient(app)
    asset_id, existing = make_asset(client, "character")
    (base_file,) = existing["files"]
    client_id, (out_a,) = make_job_with_outputs(1)
    _add(client_id, out_a, "character", asset_id, make_default=True)
    res = client.get(f"/api/libraries/character/assets/{asset_id}")
    files = res.json()["files"]
    by_id = {f["id"]: f for f in files}
    (new_file,) = [f for f in files if f["id"] != base_file["id"]]
    assert new_file["is_default"] is True
    assert by_id[base_file["id"]]["is_default"] is False  # demoted
    assert sum(1 for f in files if f["is_default"]) == 1  # exactly one default


def test_add_output_already_associated_is_rejected():
    client = TestClient(app)
    asset_id, _ = make_asset(client, "character")
    client_id, (out_a,) = make_job_with_outputs(1)
    _add(client_id, out_a, "character", asset_id)
    with SessionLocal() as db:
        try:
            job_outputs.add_output_to_asset(db, client_id, out_a, "character", asset_id)
            assert False, "expected JobError"
        except JobError as exc:
            assert exc.status_code == 409
    # Still exactly one reference of that image on the asset.
    res = client.get(f"/api/libraries/character/assets/{asset_id}")
    assert res.json()["reference_count"] == 2


def test_add_output_already_in_library_shares_file():
    client = TestClient(app)
    asset_a, _ = make_asset(client, "character")
    asset_b, _ = make_asset(client, "character")
    client_id, (out_a,) = make_job_with_outputs(1)
    _add(client_id, out_a, "character", asset_a)
    with SessionLocal() as db:
        shared_rel = db.get(JobOutput, out_a).stored_path
    # Attach the same (now-library) image to a second asset: the physical file
    # is reused, not copied or moved.
    _add(client_id, out_a, "character", asset_b)
    with SessionLocal() as db:
        refs = (
            db.query(AssetFile)
            .filter(AssetFile.stored_path == shared_rel)
            .all()
        )
    assert len(refs) == 2  # one reference per asset
    assert {r.asset_id for r in refs} == {asset_a, asset_b}
    assert (data_root() / shared_rel).is_file()
    # Exactly one physical file backs both references.
    res_a = client.get(f"/api/libraries/character/assets/{asset_a}")
    res_b = client.get(f"/api/libraries/character/assets/{asset_b}")
    url_a = [f["original_url"] for f in res_a.json()["files"]][-1]
    url_b = [f["original_url"] for f in res_b.json()["files"]][-1]
    assert client.get(url_a).status_code == 200
    assert client.get(url_b).status_code == 200
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200


def test_remove_reference_keeps_shared_image():
    client = TestClient(app)
    asset_id, _ = make_asset(client, "character")
    client_id, (out_a,) = make_job_with_outputs(1)
    _add(client_id, out_a, "character", asset_id)
    with SessionLocal() as db:
        shared_rel = db.get(JobOutput, out_a).stored_path
        (ref,) = [
            f
            for f in db.query(AssetFile).filter(AssetFile.asset_id == asset_id)
            if f.stored_path == shared_rel
        ]
        ref_id = ref.id
    # Removing the association must NOT delete the bytes the JobOutput still uses.
    res = client.delete(
        f"/api/libraries/character/assets/{asset_id}/files/{ref_id}"
    )
    assert res.status_code == 200
    assert (data_root() / shared_rel).is_file(), "shared image must survive"
    assert client.get(f"/media/job-assets/{out_a}").status_code == 200


def test_add_reference_api_endpoint():
    client = TestClient(app)
    char_id, _ = make_asset(client, "character")
    scene_id, _ = make_asset(client, "scene")
    client_id, (out_a, out_b) = make_job_with_outputs(2)

    res = client.post(
        f"/api/jobs/{client_id}/outputs/{out_a}/add-reference",
        json={"kind": "character", "asset_id": char_id, "make_default": False},
    )
    assert res.status_code == 200, res.text
    assert [o["id"] for o in res.json()["outputs"]] == [out_a, out_b]

    # Wrong kind for the asset, unknown asset, unknown output, unknown job.
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/{out_b}/add-reference",
            json={"kind": "scene", "asset_id": char_id},  # char_id is a character
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/{out_b}/add-reference",
            json={"kind": "scene", "asset_id": 999999},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/999999/add-reference",
            json={"kind": "scene", "asset_id": scene_id},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/jobs/nope/outputs/1/add-reference",
            json={"kind": "scene", "asset_id": scene_id},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/jobs/{client_id}/outputs/{out_b}/add-reference",
            json={"kind": "bogus", "asset_id": scene_id},
        ).status_code
        == 422
    )
    # Attach out_b to scene_id, then a second identical call is a duplicate.
    first = client.post(
        f"/api/jobs/{client_id}/outputs/{out_b}/add-reference",
        json={"kind": "scene", "asset_id": scene_id},
    )
    assert first.status_code == 200, first.text
    res2 = client.post(
        f"/api/jobs/{client_id}/outputs/{out_b}/add-reference",
        json={"kind": "scene", "asset_id": scene_id},
    )
    assert res2.status_code == 409
