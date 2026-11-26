from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas import SettingsRead, SettingsUpdate
from app.services.settings import (
    get_effective_settings,
    update_settings,
    validate_update,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _read(db: Session) -> SettingsRead:
    values = get_effective_settings(db)
    return SettingsRead(
        comfyui_http_url=values["comfyui_http_url"],
        comfyui_ws_url=values["comfyui_ws_url"],
        jpeg_quality=int(values["jpeg_quality"]),
        thumb_max_dim=int(values["thumb_max_dim"]),
    )


@router.get("", response_model=SettingsRead)
async def read_settings(db: Session = Depends(get_db)) -> SettingsRead:
    return _read(db)


@router.put("", response_model=SettingsRead)
async def put_settings(
    update: SettingsUpdate, db: Session = Depends(get_db)
) -> SettingsRead:
    errors = validate_update(update)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    update_settings(db, update.model_dump(exclude_none=True))
    return _read(db)
