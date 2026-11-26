import copy
import json

import pytest
from fastapi.testclient import TestClient

from app.comfyui.adapter import WorkflowAdapter
from app.comfyui.registry import (
    WorkflowSpec,
    InputMapping,
    load_template,
    missing_custom_nodes,
    invalid_mappings,
    missing_models,
)
from app.main import app
from app.schemas import JobError

SPEC_DIR = "workflows/character_swap/qwen_person_swap_v1"


def spec_and_template():
    spec = WorkflowSpec.from_dir(
        __import__("pathlib").Path(__file__).resolve().parent.parent.parent
        / SPEC_DIR
    )
    return spec, load_template(spec)


def tiny_spec():
    return WorkflowSpec(
        id="tiny",
        name="Tiny",
        category="general_generation",
        version=1,
        workflow_dir=__import__("pathlib").Path("/tmp"),
        inputs={
            "prompt": InputMapping(
                name="prompt",
                node_id="1",
                input_name="text",
                type="text",
                required=True,
            ),
            "width": InputMapping(
                name="width",
                node_id="1",
                input_name="width",
                type="width",
                default=512,
            ),
            "seed": InputMapping(
                name="seed",
                node_id="1",
                input_name="seed",
                type="seed",
            ),
            "flag": InputMapping(
                name="flag",
                node_id="1",
                input_name="flag",
                type="boolean",
            ),
        },
        outputs={},
    )


def tiny_template():
    return {
        "1": {
            "inputs": {"text": "old", "width": 512, "seed": 1, "flag": False},
            "class_type": "FakeNode",
        }
    }


def test_prepare_applies_values_to_copy_not_template():
    spec = tiny_spec()
    template = tiny_template()
    snapshot = copy.deepcopy(template)
    adapter = WorkflowAdapter(spec, template)
    workflow, applied = adapter.prepare({"prompt": "hello"}, {})
    assert workflow["1"]["inputs"]["text"] == "hello"
    assert workflow["1"]["inputs"]["width"] == 512
    assert template == snapshot
    assert applied["prompt"] == "hello"


def test_prepare_seed_randomization():
    spec = tiny_spec()
    adapter = WorkflowAdapter(spec, tiny_template())
    workflow, _ = adapter.prepare({"prompt": "x", "seed": "random"}, {})
    seed = workflow["1"]["inputs"]["seed"]
    assert isinstance(seed, int)
    assert seed >= 0


def test_prepare_seed_explicit_value_kept():
    spec = tiny_spec()
    adapter = WorkflowAdapter(spec, tiny_template())
    workflow, _ = adapter.prepare({"prompt": "x", "seed": 42}, {})
    assert workflow["1"]["inputs"]["seed"] == 42


def test_prepare_missing_required_raises():
    spec = tiny_spec()
    adapter = WorkflowAdapter(spec, tiny_template())
    with pytest.raises(JobError) as exc:
        adapter.prepare({}, {})
    assert exc.value.status_code == 422
    assert "prompt" in str(exc.value)


def test_prepare_coercions():
    spec = tiny_spec()
    adapter = WorkflowAdapter(spec, tiny_template())
    workflow, _ = adapter.prepare(
        {"prompt": "x", "flag": "true", "width": "768.0"}, {}
    )
    assert workflow["1"]["inputs"]["flag"] is True
    assert workflow["1"]["inputs"]["width"] == 768


def test_prepare_image_filename_mapping():
    spec = tiny_spec()
    spec.inputs["img"] = InputMapping(
        name="img", node_id="1", input_name="image", type="image", required=True
    )
    spec_template = tiny_template()
    spec_template["1"]["inputs"]["image"] = "old.jpg"
    adapter = WorkflowAdapter(spec, spec_template)
    workflow, _ = adapter.prepare(
        {"prompt": "x"}, {"img": "sf_abc123.png"}
    )
    assert workflow["1"]["inputs"]["image"] == "sf_abc123.png"


def test_prepare_image_required_but_not_uploaded():
    spec = tiny_spec()
    spec.inputs["img"] = InputMapping(
        name="img", node_id="1", input_name="image", type="image", required=True
    )
    spec_template = tiny_template()
    spec_template["1"]["inputs"]["image"] = "old.jpg"
    adapter = WorkflowAdapter(spec, spec_template)
    with pytest.raises(JobError) as exc:
        adapter.prepare({"prompt": "x"}, {})
    assert exc.value.status_code == 422
    assert "img" in str(exc)


def test_person_swap_template_integrity():
    spec, template = spec_and_template()
    adapter = WorkflowAdapter(spec, template)
    assert adapter.check_template_integrity() == []


def object_info_fixture():
    return {
        "LoadImage": {
            "input": {"required": {"image": [["a.jpg"]]}, "optional": {}}
        },
        "FakeNode": {"input": {"required": {}, "optional": {}}},
        "AUSBOSS_NODES_Text": {
            "input": {"required": {"text": [["STRING"]]}, "optional": {}}
        },
        "PrimitiveBoolean": {
            "input": {"required": {"value": [["BOOLEAN"]]}, "optional": {}}
        },
        "AUSBOSS_NODES_Seed": {
            "input": {
                "required": {"seed": [["INT"]]},
                "optional": {},
            }
        },
        "AUSBOSS_NODES_Integer": {
            "input": {
                "required": {"value": [["INT"]]},
                "optional": {},
            }
        },
    }


def test_missing_custom_nodes_detected():
    spec, template = spec_and_template()
    info = object_info_fixture()
    missing = missing_custom_nodes(spec, template, info)
    assert any("CLIPLoader" in m for m in missing)
    assert any("KSampler" in m for m in missing)


def test_invalid_mapping_detected():
    spec = tiny_spec()
    spec.inputs["prompt"].input_name = "nonexistent_field"
    issues = invalid_mappings(spec, tiny_template(), object_info_fixture())
    assert any("nonexistent_field" in i for i in issues)


def test_missing_node_id_detected():
    spec = tiny_spec()
    spec.inputs["prompt"].node_id = "99"
    issues = invalid_mappings(spec, tiny_template(), object_info_fixture())
    assert any("99" in i for i in issues)


def test_missing_model_detected():
    info = {
        "UNETLoader": {
            "input": {
                "required": {"unet_name": [["real_model.safetensors"]]},
                "optional": {},
            }
        }
    }
    template = {
        "9": {
            "inputs": {"unet_name": "ghost_model.safetensors"},
            "class_type": "UNETLoader",
        }
    }
    spec = WorkflowSpec(
        id="x",
        name="X",
        category="general_generation",
        version=1,
        workflow_dir=__import__("pathlib").Path("/tmp"),
    )
    issues = missing_models(spec, template, info)
    assert any("ghost_model.safetensors" in i for i in issues)


def test_registry_lists_three_workflows():
    with TestClient(app) as client:
        response = client.get("/api/workflows")
    assert response.status_code == 200
    ids = {w["id"] for w in response.json()}
    assert {
        "qwen_image_gen_v1",
        "qwen_image_edit_v1",
        "qwen_person_swap_v1",
    } <= ids


def test_workflow_test_endpoint_reports_connectivity():
    with TestClient(app) as client:
        response = client.post("/api/workflows/qwen_person_swap_v1/test")
    assert response.status_code == 200
    body = response.json()
    assert "issues" in body
    assert "connectivity" in body
