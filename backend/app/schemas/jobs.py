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
    enabled: bool
    inputs: dict[str, WorkflowInputOut] = {}
    outputs: dict[str, list[dict]] = {}


class WorkflowTestResult(BaseModel):
    id: str
    ok: bool
    connectivity: dict | None
    issues: list[str]


class WorkflowPatch(BaseModel):
    enabled: bool | None = None


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
