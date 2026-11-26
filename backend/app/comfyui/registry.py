import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import ROOT_DIR

WORKFLOWS_ROOT = ROOT_DIR / "workflows"
CATEGORIES = ("general_generation", "image_modification", "character_swap")

MODEL_LOADER_FIELDS = {
    "CheckpointLoaderSimple": ("ckpt_name", "CheckpointLoaderSimple"),
    "UNETLoader": ("unet_name", "UNETLoader"),
    "CLIPLoader": ("clip_name", "CLIPLoader"),
    "VAELoader": ("vae_name", "VAELoader"),
    "CLIPLoaderGGUF": ("clip_name", "CLIPLoaderGGUF"),
    "UnetLoaderGGUF": ("unet_name", "UnetLoaderGGUF"),
    "LoraLoader": ("lora_name", "LoraLoader"),
}

INPUT_TYPES = (
    "text",
    "image",
    "number",
    "boolean",
    "combo",
    "seed",
    "width",
    "height",
)


@dataclass
class InputMapping:
    name: str
    node_id: str
    input_name: str
    type: str
    required: bool = False
    default: object = None
    auto: str | None = None

    @classmethod
    def from_dict(cls, name: str, raw: dict) -> "InputMapping":
        mapping = cls(
            name=name,
            node_id=str(raw["node_id"]),
            input_name=raw["input_name"],
            type=raw["type"],
            required=bool(raw.get("required", False)),
            default=raw.get("default"),
            auto=raw.get("auto"),
        )
        if mapping.type not in INPUT_TYPES:
            raise ValueError(f"input '{name}': unknown type {mapping.type!r}")
        return mapping


@dataclass
class OutputMapping:
    name: str
    node_id: str
    output_type: str = "images"

    @classmethod
    def from_dict(cls, name: str, raw: dict) -> "OutputMapping":
        return cls(
            name=name,
            node_id=str(raw["node_id"]),
            output_type=raw.get("output_type", "images"),
        )

    @classmethod
    def from_config(cls, name: str, raw) -> list["OutputMapping"]:
        if isinstance(raw, dict):
            return [cls.from_dict(name, raw)]
        return [cls.from_dict(name, item) for item in raw]


@dataclass
class WorkflowSpec:
    id: str
    name: str
    category: str
    version: int
    workflow_dir: Path
    inputs: dict[str, InputMapping] = field(default_factory=dict)
    outputs: dict[str, OutputMapping] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dir(cls, directory: Path) -> "WorkflowSpec":
        config_path = directory / "config.json"
        config = json.loads(config_path.read_text())
        spec = cls(
            id=config["id"],
            name=config["name"],
            category=config["category"],
            version=int(config.get("version", 1)),
            workflow_dir=directory,
            description=config.get("description", ""),
        )
        if spec.category not in CATEGORIES:
            raise ValueError(f"workflow '{spec.id}': unknown category {spec.category!r}")
        for name, raw in config.get("inputs", {}).items():
            spec.inputs[name] = InputMapping.from_dict(name, raw)
        for name, raw in config.get("outputs", {}).items():
            spec.outputs[name] = OutputMapping.from_config(name, raw)
        return spec

    def template_path(self) -> Path:
        return self.workflow_dir / self.workflow_file

    @property
    def workflow_file(self) -> str:
        return "workflow.json"


def discover_specs() -> list[WorkflowSpec]:
    specs = []
    if not WORKFLOWS_ROOT.is_dir():
        return specs
    for category in CATEGORIES:
        category_dir = WORKFLOWS_ROOT / category
        if not category_dir.is_dir():
            continue
        for entry in sorted(category_dir.iterdir()):
            if not entry.is_dir() or not (entry / "config.json").is_file():
                continue
            specs.append(WorkflowSpec.from_dir(entry))
    return specs


def load_template(spec: WorkflowSpec) -> dict:
    data = json.loads(spec.template_path().read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError(f"workflow '{spec.id}': template is not a node map")
    return data


def missing_custom_nodes(spec: WorkflowSpec, template: dict, object_info: dict) -> list[str]:
    missing = []
    for node_id, node in template.items():
        class_type = node.get("class_type")
        if class_type and class_type not in object_info:
            missing.append(f"node {node_id}: {class_type}")
    return missing


def invalid_mappings(spec: WorkflowSpec, template: dict, object_info: dict) -> list[str]:
    issues = []
    for name, mapping in spec.inputs.items():
        node = template.get(mapping.node_id)
        if node is None:
            issues.append(f"input '{name}': node {mapping.node_id} not in template")
            continue
        class_type = node.get("class_type", "")
        class_spec = object_info.get(class_type)
        if class_spec is None:
            continue
        defined = class_spec.get("input", {})
        known = set(defined.get("required", {})) | set(defined.get("optional", {}))
        if mapping.input_name not in known:
            issues.append(
                f"input '{name}': {class_type} has no field '{mapping.input_name}'"
            )
        if mapping.type == "combo":
            definition = (
                defined.get("required", {}).get(mapping.input_name)
                or defined.get("optional", {}).get(mapping.input_name)
            )
            options = (
                definition[0] if isinstance(definition, list) and definition else []
            )
            if isinstance(options, list) and isinstance(mapping.default, str):
                if options and mapping.default not in options:
                    issues.append(
                        f"input '{name}': default {mapping.default!r} not in options"
                    )
        for name, mappings in spec.outputs.items():
            for mapping in mappings:
                node = template.get(mapping.node_id)
                if node is None:
                    issues.append(
                        f"output '{name}': node {mapping.node_id} not in template"
                    )
    return issues


def missing_models(spec: WorkflowSpec, template: dict, object_info: dict) -> list[str]:
    issues = []
    for node_id, node in template.items():
        class_type = node.get("class_type", "")
        loader = MODEL_LOADER_FIELDS.get(class_type)
        if loader is None:
            continue
        field_name, list_class = loader
        value = node.get("inputs", {}).get(field_name)
        if not isinstance(value, str) or not value:
            continue
        class_spec = object_info.get(list_class)
        if class_spec is None:
            continue
        defined = class_spec.get("input", {})
        combo = (
            defined.get("required", {}).get(field_name)
            or defined.get("optional", {}).get(field_name)
        )
        options = combo[0] if isinstance(combo, list) and combo else []
        if isinstance(options, list) and options and value not in options:
            issues.append(f"node {node_id}: model {value!r} not found")
    lora_spec = object_info.get("LoraLoader")
    if lora_spec is not None:
        lora_combo = lora_spec.get("input", {}).get("required", {}).get("lora_name")
        lora_options = (
            lora_combo[0] if isinstance(lora_combo, list) and lora_combo else []
        )
        for node_id, node in template.items():
            raw_stack = node.get("inputs", {}).get("loras")
            if not isinstance(raw_stack, str):
                continue
            try:
                stack = json.loads(raw_stack)
            except json.JSONDecodeError:
                issues.append(f"node {node_id}: loras field is not valid JSON")
                continue
            for row in stack:
                if row.get("enabled") and isinstance(lora_options, list):
                    lora_name = row.get("name", "")
                    if lora_options and lora_name not in lora_options:
                        issues.append(f"node {node_id}: lora {lora_name!r} not found")
    return issues


def validate_registration(
    spec: WorkflowSpec, template: dict, object_info: dict
) -> list[str]:
    issues = missing_custom_nodes(spec, template, object_info)
    issues.extend(invalid_mappings(spec, template, object_info))
    issues.extend(missing_models(spec, template, object_info))
    return issues
