import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock

os.environ.setdefault("SCENEFORGE_DATA_DIR", tempfile.mkdtemp(prefix="sceneforge-wfmgmt-"))

from fastapi.testclient import TestClient  # noqa: E402

from app.comfyui import comfyui_client  # noqa: E402
from app.comfyui import registry  # noqa: E402
from app.comfyui.inspection import inspect_workflow  # noqa: E402
from app.comfyui.validation import validate_workflow  # noqa: E402
from app.comfyui.registry import (  # noqa: E402
    InputMapping,
    OutputMapping,
    WorkflowSpec,
)
from app.database.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job  # noqa: E402
from app.schemas import ComfyuiStatus, JobError  # noqa: E402
from app.services import generation  # noqa: E402

init_db()

client = TestClient(app)


# --- Migration / persistent layout ------------------------------------------


def test_migration_creates_versioned_layout():
    registry.discover_specs()  # triggers the one-time seed + migration
    root = registry._persistent_root()
    for wf in ["qwen_image_gen_v1", "qwen_image_edit_v1", "qwen_person_swap_v1"]:
        found = next(
            (root / cat / wf for cat in registry.CATEGORIES if (root / cat / wf).is_dir()),
            None,
        )
        assert found is not None, f"{wf} not migrated"
        meta = json.loads((found / "config.json").read_text())
        assert meta["active_version"] == 1
        assert (found / "versions" / "1" / "config.json").is_file()
        assert (found / "versions" / "1" / "workflow.json").is_file()
        # legacy workflow.json must not remain at the top level
        assert not (found / "workflow.json").is_file()


def test_migration_is_idempotent():
    before = registry.list_versions("qwen_image_gen_v1")
    registry.migrate_workflows()
    registry.migrate_workflows()
    after = registry.list_versions("qwen_image_gen_v1")
    assert before == after
    assert len(after) == 1


def test_list_versions_endpoint():
    with client:
        response = client.get("/api/workflows/qwen_image_gen_v1/versions")
    assert response.status_code == 200
    body = response.json()
    assert any(v["version"] == 1 and v["is_active"] for v in body)


# --- Upload + versioning -----------------------------------------------------


def _tiny_workflow():
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }


def test_upload_new_workflow_then_enable():
    payload = {
        "id": "test_custom_wf",
        "name": "Custom",
        "category": "general_generation",
        "description": "unit test workflow",
        "workflow": _tiny_workflow(),
        "inputs": {
            "image": {
                "node_id": "1",
                "input_name": "image",
                "type": "image",
                "required": True,
            }
        },
        "outputs": {"result": [{"node_id": "2", "output_type": "images"}]},
    }
    with client:
        response = client.post("/api/workflows", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] == "test_custom_wf"
        assert body["enabled"] is False
        assert body["version"] == 1

        patch = client.patch("/api/workflows/test_custom_wf", json={"enabled": True})
        assert patch.status_code == 200
        assert patch.json()["enabled"] is True

        listed = {w["id"] for w in client.get("/api/workflows").json()}
        assert "test_custom_wf" in listed


def test_upload_rejects_duplicate_and_bad_category():
    with client:
        dup = client.post(
            "/api/workflows",
            json={
                "id": "test_custom_wf",
                "name": "x",
                "category": "general_generation",
                "workflow": _tiny_workflow(),
                "inputs": {},
                "outputs": {},
            },
        )
        assert dup.status_code == 409
        bad = client.post(
            "/api/workflows",
            json={
                "id": "test_bad_cat",
                "name": "x",
                "category": "not_a_category",
                "workflow": _tiny_workflow(),
                "inputs": {},
                "outputs": {},
            },
        )
        assert bad.status_code == 422


