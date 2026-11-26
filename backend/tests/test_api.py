import os
import tempfile

os.environ["SCENEFORGE_DATA_DIR"] = tempfile.mkdtemp(prefix="sceneforge-test-")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    with client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "comfyui_connected" in body


def test_settings_defaults():
    with client:
        response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["comfyui_http_url"] == "http://127.0.0.1:8188"
    assert body["comfyui_ws_url"] == "ws://127.0.0.1:8188/ws"


def test_settings_roundtrip():
    with client:
        put = client.put(
            "/api/settings", json={"comfyui_http_url": "http://127.0.0.1:9999"}
        )
        assert put.status_code == 200
        assert put.json()["comfyui_http_url"] == "http://127.0.0.1:9999"

        get = client.get("/api/settings")
        assert get.json()["comfyui_http_url"] == "http://127.0.0.1:9999"


def test_settings_rejects_invalid_url():
    with client:
        put = client.put("/api/settings", json={"comfyui_http_url": "not a url"})
        assert put.status_code == 422

        put = client.put("/api/settings", json={"comfyui_http_url": "ftp://x"})
        assert put.status_code == 422


def test_comfyui_status_shape():
    with client:
        response = client.get("/api/comfyui/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True or body["connected"] is False
    if not body["connected"]:
        assert body["detail"]
