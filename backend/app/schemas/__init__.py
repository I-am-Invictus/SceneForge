from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    comfyui_http_url: str
    comfyui_ws_url: str
    jpeg_quality: int
    thumb_max_dim: int


class SettingsUpdate(BaseModel):
    comfyui_http_url: str | None = None
    comfyui_ws_url: str | None = None
    jpeg_quality: int | None = Field(default=None, ge=10, le=100)
    thumb_max_dim: int | None = Field(default=None, ge=64, le=2048)


class ComfyuiStatus(BaseModel):
    connected: bool
    version: str | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    comfyui_connected: bool