def test_upload_version_bumps_and_activates():
    payload = {
        "workflow": _tiny_workflow(),
        "inputs": {
            "image": {
                "node_id": "1",
                "input_name": "image",
                "type": "image",
                "required": True,
            }
        },
        "outputs": {"result": [{"node_id": "2", "output_type": "images"}]},
    }
    with client:
        response = client.post("/api/workflows/test_custom_wf/versions", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["version"] == 2
        assert response.json()["is_active"] is True

        versions = client.get("/api/workflows/test_custom_wf/versions").json()
        numbers = {v["version"] for v in versions}
        assert {1, 2} <= numbers
        active = [v for v in versions if v["is_active"]]
        assert [v["version"] for v in active] == [2]

        # the active version is what the workflow reports
        detail = client.get("/api/workflows/test_custom_wf").json()
        assert detail["version"] == 2
        assert detail["active_version"] == 2


def test_activate_version_switches_active():
    with client:
        r = client.post("/api/workflows/test_custom_wf/versions/1/activate")
        assert r.status_code == 200
        assert r.json()["active_version"] == 1
        detail = client.get("/api/workflows/test_custom_wf").json()
        assert detail["active_version"] == 1


def test_activate_missing_version_404():
    with client:
        r = client.post("/api/workflows/test_custom_wf/versions/99/activate")
    assert r.status_code == 404


# --- Mapping persistence -----------------------------------------------------


def test_save_mappings_persists():
    payload = {
        "inputs": {
            "prompt": {
                "node_id": "1",
                "input_name": "image",
                "type": "text",
                "required": True,
            }
        },
        "outputs": {"result": [{"node_id": "2", "output_type": "images"}]},
    }
    with client:
        r = client.put(
            "/api/workflows/test_custom_wf/versions/2/mappings", json=payload
        )
        assert r.status_code == 200, r.text
        assert r.json()["inputs"]["prompt"]["input_name"] == "image"

        # reflected back on the active spec
        spec = registry.get_spec("test_custom_wf", 2)
        assert spec.inputs["prompt"].input_name == "image"


def test_save_mappings_rejects_unknown_type():
    payload = {
        "inputs": {
            "bad": {
                "node_id": "1",
                "input_name": "image",
                "type": "not_a_type",
                "required": True,
            }
        },
        "outputs": {},
    }
    with client:
        r = client.put(
            "/api/workflows/test_custom_wf/versions/2/mappings", json=payload
        )
    assert r.status_code == 400


# --- Validation (errors vs warnings) ----------------------------------------


def _spec_with_outputs():
    return WorkflowSpec(
        id="v",
        name="V",
        category="general_generation",
        version=1,
        workflow_dir=registry._persistent_root(),
        outputs={},  # populated per test
    )


def test_validate_splits_errors_and_warnings():
    spec = _spec_with_outputs()
    spec.inputs["prompt"] = InputMapping(
        name="prompt", node_id="1", input_name="text", type="text", required=True
    )
    spec.inputs["ghost_field"] = InputMapping(
        name="ghost_field", node_id="1", input_name="nope", type="text"
    )
    spec.outputs["images"] = [OutputMapping(name="images", node_id="3")]
    template = {
        "1": {"class_type": "TextIn", "inputs": {"text": "hi"}},
        "2": {"class_type": "GhostNode", "inputs": {}},
        "3": {"class_type": "SaveImage", "inputs": {}},
    }
    object_info = {
        "TextIn": {"input": {"required": {"text": ["STRING"]}, "optional": {}}},
        "SaveImage": {"input": {"required": {}, "optional": {}}},
        "UNETLoader": {
            "input": {
                "required": {"unet_name": [["real.safetensors"]]},
                "optional": {},
            }
        },
        "LoraLoader": {
            "input": {"required": {"lora_name": [["real_lora.safetensors"]]}, "optional": {}}
        },
    }
    # a missing core model -> error; a missing lora -> warning
    template["9"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "ghost.safetensors"},
    }
    template["10"] = {
        "class_type": "LoraLoader",
        "inputs": {"loras": json.dumps([{"name": "ghost_lora.safetensors", "enabled": True}])},
    }
    errors, warnings = validate_workflow(spec, template, object_info)
    assert any("GhostNode" in e for e in errors)
    assert any("nope" in e for e in errors)
    assert any("ghost.safetensors" in e for e in errors)
    assert any("ghost_lora.safetensors" in w for w in warnings)
    # lora issue must not be in the blocking error set
    assert not any("ghost_lora" in e for e in errors)


def test_validate_no_output_mapping_is_error():
    spec = _spec_with_outputs()
    spec.inputs["prompt"] = InputMapping(
        name="prompt", node_id="1", input_name="text", type="text", required=True
    )
    template = {"1": {"class_type": "TextIn", "inputs": {"text": "hi"}}}
    object_info = {
        "TextIn": {"input": {"required": {"text": ["STRING"]}, "optional": {}}}
    }
    errors, _ = validate_workflow(spec, template, object_info)
    assert any("no output mapping" in e for e in errors)


# --- Inspection --------------------------------------------------------------


