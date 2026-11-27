import io
import os
import tempfile

os.environ["SCENEFORGE_DATA_DIR"] = tempfile.mkdtemp(
    prefix="sceneforge-assets-test-"
)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def make_image(size=(640, 480), color=(120, 60, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def data_root():
    return get_settings().data_dirs["base"]


def upload(client, kind, files, name=None, folder_id=None):
    form = {}
    if name is not None:
        form["name"] = name
    if folder_id is not None:
        form["folder_id"] = str(folder_id)
    multipart = [
        ("files", (filename, data, "image/png")) for filename, data in files
    ]
    return client.post(
        f"/api/libraries/{kind}/assets", data=form, files=multipart
    )


def create_folder(client, kind, name, parent_id=None):
    payload = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return client.post(f"/api/libraries/{kind}/folders", json=payload)


def test_create_character_with_references():
    with TestClient(app) as client:
        response = upload(
            client,
            "character",
            files=[("front.png", make_image()), ("side.png", make_image((320, 640)))]
            ,
            name="Aria",
        )
    assert response.status_code == 201, response.text
    (asset,) = response.json()
    assert asset["kind"] == "character"
    assert asset["name"] == "Aria"
    assert asset["reference_count"] == 2
    assert asset["files"][0]["is_default"] is True
    assert asset["files"][1]["width"] == 320
    assert asset["files"][0]["width"] == 640
    assert asset["thumbnail_url"].startswith("/media/thumbnails/")
    thumb_dir = data_root() / "thumbnails" / "character"
    thumbs = list(thumb_dir.glob("*.jpg"))
    assert len(thumbs) == 2
    for thumb_path in thumbs:
        with Image.open(thumb_path) as img:
            assert img.format == "JPEG"
            assert max(img.size) <= 320


def test_create_scenes_batch():
    with TestClient(app) as client:
        response = upload(
            client,
            "scene",
            files=[("alley.png", make_image()), ("rooftop.png", make_image())],
        )
    assert response.status_code == 201
    assets = response.json()
    assert len(assets) == 2
    assert [a["name"] for a in assets] == ["alley", "rooftop"]
    assert all(a["reference_count"] == 1 for a in assets)


def test_scene_single_upload_uses_name():
    with TestClient(app) as client:
        response = upload(
            client, "scene", files=[("x.png", make_image())], name="Harbor"
        )
    (asset,) = response.json()
    assert asset["name"] == "Harbor"


def test_rename_favorite_search():
    with TestClient(app) as client:
        (asset,) = upload(
            client, "character", files=[("a.png", make_image())], name="Alpha Hero"
        ).json()
        upload(client, "character", files=[("b.png", make_image())], name="Beta Villain")

        renamed = client.patch(
            f"/api/libraries/character/assets/{asset['id']}",
            json={"name": "Alpha Prime"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Alpha Prime"

        starred = client.patch(
            f"/api/libraries/character/assets/{asset['id']}",
            json={"is_favorite": True},
        )
        assert starred.json()["is_favorite"] is True

        starred_list = client.get(
            "/api/libraries/character/assets", params={"favorite": "true"}
        )
        assert [a["id"] for a in starred_list.json()] == [asset["id"]]

        found = client.get(
            "/api/libraries/character/assets", params={"q": "prime"}
        )
        assert [a["name"] for a in found.json()] == ["Alpha Prime"]
        found_case = client.get(
            "/api/libraries/character/assets", params={"q": "PRIME"}
        )
        assert len(found_case.json()) == 1


def test_folders_nested_move_delete():
    with TestClient(app) as client:
        parent = create_folder(client, "character", "Heroes").json()
        child = create_folder(
            client, "character", "Mages", parent_id=parent["id"]
        ).json()
        assert child["parent_id"] == parent["id"]

        (asset,) = upload(
            client, "character", files=[("c.png", make_image())], name="Rook"
        ).json()

        moved = client.post(
            f"/api/libraries/character/assets/{asset['id']}/move",
            json={"folder_id": child["id"]},
        )
        assert moved.status_code == 200
        assert moved.json()["folder_id"] == child["id"]

        in_parent = client.get(
            "/api/libraries/character/assets", params={"folder_id": parent["id"]}
        )
        assert any(a["id"] == asset["id"] for a in in_parent.json())

        blocked = client.delete(f"/api/libraries/character/folders/{parent['id']}")
        assert blocked.status_code == 409

        client.post(
            f"/api/libraries/character/assets/{asset['id']}/move",
            json={"folder_id": None},
        )
        deleted = client.delete(f"/api/libraries/character/folders/{child['id']}")
        assert deleted.status_code == 204
        deleted_parent = client.delete(
            f"/api/libraries/character/folders/{parent['id']}"
        )
        assert deleted_parent.status_code == 204

        renamed = client.patch(
            f"/api/libraries/character/folders/{child['id']}", json={"name": "gone?"}
        )
        assert renamed.status_code == 404


def test_kind_isolation():
    with TestClient(app) as client:
        char_folder = create_folder(client, "character", "CharOnly").json()
        scene_folder = create_folder(client, "scene", "SceneOnly").json()

        (asset,) = upload(
            client, "scene", files=[("s.png", make_image())], name="Docks"
        ).json()
        cross_move = client.post(
            f"/api/libraries/scene/assets/{asset['id']}/move",
            json={"folder_id": char_folder["id"]},
        )
        assert cross_move.status_code == 404
        cross_folder = create_folder(client, "scene", "X", parent_id=char_folder["id"])
        assert cross_folder.status_code == 404


def test_add_delete_reference_and_default_promotion():
    with TestClient(app) as client:
        (asset,) = upload(
            client,
            "character",
            files=[("r1.png", make_image()), ("r2.png", make_image())],
            name="Duo",
        ).json()
        default_id = asset["files"][0]["id"]
        second_id = asset["files"][1]["id"]

        added = client.post(
            f"/api/libraries/character/assets/{asset['id']}/files",
            files=[("files", ("r3.png", make_image(), "image/png"))],
        )
        assert added.status_code == 201
        assert added.json()["reference_count"] == 3

        set_default = client.post(
            f"/api/libraries/character/assets/{asset['id']}/files/{second_id}/default"
        )
        assert set_default.status_code == 200
        defaults = [f for f in set_default.json()["files"] if f["is_default"]]
        assert [f["id"] for f in defaults] == [second_id]

        removed = client.delete(
            f"/api/libraries/character/assets/{asset['id']}/files/{second_id}"
        )
        assert removed.status_code == 200
        defaults = [f for f in removed.json()["files"] if f["is_default"]]
        assert [f["id"] for f in defaults] == [default_id]

        scene_add = client.post(
            f"/api/libraries/scene/assets/{asset['id']}/files",
            files=[("files", ("x.png", make_image(), "image/png"))],
        )
        assert scene_add.status_code == 404


def test_invalid_and_oversize_rejected():
    with TestClient(app) as client:
        bad = client.post(
            "/api/libraries/character/assets",
            data={"name": "Bad"},
            files=[("files", ("notimage.png", b"hello", "image/png"))],
        )
        assert bad.status_code == 422

        wrong_ext = client.post(
            "/api/libraries/character/assets",
            data={"name": "Bad2"},
            files=[("files", ("notes.txt", b"hello", "text/plain"))],
        )
        assert wrong_ext.status_code == 422


def test_delete_asset_removes_files():
    with TestClient(app) as client:
        (asset,) = upload(
            client, "scene", files=[("del.png", make_image())], name="Doomed"
        ).json()
        thumb_dir = data_root() / "thumbnails" / "scene"
        thumbs_before = set(thumb_dir.glob("*.jpg"))
        original_full = data_root() / "assets" / "scene"
        originals_before = set(original_full.rglob("*"))
        assert len(originals_before) >= 1

        deleted = client.delete(f"/api/libraries/scene/assets/{asset['id']}")
        assert deleted.status_code == 204
        assert len(set(thumb_dir.glob("*.jpg"))) == len(thumbs_before) - 1
        assert len(set(original_full.rglob("*"))) == len(originals_before) - 1
        assert client.get(f"/api/libraries/scene/assets/{asset['id']}").status_code == 404
        assert client.get(asset["files"][0]["thumbnail_url"]).status_code == 404


def test_restart_persistence():
    with TestClient(app) as client:
        (asset,) = upload(
            client,
            "character",
            files=[("persist.png", make_image())],
            name="Survivor",
        ).json()
        client.patch(
            f"/api/libraries/character/assets/{asset['id']}",
            json={"is_favorite": True},
        )
    with TestClient(app) as client:
        found = client.get(
            "/api/libraries/character/assets", params={"q": "survivor"}
        )
        assert [a["name"] for a in found.json()] == ["Survivor"]
        assert found.json()[0]["is_favorite"] is True
        detail = client.get(f"/api/libraries/character/assets/{asset['id']}")
        assert detail.status_code == 200
        thumb = client.get(detail.json()["files"][0]["thumbnail_url"])
        assert thumb.status_code == 200
        assert thumb.headers["content-type"] == "image/jpeg"
        original = client.get(detail.json()["files"][0]["original_url"])
        assert original.status_code == 200
        assert original.headers["content-type"] == "image/png"


# --- asset metadata editing -------------------------------------------------


def test_update_asset_metadata():
    with TestClient(app) as client:
        (asset,) = upload(
            client, "character", files=[("meta.png", make_image())], name="Meta"
        ).json()
        assert asset["description"] is None
        assert asset["tags"] == []
        (file_before,) = asset["files"]

        res = client.patch(
            f"/api/libraries/character/assets/{asset['id']}",
            json={
                "name": "Meta Renamed",
                "description": "A test character description",
                "tags": ["hero", "classic", "hero"],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["name"] == "Meta Renamed"
        assert body["description"] == "A test character description"
        assert body["tags"] == ["hero", "classic"]  # deduplicated, order kept

        # Individual fields: clear description and tags, keep the name.
        res = client.patch(
            f"/api/libraries/character/assets/{asset['id']}",
            json={"description": "", "tags": []},
        )
        assert res.status_code == 200
        assert res.json()["description"] is None
        assert res.json()["tags"] == []
        assert res.json()["name"] == "Meta Renamed"

        # The underlying image is untouched: same file id and bytes.
        detail = client.get(f"/api/libraries/character/assets/{asset['id']}")
        (file_after,) = detail.json()["files"]
        assert file_after["id"] == file_before["id"]
        assert (
            client.get(file_after["original_url"]).content
            == client.get(file_before["original_url"]).content
        )


def test_update_asset_metadata_validation():
    with TestClient(app) as client:
        (asset,) = upload(
            client, "scene", files=[("v.png", make_image())], name="V"
        ).json()
        # Name still required when provided.
        assert (
            client.patch(
                f"/api/libraries/scene/assets/{asset['id']}", json={"name": "  "}
            ).status_code
            == 422
        )
        # Too many tags.
        assert (
            client.patch(
                f"/api/libraries/scene/assets/{asset['id']}",
                json={"tags": [f"t{i}" for i in range(21)]},
            ).status_code
            == 422
        )
        # Tag too long.
        assert (
            client.patch(
                f"/api/libraries/scene/assets/{asset['id']}",
                json={"tags": ["x" * 51]},
            ).status_code
            == 422
        )
        # Description too long.
        assert (
            client.patch(
                f"/api/libraries/scene/assets/{asset['id']}",
                json={"description": "x" * 2001},
            ).status_code
            == 422
        )


# --- startup migration for pre-existing databases ---------------------------


def test_startup_migration_adds_metadata_columns(tmp_path):
    import sqlalchemy as sa
    from app.database.db import migrate_legacy_columns

    db_file = tmp_path / "legacy.db"
    legacy_engine = sa.create_engine(f"sqlite:///{db_file}")
    with legacy_engine.begin() as conn:
        # Pre-metadata schema: assets without description/tags.
        conn.execute(
            sa.text(
                "CREATE TABLE assets ("
                "id INTEGER PRIMARY KEY, kind VARCHAR(16) NOT NULL, "
                "name VARCHAR(200) NOT NULL, "
                "folder_id INTEGER, is_favorite BOOLEAN NOT NULL, "
                "storage_dir VARCHAR(64) NOT NULL, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO assets (kind, name, is_favorite, storage_dir) "
                "VALUES ('scene', 'Legacy', 0, 'assets/scene/legacy')"
            )
        )
    migrate_legacy_columns(legacy_engine)
    migrate_legacy_columns(legacy_engine)  # idempotent
    with legacy_engine.connect() as conn:
        cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(assets)"))}
        assert "description" in cols and "tags" in cols
        row = conn.execute(
            sa.text("SELECT name, description, tags FROM assets")
        ).fetchone()
    assert row == ("Legacy", None, None)
    legacy_engine.dispose()


# --- reference-safe asset deletion ------------------------------------------


def _make_job_referencing_asset_file(file_id):
    import uuid as _uuid
    from app.database.db import SessionLocal
    from app.models import Job

    with SessionLocal() as db:
        job = Job(
            client_id=f"job-{_uuid.uuid4().hex[:8]}",
            comfyui_prompt_id=f"p-{_uuid.uuid4().hex[:8]}",
            workflow_id="qwen_image_edit_v1",
            workflow_version=1,
            workflow_name="Qwen Image Edit",
            category="image_modification",
            status="completed",
            inputs_json=(
                '{"source_image": {"asset_file_id": %d, '
                '"uploaded_as": "sf_test.webp"}}' % file_id
            ),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.client_id


def test_delete_asset_keeps_file_referenced_by_job_inputs():
    from app.database.db import SessionLocal
    from app.models import AssetFile, Job

    with TestClient(app) as client:
        (asset,) = upload(
            client, "scene", files=[("ref.png", make_image())], name="Referenced"
        ).json()
        (file,) = asset["files"]
        job_client_id = _make_job_referencing_asset_file(file["id"])
        with SessionLocal() as db:
            af = db.get(AssetFile, file["id"])
            stored_rel = af.stored_path

        assert (
            client.delete(f"/api/libraries/scene/assets/{asset['id']}").status_code
            == 204
        )
        assert (
            client.get(f"/api/libraries/scene/assets/{asset['id']}").status_code
            == 404
        )
        # The AssetFile row is gone...
        with SessionLocal() as db:
            assert db.get(AssetFile, file["id"]) is None
            job = db.query(Job).filter(Job.client_id == job_client_id).first()
            assert job is not None
        # ...but the bytes survive for the job's source comparison.
        assert (data_root() / stored_rel).is_file()


def test_delete_asset_keeps_file_referenced_by_job_output():
    import uuid

    from app.database.db import SessionLocal
    from app.models import AssetFile, Job, JobOutput

    with TestClient(app) as client:
        (asset,) = upload(
            client,
            "character",
            files=[("moved.png", make_image())],
            name="Moved Result",
        ).json()
        (file,) = asset["files"]
        with SessionLocal() as db:
            af = db.get(AssetFile, file["id"])
            job = Job(
                client_id=f"job-{uuid.uuid4().hex[:8]}",
                workflow_id="qwen_image_edit_v1",
                workflow_version=1,
                workflow_name="Qwen Image Edit",
                category="image_modification",
                status="completed",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            # Simulate a generated output moved into this asset.
            db.add(
                JobOutput(
                    job_id=job.id,
                    node_id="30",
                    comfyui_filename="final.png",
                    stored_path=af.stored_path,
                    thumbnail_path=af.thumbnail_path,
                    width=file["width"],
                    height=file["height"],
                    size_bytes=file["size_bytes"],
                    mime=file["mime"],
                )
            )
            db.commit()
            out_id = db.query(JobOutput).first().id

        assert (
            client.delete(f"/api/libraries/character/assets/{asset['id']}").status_code
            == 204
        )
        assert (
            client.get(f"/api/libraries/character/assets/{asset['id']}").status_code
            == 404
        )
        # The job output still serves the shared bytes.
        assert client.get(f"/media/job-assets/{out_id}").status_code == 200


def test_delete_asset_missing_files_graceful():
    from app.database.db import SessionLocal
    from app.models import AssetFile

    with TestClient(app) as client:
        (asset,) = upload(
            client, "scene", files=[("gone.png", make_image())], name="Gone"
        ).json()
        (file,) = asset["files"]
        with SessionLocal() as db:
            af = db.get(AssetFile, file["id"])
            stored_rel, thumb_rel = af.stored_path, af.thumbnail_path
        (data_root() / stored_rel).unlink()
        (data_root() / thumb_rel).unlink()
        assert (
            client.delete(f"/api/libraries/scene/assets/{asset['id']}").status_code
            == 204
        )
        assert (
            client.get(f"/api/libraries/scene/assets/{asset['id']}").status_code
            == 404
        )


def test_delete_asset_refuses_outside_storage_path():
    from app.database.db import SessionLocal
    from app.models import AssetFile

    outside = data_root().parent / "outside_asset.png"
    outside.write_bytes(make_image())
    with TestClient(app) as client:
        (asset,) = upload(
            client, "scene", files=[("safe.png", make_image())], name="Outside"
        ).json()
        (file,) = asset["files"]
        with SessionLocal() as db:
            af = db.get(AssetFile, file["id"])
            af.stored_path = "../outside_asset.png"
            db.commit()
        assert (
            client.delete(f"/api/libraries/scene/assets/{asset['id']}").status_code
            == 204
        )
    assert outside.is_file(), "file outside managed storage must not be touched"
    outside.unlink(missing_ok=True)


def test_delete_asset_unknown():
    with TestClient(app) as client:
        assert client.delete("/api/libraries/scene/assets/999999").status_code == 404
        assert client.delete("/api/libraries/character/assets/999999").status_code == 404
