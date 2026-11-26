from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import AssetFile
from app.services.assets import AssetError, _resolve_stored

router = APIRouter(prefix="/media", tags=["media"])

_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def _serve(file_id: int, db: Session, want_thumbnail: bool):
    asset_file = db.get(AssetFile, file_id)
    if asset_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    rel_path = asset_file.thumbnail_path if want_thumbnail else asset_file.stored_path
    try:
        path = _resolve_stored(rel_path)
    except AssetError:
        raise HTTPException(status_code=404, detail="File not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not available")
    media_type = "image/jpeg" if want_thumbnail else asset_file.mime
    return FileResponse(path, media_type=media_type, headers=_CACHE_HEADERS)


@router.get("/thumbnails/{file_id}")
async def thumbnail(file_id: int, db: Session = Depends(get_db)):
    return _serve(file_id, db, want_thumbnail=True)


@router.get("/assets/{file_id}")
async def original(file_id: int, db: Session = Depends(get_db)):
    return _serve(file_id, db, want_thumbnail=False)
