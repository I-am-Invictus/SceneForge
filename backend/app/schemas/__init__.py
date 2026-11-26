from pydantic import BaseModel


class SettingsRead(BaseModel):
    comfyui_http_url: str
    comfyui_ws_url: str


class SettingsUpdate(BaseModel):
    comfyui_http_url: str | None = None
    comfyui_ws_url: str | None = None


class ComfyuiStatus(BaseModel):
    connected: bool
    version: str | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    comfyui_connected: bool
