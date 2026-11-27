"""Workflow validation that distinguishes blocking errors from warnings.

Reuses the registry's object_info-based checks and adds input-type
compatibility. Returns ``(errors, warnings)``: an empty ``errors`` list means
the workflow is *eligible* to run (subject to ComfyUI connectivity); warnings
are things that may or may not prevent execution.
"""

from app.comfyui.adapter import WorkflowAdapter
from app.comfyui.registry import (
    WorkflowSpec,
    invalid_mappings,
    missing_custom_nodes,
    missing_models,
)

# Mapping type -> ComfyUI field base types that accept a value of that type.
_TYPE_COMPAT: dict[str, set[str]] = {
    "text": {"STRING"},
    "number": {"INT", "FLOAT"},
    "seed": {"INT", "FLOAT"},
    "width": {"INT"},
    "height": {"INT"},
    "boolean": {"BOOLEAN"},
    "image": {"IMAGE"},
}


def _field_definition(class_spec: dict, input_name: str):
    defined = class_spec.get("input", {})
    return (
        defined.get("required", {}).get(input_name)
        or defined.get("optional", {}).get(input_name)
    )


def _is_combo(field_def) -> bool:
    # A combo/dropdown field is ["option1", "option2", ...] wrapped: the first
    # element is itself the list of options.
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


def _type_compatibility(spec: WorkflowSpec, template: dict, object_info: dict) -> list[str]:
    issues = []
    for name, mapping in spec.inputs.items():
        node = template.get(mapping.node_id)
        if node is None:
            continue  # missing node already reported by invalid_mappings
        class_spec = object_info.get(node.get("class_type", ""))
        if class_spec is None:
            continue  # missing class already reported by missing_custom_nodes
        field_def = _field_definition(class_spec, mapping.input_name)
        if field_def is None:
            continue  # unknown field already reported by invalid_mappings
        if _is_combo(field_def):
            # A combo is a dropdown. "combo" selects an option; "image" sets a
            # filename into a file-picker combo (e.g. LoadImage.image) — both
            # write a string, so both are valid for combo fields.
            if mapping.type not in {"combo", "image"}:
                issues.append(
                    f"input '{name}': {node['class_type']}.{mapping.input_name} is a "
                    f"combo, but the mapping type is '{mapping.type}'"
                )
            continue
        accepted = _base_types(field_def)
        if not accepted:
            continue
        allowed = _TYPE_COMPAT.get(mapping.type)
        if allowed is None:
            continue
        if not (allowed & accepted):
            issues.append(
                f"input '{name}': type '{mapping.type}' is not compatible with "
                f"{node['class_type']}.{mapping.input_name} ({sorted(accepted)})"
            )
    return issues


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def validate_workflow(spec: WorkflowSpec, template: dict, object_info: dict):
    """Return ``(errors, warnings)`` for a workflow against ComfyUI."""
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(WorkflowAdapter(spec, template).check_template_integrity())
    errors.extend(missing_custom_nodes(spec, template, object_info))
    errors.extend(invalid_mappings(spec, template, object_info))
    if not spec.outputs:
        errors.append("no output mapping configured (the workflow would produce no results)")
    # Core model loaders block execution; missing LoRAs often do not.
    for issue in missing_models(spec, template, object_info):
        (warnings if "lora" in issue.lower() else errors).append(issue)
    errors.extend(_type_compatibility(spec, template, object_info))

    return _dedupe(errors), _dedupe(warnings)
