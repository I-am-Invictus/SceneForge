"""Structural inspection of a ComfyUI API-format workflow.

Produces a report of node ids, classes, and per-node inputs (with ComfyUI
types from ``object_info``), plus summary lists (image loaders, text/seed/
dimension/numeric/boolean/combo inputs, output nodes, custom-node
dependencies, referenced models). Node semantics are surfaced as *hints*
derived from the workflow structure and field names; the actual mapping is
always set explicitly by the user, never inferred here.
"""

from app.comfyui.registry import MODEL_LOADER_FIELDS

VALUE_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "IMAGE"}

IMAGE_LOADER_CLASSES = {
    "LoadImage",
    "LoadImageMask",
    "LoadImageFromDirectory",
    "LoadImages",
    "LoadT2IImages",
    "ImageFromBatch",
    "LoadVideoPath",
    "VHS_LoadVideo",
    "Load3DModel",
}

SAVE_PREVIEW_CLASSES = {
    "SaveImage",
    "SaveImageAdvanced",
    "PreviewImage",
    "SaveAnimatedWEBP",
    "SaveWEBM",
    "VideoCombine",
    "VHS_VideoCombine",
    "AUSBOSS_NODES_SaveImage",
}

_SEED_NAMES = {"seed", "noise_seed", "random_seed", "seed_control", "control_seed"}
_DIMENSION_NAMES = {"width", "height"}


def _field_definition(class_spec: dict, field_name: str):
    defined = class_spec.get("input", {})
    return (
        defined.get("required", {}).get(field_name)
        or defined.get("optional", {}).get(field_name)
    )


def _is_combo(field_def) -> bool:
    return (
        isinstance(field_def, list)
        and bool(field_def)
        and isinstance(field_def[0], list)
    )


def _base_types(field_def) -> set[str]:
    if _is_combo(field_def):
        return set()
    if isinstance(field_def, list) and all(isinstance(x, str) for x in field_def):
        return set(field_def)
    return set()


def _combo_options(class_spec: dict, field_name: str):
    field_def = _field_definition(class_spec, field_name)
    if _is_combo(field_def):
        return field_def[0]
    return None


