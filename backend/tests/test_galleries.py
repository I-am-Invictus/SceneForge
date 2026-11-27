import json

from fastapi.testclient import TestClient

from app.database.db import SessionLocal
from app.main import app
from app.models import GalleryImage, Job
from test_assets import make_image, upload
from test_job_outputs import make_job_with_outputs

client = TestClient(app)


def _outputs(n=1):
    return make_job_with_outputs(n_outputs=n)


def test_create_and_list_galleries():
    with client:
        r = client.post("/api/galleries", json={"name": "My Gallery"})
        assert r.status_code == 201
        assert r.json()["name"] == "My Gallery"
        assert r.json()["image_count"] == 0
        names = [g["name"] for g in client.get("/api/galleries").json()]
        assert "My Gallery" in names


def test_create_gallery_rejects_blank_name():
    with client:
        assert client.post("/api/galleries", json={"name": "   "}).status_code == 422


def test_get_gallery_by_id():
    with client:
        gid = client.post("/api/galleries", json={"name": "Lookup"}).json()["id"]
        r = client.get(f"/api/galleries/{gid}")
        assert r.status_code == 200
        assert r.json()["id"] == gid
        assert r.json()["name"] == "Lookup"
        assert client.get("/api/galleries/999999").status_code == 404


def test_rename_gallery_preserves_memberships():
    with client:
        gid = client.post("/api/galleries", json={"name": "Before"}).json()["id"]
        _, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [gid]})
        r = client.patch(f"/api/galleries/{gid}", json={"name": "After"})
        assert r.status_code == 200
        assert r.json()["name"] == "After"
        assert r.json()["image_count"] == 1


def test_delete_gallery_keeps_images():
    with client:
        gid = client.post("/api/galleries", json={"name": "Temp"}).json()["id"]
        client_id, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [gid]})
        assert client.delete(f"/api/galleries/{gid}").status_code == 204
        ids = [g["id"] for g in client.get("/api/galleries").json()]
        assert gid not in ids
        # The underlying output + job survive.
        job = client.get(f"/api/jobs/{client_id}").json()
        assert job["outputs"] and job["outputs"][0]["id"] == out[0]


def test_add_image_to_multiple_galleries_and_dedup():
    with client:
        g1 = client.post("/api/galleries", json={"name": "A"}).json()["id"]
        g2 = client.post("/api/galleries", json={"name": "B"}).json()["id"]
        _, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [g1, g2]})
        # Re-adding the same set must not duplicate the membership.
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [g1, g2]})
        got = sorted(
            g["id"] for g in client.get(f"/api/job-outputs/{out[0]}/galleries").json()
        )
        assert got == sorted([g1, g2])
        assert len(client.get(f"/api/galleries/{g1}/images").json()) == 1
        assert len(client.get(f"/api/galleries/{g2}/images").json()) == 1


def test_remove_from_one_gallery_keeps_other():
    with client:
        g1 = client.post("/api/galleries", json={"name": "A"}).json()["id"]
        g2 = client.post("/api/galleries", json={"name": "B"}).json()["id"]
        _, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [g1, g2]})
        r = client.delete(f"/api/galleries/{g1}/images/{out[0]}")
        assert r.status_code == 200
        assert r.json()["image_count"] == 0
        assert [g["id"] for g in client.get(f"/api/job-outputs/{out[0]}/galleries").json()] == [g2]


def test_sync_removes_unselected_galleries():
    with client:
        g1 = client.post("/api/galleries", json={"name": "A"}).json()["id"]
        g2 = client.post("/api/galleries", json={"name": "B"}).json()["id"]
        _, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [g1, g2]})
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [g2]})
        assert [g["id"] for g in client.get(f"/api/job-outputs/{out[0]}/galleries").json()] == [g2]


def test_membership_persists_in_db():
    gid = out = None
    with client:
        gid = client.post("/api/galleries", json={"name": "Persist"}).json()["id"]
        _, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [gid]})
    # A fresh session (stand-in for a service restart) still sees the row.
    with SessionLocal() as db:
        row = db.query(GalleryImage).filter(
            GalleryImage.gallery_id == gid,
            GalleryImage.job_output_id == out[0],
        ).first()
        assert row is not None


def test_deleting_output_cleans_gallery_memberships():
    gid = client_id = out = None
    with client:
        gid = client.post("/api/galleries", json={"name": "Del"}).json()["id"]
        client_id, out = _outputs(1)
        client.put(f"/api/job-outputs/{out[0]}/galleries", json={"gallery_ids": [gid]})
        assert client.delete(f"/api/jobs/{client_id}/outputs/{out[0]}").status_code == 200
    with SessionLocal() as db:
        assert db.query(GalleryImage).filter(
            GalleryImage.job_output_id == out[0]
        ).count() == 0


def test_gallery_image_resolves_original_for_edit_and_swap():
    with client:
        # A real scene asset to reference as the source image.
        res = upload(
            client,
            "scene",
            files=[("source.png", make_image((64, 48), (200, 30, 30)))],
            name="Source",
        )
        assert res.status_code == 201
        (scene_asset,) = res.json()
        (scene_file,) = scene_asset["files"]
        source_url = scene_file["original_url"]

        # A completed output whose job is an image_modification referencing it.
        client_id, (out_id,) = _outputs(1)
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.client_id == client_id).first()
            job.category = "image_modification"
            job.inputs_json = json.dumps(
                {"source_image": {"asset_file_id": scene_file["id"]}}
            )
            db.commit()

        gid = client.post("/api/galleries", json={"name": "Orig"}).json()["id"]
        client.put(f"/api/job-outputs/{out_id}/galleries", json={"gallery_ids": [gid]})
        image = client.get(f"/api/galleries/{gid}/images").json()[0]
        assert image["job_category"] == "image_modification"
        assert image["original"] is not None
        assert image["original"]["url"] == source_url
