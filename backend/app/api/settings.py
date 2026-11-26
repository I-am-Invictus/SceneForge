from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas import SettingsRead, SettingsUpdate
from app.services.settings import get_effective_settings, update_settings, validate_url

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SCHEME_BY_KEY = {
    "comfyui_http_url": "http",
    "comfyui_ws_url": "ws",
}


@router.get("", response_model=SettingsRead)
async def read_settings(db: Session = Depends(get_db)) -> SettingsRead:
    return SettingsRead(**get_effective_settings(db))


@router.put("", response_model=SettingsRead)
async def put_settings(
    update: SettingsUpdate, db: Session = Depends(get_db)
) -> SettingsRead:
    changes = update.model_dump(exclude_none=True)
    for key, value in changes.items():
        error = validate_url(value, _SCHEME_BY_KEY[key])
        if error:
            raise HTTPException(status_code=422, detail=f"{key}: {error}")
    return SettingsRead(**update_settings(db, changes))