def _is_link(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def _input_hint(field_name: str, base: set[str], combo: bool) -> str | None:
    lowered = field_name.lower()
    if lowered in _SEED_NAMES and (base & {"INT", "FLOAT"}):
        return "seed"
    if lowered in _DIMENSION_NAMES and (base & {"INT", "FLOAT"}):
        return "dimension"
    if combo:
        return "combo"
    if base == {"STRING"}:
        return "text"
    if base == {"BOOLEAN"}:
        return "boolean"
    if base and base <= {"INT", "FLOAT"}:
        return "number"
    return None


def _consumed_outputs(template: dict) -> set[tuple[str, int]]:
    consumed = set()
    for node in template.values():
        for value in node.get("inputs", {}).values():
            if _is_link(value):
                consumed.add((str(value[0]), value[1]))
    return consumed


def _node_inputs(node: dict, class_spec: dict | None) -> list[dict]:
    inputs = []
    for field_name, value in node.get("inputs", {}).items():
        field_def = (
            _field_definition(class_spec, field_name) if class_spec else None
        )
        combo = _is_combo(field_def)
        base = _base_types(field_def)
        optional = False
        if class_spec:
            optional = field_name in class_spec.get("input", {}).get("optional", {})
        inputs.append(
            {
                "name": field_name,
                "value": value,
                "is_link": _is_link(value),
                "is_combo": combo,
                "types": sorted(base) if base else None,
                "optional": optional,
                "hint": _input_hint(field_name, base, combo),
            }
        )
    return inputs


def _output_nodes(template: dict, object_info: dict, consumed: set) -> list[str]:
    result = set()
    for node_id, node in template.items():
        class_type = node.get("class_type", "")
        # Image loaders are sources (files enter the graph here), not outputs.
        if class_type in IMAGE_LOADER_CLASSES:
            continue
        class_spec = object_info.get(class_type)
        if class_spec:
            out_types = class_spec.get("output", {}).get("type", [])
            for index, types in enumerate(out_types):
                type_list = types if isinstance(types, list) else [types]
                if "IMAGE" in type_list and (node_id, index) not in consumed:
                    result.add(node_id)
                    break
        if class_type in SAVE_PREVIEW_CLASSES:
            result.add(node_id)
    return sorted(result, key=lambda n: (len(n), n))


def _image_loader_nodes(template: dict, object_info: dict) -> list[str]:
    result = set()
    for node_id, node in template.items():
        class_type = node.get("class_type", "")
        if class_type in IMAGE_LOADER_CLASSES:
            result.add(node_id)
            continue
        class_spec = object_info.get(class_type)
        if not class_spec:
            continue
        for field_name in node.get("inputs", {}):
            if _is_combo(_field_definition(class_spec, field_name)) and field_name.lower() in {
                "image", "images", "file", "filename", "upload", "video", "video_file",
            }:
                result.add(node_id)
                break
    return sorted(result, key=lambda n: (len(n), n))


def _referenced_models(template: dict, object_info: dict) -> list[dict]:
    models = []
    for node_id, node in template.items():
        class_type = node.get("class_type", "")
        loader = MODEL_LOADER_FIELDS.get(class_type)
        if loader is None:
            continue
        field_name, list_class = loader
        value = node.get("inputs", {}).get(field_name)
        if not isinstance(value, str) or not value:
            continue
        options = _combo_options(object_info.get(list_class, {}), field_name)
        models.append(
            {
                "node_id": node_id,
                "field": field_name,
                "value": value,
                "found": options is None or value in options,
            }
        )
    lora_spec = object_info.get("LoraLoader")
    lora_options = (
        _combo_options(lora_spec, "lora_name") if lora_spec is not None else None
    )
    for node_id, node in template.items():
        raw_stack = node.get("inputs", {}).get("loras")
        if not isinstance(raw_stack, str):
            continue
        try:
            import json as _json

            stack = _json.loads(raw_stack)
        except ValueError:
            continue
        for row in stack:
            if not isinstance(row, dict) or not row.get("enabled"):
                continue
            name = row.get("name", "")
            models.append(
                {
                    "node_id": node_id,
                    "field": "loras",
                    "value": name,
                    "found": lora_options is None or name in lora_options,
                }
            )
    return models


def inspect_workflow(template: dict, object_info: dict | None) -> dict:
    """Build the inspection report. ``object_info`` may be None (ComfyUI
    unreachable), in which case type/dependency detection is degraded."""
    object_info = object_info or {}
    consumed = _consumed_outputs(template)
    nodes = []
    custom_classes: set[str] = set()
    for node_id in sorted(template, key=lambda n: (len(n), n)):
        node = template[node_id]
        class_type = node.get("class_type", "")
        class_spec = object_info.get(class_type)
        if class_type:
            custom_classes.add(class_type)
        nodes.append(
            {
                "id": node_id,
                "class_type": class_type,
                "present": class_type in object_info,
                "is_image_loader": class_type in IMAGE_LOADER_CLASSES,
                "inputs": _node_inputs(node, class_spec),
            }
        )

    def _collect(kind: str) -> list[dict]:
        out = []
        for node in nodes:
            for inp in node["inputs"]:
                if inp["hint"] == kind and not inp["is_link"]:
                    out.append({"node_id": node["id"], "field": inp["name"]})
        return out

    def _collect_fields(pred) -> list[dict]:
        out = []
        for node in nodes:
            for inp in node["inputs"]:
                if pred(inp) and not inp["is_link"]:
                    out.append({"node_id": node["id"], "field": inp["name"]})
        return out

    image_loaders = _image_loader_nodes(template, object_info)
    missing_classes = sorted(c for c in custom_classes if c not in object_info)
    return {
        "node_count": len(template),
        "nodes": nodes,
        "image_loaders": image_loaders,
        "text_inputs": _collect("text"),
        "seed_inputs": _collect("seed"),
        "dimension_inputs": _collect("dimension"),
        "numeric_inputs": _collect_fields(
            lambda i: i["hint"] == "number"
        ),
        "boolean_inputs": _collect_fields(lambda i: i["hint"] == "boolean"),
        "combo_inputs": _collect_fields(lambda i: i["is_combo"]),
        "output_nodes": _output_nodes(template, object_info, consumed),
        "custom_classes": sorted(custom_classes),
        "missing_classes": missing_classes,
        "referenced_models": _referenced_models(template, object_info),
    }
