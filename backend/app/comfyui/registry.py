import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.config import ROOT_DIR, get_settings

# The built-in workflows shipped with the app (git-tracked, rsynced on deploy)
# are an immutable *seed*. User-managed workflows and every version of a
# workflow live under the persistent data dir so deploys (which rsync the app
# dir with --delete) never wipe them.
BUILTIN_WORKFLOWS_ROOT = ROOT_DIR / "workflows"
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
    inputs: dict[str, "InputMapping"] = field(default_factory=dict)
    outputs: dict[str, list["OutputMapping"]] = field(default_factory=dict)
    description: str = ""
    # The version currently selected for new jobs. Defaults to `version` when a
    # spec is built for a single version (e.g. the built-in seed layout).
    active_version: int | None = None
    # Where this spec's config.json / workflow.json actually live. For the
    # built-in single-dir layout this equals `workflow_dir`; for the persistent
    # versioned layout it is `workflow_dir/versions/{version}`.
    version_dir: Path | None = None

    def __post_init__(self):
        if self.active_version is None:
            self.active_version = self.version

    @property
    def _template_dir(self) -> Path:
        return self.version_dir if self.version_dir is not None else self.workflow_dir

    def template_path(self) -> Path:
        return self._template_dir / self.workflow_file

    @property
    def workflow_file(self) -> str:
        return "workflow.json"

    @classmethod
    def from_dir(cls, directory: Path) -> "WorkflowSpec":
        """Load the legacy single-dir layout: one `config.json` (with inputs
        and outputs) plus `workflow.json` in the same directory. Used by the
        built-in seed and existing unit tests."""
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


# --- Persistent, version-aware storage --------------------------------------
#
# Layout under the data dir:
#   {category}/{id}/config.json        -> {id, name, description, category, active_version}
#   {category}/{id}/versions/{N}/config.json     -> {version, inputs, outputs}
#   {category}/{id}/versions/{N}/workflow.json   -> raw ComfyUI API graph
#
# Each version directory is immutable once written: a new revision is a new
# directory, never an overwrite, so a version that existing jobs point at is
# never modified.

def _persistent_root() -> Path:
    return get_settings().data_dirs["workflows"]


def _read_meta(workflow_dir: Path) -> dict:
    return json.loads((workflow_dir / "config.json").read_text())


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _version_numbers(workflow_dir: Path) -> list[int]:
    versions_dir = workflow_dir / "versions"
    if not versions_dir.is_dir():
        return []
    numbers = []
    for entry in versions_dir.iterdir():
        if entry.is_dir() and (entry / "config.json").is_file():
            try:
                numbers.append(int(entry.name))
            except ValueError:
                continue
    return sorted(numbers)


def _first_existing_version(workflow_dir: Path) -> int | None:
    numbers = _version_numbers(workflow_dir)
    return numbers[0] if numbers else None


def _load_spec(workflow_dir: Path, version: int) -> WorkflowSpec:
    meta = _read_meta(workflow_dir)
    version_dir = workflow_dir / "versions" / str(version)
    vconfig = json.loads((version_dir / "config.json").read_text())
    spec = WorkflowSpec(
        id=meta["id"],
        name=meta["name"],
        category=meta["category"],
        version=int(version),
        workflow_dir=workflow_dir,
        version_dir=version_dir,
        active_version=int(meta.get("active_version", version)),
        description=meta.get("description", ""),
    )
    if spec.category not in CATEGORIES:
        raise ValueError(f"workflow '{spec.id}': unknown category {spec.category!r}")
    for name, raw in vconfig.get("inputs", {}).items():
        spec.inputs[name] = InputMapping.from_dict(name, raw)
    for name, raw in vconfig.get("outputs", {}).items():
        spec.outputs[name] = OutputMapping.from_config(name, raw)
    return spec