def test_inspect_report_structure():
    template = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
        "2": {
            "class_type": "KSampler",
            "inputs": {"seed": 5, "steps": 20, "width": 512, "height": 512, "cfg": 7.0, "denoise": 1.0},
        },
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        "4": {"class_type": "GhostNode", "inputs": {}},
    }
    object_info = {
        "LoadImage": {
            "input": {"required": {"image": [["a.png"]]}, "optional": {}},
            "output": {"type": ["IMAGE"], "name": ["image"]},
        },
        "KSampler": {
            "input": {
                "required": {
                    "seed": ["INT"],
                    "steps": ["INT"],
                    "width": ["INT"],
                    "height": ["INT"],
                    "cfg": ["FLOAT"],
                    "denoise": ["FLOAT"],
                },
                "optional": {},
            },
            "output": {"type": ["LATENT"], "name": ["latent"]},
        },
        "SaveImage": {
            "input": {"required": {"images": [["IMAGE"]]}, "optional": {}},
            "output": {"type": ["IMAGE"], "name": ["images"]},
        },
    }
    report = inspect_workflow(template, object_info)
    assert report["node_count"] == 4
    assert "1" in report["image_loaders"]
    assert report["output_nodes"] == ["3"]
    assert report["missing_classes"] == ["GhostNode"]
    seeds = {(i["node_id"], i["field"]) for i in report["seed_inputs"]}
    assert ("2", "seed") in seeds
    dims = {(i["node_id"], i["field"]) for i in report["dimension_inputs"]}
    assert ("2", "width") in dims and ("2", "height") in dims
    combos = {(i["node_id"], i["field"]) for i in report["combo_inputs"]}
    assert ("1", "image") in combos


def test_inspect_endpoint_returns_report():
    with client:
        response = client.get("/api/workflows/qwen_image_gen_v1/versions/1")
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is True
    assert body["report"]["node_count"] > 0
    assert "nodes" in body["report"]
    assert "output_nodes" in body["report"]
    assert body["inputs"]


# --- Test endpoint (real inference submission) -------------------------------


def test_test_endpoint_submits_real_job(monkeypatch):
    monkeypatch.setattr(
        comfyui_client,
        "get_status",
        AsyncMock(return_value=ComfyuiStatus(connected=True, version="0.46.0")),
    )
    monkeypatch.setattr(
        comfyui_client, "object_info", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        generation, "validate_workflow", lambda spec, template, oi: ([], [])
    )
    monkeypatch.setattr(
        comfyui_client,
        "submit_prompt",
        AsyncMock(return_value="prompt-gen-test"),
    )
    with client:
        response = client.post(
            "/api/workflows/qwen_image_gen_v1/test",
            json={"test_inputs": {"prompt": "hello test"}},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["submitted"] is True
    assert body["job_client_id"]

    with SessionLocal() as db:
        job = db.query(Job).filter_by(client_id=body["job_client_id"]).first()
        assert job is not None
        assert job.workflow_id == "qwen_image_gen_v1"
        assert job.workflow_version == 1
        assert job.comfyui_prompt_id == "prompt-gen-test"


def test_test_endpoint_reports_missing_required_input(monkeypatch):
    monkeypatch.setattr(
        comfyui_client,
        "get_status",
        AsyncMock(return_value=ComfyuiStatus(connected=True, version="0.46.0")),
    )
    monkeypatch.setattr(comfyui_client, "object_info", AsyncMock(return_value={}))
    monkeypatch.setattr(
        generation, "validate_workflow", lambda spec, template, oi: ([], [])
    )
    with client:
        # person-swap requires images that are not provided
        response = client.post(
            "/api/workflows/qwen_person_swap_v1/test",
            json={"test_inputs": {"composition_prompt": "x"}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["submitted"] is False
    assert any("Missing required input" in i for i in body["issues"])


# --- Disable gating ----------------------------------------------------------


def test_disabled_workflow_blocks_submit_but_test_ignores(monkeypatch):
    with client:
        client.patch("/api/workflows/qwen_image_gen_v1", json={"enabled": False})

    async def run_disabled():
        with SessionLocal() as db:
            try:
                await generation.submit_generation(
                    db, "qwen_image_gen_v1", {"prompt": "hi"}
                )
                return None
            except JobError as exc:
                return exc.status_code

    assert asyncio.run(run_disabled()) == 409

    # restore
    with client:
        client.patch("/api/workflows/qwen_image_gen_v1", json={"enabled": True})
