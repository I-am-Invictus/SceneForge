from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import AssetFile, JobOutput
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


def _serve_job_output(output_id: int, db: Session, want_thumbnail: bool):
    row = db.get(JobOutput, output_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Output not found")
    rel_path = row.thumbnail_path if want_thumbnail else row.stored_path
    if not rel_path:
        raise HTTPException(status_code=404, detail="Output not available")
    try:
        path = _resolve_stored(rel_path)
    except AssetError:
        raise HTTPException(status_code=404, detail="Output not available")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Output not available")
    media_type = "image/jpeg" if want_thumbnail else (row.mime or "image/png")
    return FileResponse(path, media_type=media_type, headers=_CACHE_HEADERS)


@router.get("/job-thumbnails/{output_id}")
async def job_thumbnail(output_id: int, db: Session = Depends(get_db)):
    return _serve_job_output(output_id, db, want_thumbnail=True)


@router.get("/job-assets/{output_id}")
async def job_original(output_id: int, db: Session = Depends(get_db)):
    return _serve_job_output(output_id, db, want_thumbnail=False)