def _convert_to_new_layout(src_dir: Path, dest_dir: Path) -> None:
    """Convert a legacy single-dir workflow (config.json + workflow.json) into
    the versioned layout, writing into `dest_dir` (which may differ from the
    source, e.g. when seeding the persistent root from the built-in app dir)."""
    config = json.loads((src_dir / "config.json").read_text())
    version = int(config.get("version", 1))
    _write_json(
        dest_dir / "config.json",
        {
            "id": config["id"],
            "name": config["name"],
            "category": config["category"],
            "description": config.get("description", ""),
            "active_version": version,
        },
    )
    version_dir = dest_dir / "versions" / str(version)
    _write_json(
        version_dir / "config.json",
        {
            "version": version,
            "inputs": config.get("inputs", {}),
            "outputs": config.get("outputs", {}),
        },
    )
    shutil.copyfile(src_dir / "workflow.json", version_dir / "workflow.json")


def migrate_workflows() -> None:
    """Idempotently seed the persistent root from the built-in app dir and
    convert any workflow still in the legacy layout. Safe to call repeatedly."""
    persistent = _persistent_root()
    persistent.mkdir(parents=True, exist_ok=True)
    builtin = BUILTIN_WORKFLOWS_ROOT
    for category in CATEGORIES:
        category_dir = builtin / category
        if not category_dir.is_dir():
            continue
        for seed_dir in sorted(category_dir.iterdir()):
            if not seed_dir.is_dir() or not (seed_dir / "config.json").is_file():
                continue
            dest_dir = persistent / category / seed_dir.name
            if (dest_dir / "config.json").is_file():
                continue  # already present in persistent storage
            _convert_to_new_layout(seed_dir, dest_dir)
    # Defensive: convert any persistent workflow left in the legacy layout.
    for category_dir in persistent.iterdir():
        if not category_dir.is_dir():
            continue
        for id_dir in category_dir.iterdir():
            if (
                id_dir.is_dir()
                and (id_dir / "config.json").is_file()
                and (id_dir / "workflow.json").is_file()
                and not (id_dir / "versions").is_dir()
            ):
                _convert_to_new_layout_inplace(id_dir)


def _convert_to_new_layout_inplace(workflow_dir: Path) -> None:
    config = json.loads((workflow_dir / "config.json").read_text())
    version = int(config.get("version", 1))
    _write_json(
        workflow_dir / "config.json",
        {
            "id": config["id"],
            "name": config["name"],
            "category": config["category"],
            "description": config.get("description", ""),
            "active_version": version,
        },
    )
    _convert_to_new_layout(workflow_dir, workflow_dir)
    (workflow_dir / "workflow.json").unlink(missing_ok=True)


def _find_workflow_dir(workflow_id: str) -> Path | None:
    persistent = _persistent_root()
    for category in CATEGORIES:
        candidate = persistent / category / workflow_id
        if candidate.is_dir() and (candidate / "config.json").is_file():
            return candidate
    return None


def discover_specs() -> list[WorkflowSpec]:
    migrate_workflows()
    root = _persistent_root()
    specs: list[WorkflowSpec] = []
    if not root.is_dir():
        return specs
    for category in CATEGORIES:
        category_dir = root / category
        if not category_dir.is_dir():
            continue
        for entry in sorted(category_dir.iterdir()):
            if not entry.is_dir() or not (entry / "config.json").is_file():
                continue
            try:
                meta = _read_meta(entry)
                active = int(meta.get("active_version", 1))
                if not (entry / "versions" / str(active) / "config.json").is_file():
                    active = _first_existing_version(entry)
                    if active is None:
                        continue
                specs.append(_load_spec(entry, active))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
    return specs


def get_spec(workflow_id: str, version: int | None = None) -> WorkflowSpec:
    migrate_workflows()
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    meta = _read_meta(workflow_dir)
    if version is None:
        version = int(meta.get("active_version", 1))
    if not (workflow_dir / "versions" / str(version) / "config.json").is_file():
        raise ValueError(f"workflow '{workflow_id}' version {version} not found")
    return _load_spec(workflow_dir, int(version))


def list_versions(workflow_id: str) -> list[dict]:
    migrate_workflows()
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    meta = _read_meta(workflow_dir)
    active = int(meta.get("active_version", 1))
    versions = []
    for number in _version_numbers(workflow_dir):
        vconfig = json.loads(
            (workflow_dir / "versions" / str(number) / "config.json").read_text()
        )
        versions.append(
            {
                "version": number,
                "is_active": number == active,
                "input_count": len(vconfig.get("inputs", {})),
                "output_count": len(vconfig.get("outputs", {})),
            }
        )
    return versions


