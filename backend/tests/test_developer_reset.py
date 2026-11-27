import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.api import developer as dev_module
from app.config import Settings
from app.main import app
from app.services import reset as reset_service

from test_assets import data_root, make_image, upload
from test_job_outputs import make_job_with_outputs

IMAGE_TABLES = (
    "assets",
    "asset_files",
    "jobs",
    "job_outputs",
    "galleries",
    "gallery_images",
)
ALL_TABLES = IMAGE_TABLES + ("folders", "settings", "workflows")


def _enable_dev(monkeypatch, enabled: bool):
    monkeypatch.setattr(dev_module, "_dev_mode_enabled", lambda: enabled)


def _counts() -> dict[str, int]:
    db = data_root() / "database" / "sceneforge.db"
    con = sqlite3.connect(str(db))
    try:
        cur = con.cursor()
        return {
            t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ALL_TABLES
        }
    finally:
        con.close()


def _first_output_id() -> int:
    con = sqlite3.connect(str(data_root() / "database" / "sceneforge.db"))
    try:
        return con.execute("SELECT MIN(id) FROM job_outputs").fetchone()[0]
    finally:
        con.close()


def _image_file_count() -> int:
    n = 0
    for sub in ("assets", "thumbnails", "generated", "temporary"):
        d = data_root() / sub
        if d.exists():
            n += sum(1 for _root, _dirs, names in os.walk(d) for _ in names)
    return n


def _seed_data(client: TestClient):
    upload(client, "scene", files=[("s.png", make_image())])
    upload(client, "character", files=[("c.png", make_image())], name="DevChar")
    client.post("/api/libraries/scene/folders", json={"name": "DevFolder"})
    client.put("/api/settings", json={"jpeg_quality": 91})
    make_job_with_outputs(1)
    gid = client.post("/api/galleries", json={"name": "DevGallery"}).json()["id"]
    client.put(
        f"/api/job-outputs/{_first_output_id()}/galleries",
        json={"gallery_ids": [gid]},
    )


def test_config_maps_dev_mode_env(monkeypatch):
    monkeypatch.setenv("SCENEFORGE_DEV_MODE", "1")
    assert Settings().sceneforge_dev_mode is True
    monkeypatch.delenv("SCENEFORGE_DEV_MODE")
    assert Settings().sceneforge_dev_mode is False


def test_status_reflects_dev_mode(monkeypatch):
    _enable_dev(monkeypatch, False)
    with TestClient(app) as client:
        assert client.get("/api/developer/status").json() == {"dev_mode": False}
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        assert client.get("/api/developer/status").json() == {"dev_mode": True}


def test_reset_blocked_when_dev_mode_off(monkeypatch):
    _enable_dev(monkeypatch, False)
    with TestClient(app) as client:
        _seed_data(client)
        before = _counts()
        res = client.post("/api/developer/reset", json={"confirm": "RESET"})
    assert res.status_code == 404
    assert _counts() == before, "reset must be a no-op when dev mode is off"


def test_reset_requires_typed_confirmation(monkeypatch):
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        _seed_data(client)
        before = _counts()
        wrong = client.post("/api/developer/reset", json={"confirm": "reset"})
        missing = client.post("/api/developer/reset", json={})
    assert wrong.status_code == 400
    assert missing.status_code == 422
    assert _counts() == before, "wrong/missing confirmation must not reset"


def test_reset_not_triggerable_via_get(monkeypatch):
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        _seed_data(client)
        before = _counts()
        res = client.get("/api/developer/reset")
    # A GET must never reset (the SPA catch-all returns 404 for api/ paths).
    assert res.status_code in (404, 405)
    assert _counts() == before, "GET must never perform a reset"


def test_reset_success_clears_and_preserves(monkeypatch):
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        _seed_data(client)
        before = _counts()
        assert before["assets"] >= 2 and before["workflows"] >= 1
        res = client.post("/api/developer/reset", json={"confirm": "RESET"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["backup_path"]

    after = _counts()
    for t in IMAGE_TABLES:
        assert after[t] == 0, f"{t} should be cleared"
    # Non-image data preserved.
    assert after["folders"] == before["folders"]
    assert after["settings"] == before["settings"]
    assert after["workflows"] == before["workflows"]
    assert _image_file_count() == 0


def test_repeated_reset_is_idempotent(monkeypatch):
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        _seed_data(client)
        first = client.post("/api/developer/reset", json={"confirm": "RESET"})
        assert first.status_code == 200 and first.json()["ok"] is True
        second = client.post("/api/developer/reset", json={"confirm": "RESET"})
    assert second.status_code == 200, second.text
    assert second.json()["ok"] is True
    after = _counts()
    for t in IMAGE_TABLES:
        assert after[t] == 0
    assert after["workflows"] >= 1, "workflow registrations must survive repeated resets"
    assert after["settings"] >= 1, "settings must survive repeated resets"


def test_reset_endpoint_reports_structured_failure(monkeypatch):
    def fake(base):
        return reset_service.ResetReport(
            ok=False,
            before={"assets": 1},
            after={"assets": 1},
            error="simulated storage failure",
        )

    monkeypatch.setattr(reset_service, "reset_image_data", fake)
    _enable_dev(monkeypatch, True)
    with TestClient(app) as client:
        res = client.post("/api/developer/reset", json={"confirm": "RESET"})
    assert res.status_code == 500
    assert res.json()["ok"] is False
    assert res.json()["error"] == "simulated storage failure"


def test_reset_service_reports_missing_db():
    report = reset_service.reset_image_data("/nonexistent/base/dir")
    assert report.ok is False
    assert "database not found" in report.error
