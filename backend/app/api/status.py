from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.comfyui import comfyui_client
from app.database.db import get_db
from app.schemas import ComfyuiStatus, HealthResponse
from app.services.settings import get_effective_settings

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db)) -> HealthResponse:
    urls = get_effective_settings(db)
    status = await comfyui_client.get_status(urls["comfyui_http_url"])
    return HealthResponse(status="ok", comfyui_connected=status.connected)


@router.get("/comfyui/status", response_model=ComfyuiStatus)
async def comfyui_status(db: Session = Depends(get_db)) -> ComfyuiStatus:
    urls = get_effective_settings(db)
    return await comfyui_client.get_status(urls["comfyui_http_url"])