def workflow_meta(workflow_id: str) -> dict:
    migrate_workflows()
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    return _read_meta(workflow_dir)


def _validate_workflow_json(workflow: dict) -> None:
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("Workflow JSON must be a non-empty node map")
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or "class_type" not in node:
            raise ValueError(
                f"node {node_id}: not a valid API-format node (missing 'class_type')"
            )


def _validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category {category!r}; expected one of {CATEGORIES}")


def save_new_workflow(
    workflow_id: str,
    name: str,
    category: str,
    workflow: dict,
    inputs: dict,
    outputs: dict,
    description: str = "",
) -> WorkflowSpec:
    _validate_category(category)
    _validate_workflow_json(workflow)
    if _find_workflow_dir(workflow_id) is not None:
        raise ValueError(f"workflow '{workflow_id}' already exists")
    for raw_name, raw in inputs.items():
        InputMapping.from_dict(raw_name, raw)
    for raw_name, raw in outputs.items():
        OutputMapping.from_config(raw_name, raw)
    workflow_dir = _persistent_root() / category / workflow_id
    if workflow_dir.exists():
        raise ValueError(f"workflow '{workflow_id}' already exists")
    _write_json(
        workflow_dir / "config.json",
        {
            "id": workflow_id,
            "name": name,
            "category": category,
            "description": description,
            "active_version": 1,
        },
    )
    _write_json(
        workflow_dir / "versions" / "1" / "config.json",
        {"version": 1, "inputs": inputs, "outputs": outputs},
    )
    _write_json(workflow_dir / "versions" / "1" / "workflow.json", workflow)
    return get_spec(workflow_id, 1)


def save_new_version(
    workflow_id: str,
    workflow: dict,
    inputs: dict,
    outputs: dict,
    name: str | None = None,
    description: str | None = None,
) -> WorkflowSpec:
    _validate_workflow_json(workflow)
    for raw_name, raw in inputs.items():
        InputMapping.from_dict(raw_name, raw)
    for raw_name, raw in outputs.items():
        OutputMapping.from_config(raw_name, raw)
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    meta = _read_meta(workflow_dir)
    existing = _version_numbers(workflow_dir)
    version = (existing[-1] + 1) if existing else 1
    _write_json(
        workflow_dir / "versions" / str(version) / "config.json",
        {"version": version, "inputs": inputs, "outputs": outputs},
    )
    _write_json(
        workflow_dir / "versions" / str(version) / "workflow.json", workflow
    )
    if name is not None:
        meta["name"] = name
    if description is not None:
        meta["description"] = description
    meta["active_version"] = version
    _write_json(workflow_dir / "config.json", meta)
    return get_spec(workflow_id, version)


def save_mappings(
    workflow_id: str,
    version: int,
    inputs: dict,
    outputs: dict,
) -> WorkflowSpec:
    for raw_name, raw in inputs.items():
        InputMapping.from_dict(raw_name, raw)
    for raw_name, raw in outputs.items():
        OutputMapping.from_config(raw_name, raw)
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    version_dir = workflow_dir / "versions" / str(version)
    if not (version_dir / "config.json").is_file():
        raise ValueError(f"workflow '{workflow_id}' version {version} not found")
    _write_json(
        version_dir / "config.json",
        {"version": int(version), "inputs": inputs, "outputs": outputs},
    )
    return get_spec(workflow_id, version)


def set_active_version(workflow_id: str, version: int) -> WorkflowSpec:
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    if int(version) not in _version_numbers(workflow_dir):
        raise ValueError(f"workflow '{workflow_id}' version {version} not found")
    meta = _read_meta(workflow_dir)
    meta["active_version"] = int(version)
    _write_json(workflow_dir / "config.json", meta)
    return get_spec(workflow_id, int(version))


def update_meta(
    workflow_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    workflow_dir = _find_workflow_dir(workflow_id)
    if workflow_dir is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    meta = _read_meta(workflow_dir)
    if name is not None:
        meta["name"] = name
    if description is not None:
        meta["description"] = description
    _write_json(workflow_dir / "config.json", meta)
    return meta


# --- Template loading + validation -----------------------------------------


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
                issues.append(f"output '{name}': node {mapping.node_id} not in template")
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
