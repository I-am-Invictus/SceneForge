from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas import JobError  # noqa: F401 (re-export convenience)


class WorkflowInputOut(BaseModel):
    type: str
    required: bool
    default: object = None
    auto: str | None = None


class WorkflowOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    version: int
    active_version: int | None = None
    enabled: bool
    inputs: dict[str, WorkflowInputOut] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowVersionOut(BaseModel):
    id: str
    version: int
    is_active: bool
    inputs: dict[str, WorkflowInputOut] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowTestResult(BaseModel):
    id: str
    ok: bool
    connectivity: dict | None
    issues: list[str]
    version: int | None = None
    warnings: list[str] = []
    submitted: bool = False
    job_client_id: str | None = None


class WorkflowPatch(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    description: str | None = None


class WorkflowUpload(BaseModel):
    id: str
    name: str
    category: str
    description: str = ""
    workflow: dict
    inputs: dict[str, dict] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowVersionUpload(BaseModel):
    workflow: dict
    inputs: dict[str, dict] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowMappings(BaseModel):
    inputs: dict[str, dict] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowTestRequest(BaseModel):
    version: int | None = None
    test_inputs: dict = {}


class JobOutputOut(BaseModel):
    id: int
    node_id: str
    comfyui_filename: str
    width: int | None
    height: int | None
    size_bytes: int | None
    thumbnail_url: str
    original_url: str


class JobOut(BaseModel):
    client_id: str
    comfyui_prompt_id: str | None
    workflow_id: str
    workflow_name: str
    workflow_version: int
    category: str
    status: str
    progress: float
    prompt: str | None
    error: str | None
    inputs: dict = {}
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    outputs: list[JobOutputOut] = []


class GenerateRequest(BaseModel):
    inputs: dict = {}


class JobOutputMove(BaseModel):
    folder: Literal["character", "scene"]
