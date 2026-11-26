import copy
import random

from app.comfyui.registry import WorkflowSpec
from app.schemas import JobError


class WorkflowAdapter:
    """Applies SceneForge input values to a copy of an API-format workflow.

    The template is never mutated: every prepare() call deep-copies it.
    """

    def __init__(self, spec: WorkflowSpec, template: dict):
        self.spec = spec
        self.template = template

    def check_template_integrity(self) -> list[str]:
        issues = []
        for node_id, node in self.template.items():
            if not isinstance(node, dict) or "class_type" not in node:
                issues.append(f"node {node_id}: malformed node definition")
        for name, mapping in self.spec.inputs.items():
            node = self.template.get(mapping.node_id)
            if node is None:
                issues.append(f"input '{name}': node {mapping.node_id} missing")
                continue
            if mapping.input_name not in node.get("inputs", {}):
                issues.append(
                    f"input '{name}': field '{mapping.input_name}' not on node {mapping.node_id}"
                )
        for name, mappings in self.spec.outputs.items():
            for mapping in mappings:
                if mapping.node_id not in self.template:
                    issues.append(f"output '{name}': node {mapping.node_id} missing")
        return issues

    def prepare(
        self, values: dict, image_filenames: dict[str, str]
    ) -> tuple[dict, dict]:
        workflow = copy.deepcopy(self.template)
        applied: dict[str, object] = {}
        for name, mapping in self.spec.inputs.items():
            if mapping.type == "image" and name in image_filenames:
                value = image_filenames[name]
            elif name in values and values[name] is not None:
                value = values[name]
            elif mapping.default is not None:
                value = mapping.default
            else:
                if mapping.required:
                    raise JobError(
                        422, f"Missing required input: {name}"
                    )
                continue
            if mapping.type == "seed":
                value = self._resolve_seed(value)
            value = self._coerce(name, mapping, value)
            node = workflow.get(mapping.node_id)
            if node is None:
                raise JobError(400, f"Workflow node {mapping.node_id} missing")
            node.setdefault("inputs", {})[mapping.input_name] = value
            applied[name] = value
        return workflow, applied

    @staticmethod
    def _resolve_seed(value: object) -> int:
        if value in (None, "random", "randomize"):
            return random.randint(0, 2**63 - 1)
        return int(value)

    def _coerce(self, name: str, mapping, value: object) -> object:
        if mapping.type in ("number", "width", "height"):
            number = float(value)
            return int(number) if number.is_integer() else number
        if mapping.type == "boolean":
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on")
            return bool(value)
        if mapping.type in ("text", "combo"):
            return str(value)
        if mapping.type == "seed":
            return int(value)
        return value
