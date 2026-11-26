from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import Asset, ASSET_KINDS, KIND_CHARACTER
from app.schemas.assets import (
    AssetFileOut,
    AssetMove,
    AssetOut,
    AssetPatch,
    FolderCreate,
    FolderOut,
    FolderRename,
)
from app.services import assets as asset_service
from app.services.assets import AssetError, prepare_upload
from app.services import folders as folder_service
from app.services.folders import FolderError

router = APIRouter(prefix="/api/libraries/{kind}", tags=["assets"])

MAX_FILES_PER_UPLOAD = 20


def _check_kind(kind: str) -> None:
    if kind not in ASSET_KINDS:
        raise HTTPException(status_code=404, detail="Unknown library")


def _raise_service_error(exc: AssetError | FolderError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc))


def serialize_file(asset_file) -> AssetFileOut:
    return AssetFileOut(
        id=asset_file.id,
        display_name=asset_file.display_name,
        width=asset_file.width,
        height=asset_file.height,
        size_bytes=asset_file.size_bytes,
        mime=asset_file.mime,
        is_default=asset_file.is_default,
        sort_order=asset_file.sort_order,
        created_at=asset_file.created_at,
        thumbnail_url=f"/media/thumbnails/{asset_file.id}",
        original_url=f"/media/assets/{asset_file.id}",
    )


def serialize_asset(asset: Asset) -> AssetOut:
    files = [serialize_file(f) for f in asset.files]
    default = next((f for f in asset.files if f.is_default), None)
    thumb = default or (asset.files[0] if asset.files else None)
    return AssetOut(
        id=asset.id,
        kind=asset.kind,
        name=asset.name,
        folder_id=asset.folder_id,
        is_favorite=asset.is_favorite,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        files=files,
        thumbnail_url=f"/media/thumbnails/{thumb.id}" if thumb else None,
        reference_count=len(asset.files),
    )


@router.get("/folders", response_model=list[FolderOut])
async def list_folders(kind: str, db: Session = Depends(get_db)):
    _check_kind(kind)
    return folder_service.list_folders(db, kind)


@router.post("/folders", status_code=201, response_model=FolderOut)
async def create_folder(
    kind: str, payload: FolderCreate, db: Session = Depends(get_db)
):
    _check_kind(kind)
    try:
        return folder_service.create_folder(
            db, kind, payload.name, payload.parent_id
        )
    except FolderError as exc:
        _raise_service_error(exc)


@router.patch("/folders/{folder_id}", response_model=FolderOut)
async def rename_folder(
    kind: str,
    folder_id: int,
    payload: FolderRename,
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    try:
        return folder_service.rename_folder(db, kind, folder_id, payload.name)
    except FolderError as exc:
        _raise_service_error(exc)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(kind: str, folder_id: int, db: Session = Depends(get_db)):
    _check_kind(kind)
    try:
        folder_service.delete_folder(db, kind, folder_id)
    except FolderError as exc:
        _raise_service_error(exc)


@router.get("/assets", response_model=list[AssetOut])
async def list_assets(
    kind: str,
    q: str | None = None,
    folder_id: int | None = None,
    favorite: bool = False,
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    assets = asset_service.list_assets(
        db, kind, q=q, folder_id=folder_id, favorite_only=favorite
    )
    return [serialize_asset(a) for a in assets]


@router.post("/assets", status_code=201, response_model=list[AssetOut])
async def create_assets(
    kind: str,
    name: str | None = Form(default=None),
    folder_id: int | None = Form(default=None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=422, detail=f"Maximum {MAX_FILES_PER_UPLOAD} files per upload"
        )
    try:
        incoming = [await prepare_upload(f) for f in files]
        if kind == KIND_CHARACTER:
            asset = await asset_service.create_character(
                db, name or "", folder_id, incoming
            )
            return [serialize_asset(asset)]
        created = await asset_service.create_scenes(db, name, folder_id, incoming)
        return [serialize_asset(a) for a in created]
    except (AssetError, FolderError) as exc:
        _raise_service_error(exc)


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(kind: str, asset_id: int, db: Session = Depends(get_db)):
    _check_kind(kind)
    try:
        return serialize_asset(asset_service.get_asset(db, kind, asset_id))
    except AssetError as exc:
        _raise_service_error(exc)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
async def patch_asset(
    kind: str,
    asset_id: int,
    payload: AssetPatch,
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    try:
        asset = asset_service.update_asset(
            db,
            kind,
            asset_id,
            name=payload.name,
            is_favorite=payload.is_favorite,
        )
        return serialize_asset(asset)
    except AssetError as exc:
        _raise_service_error(exc)


@router.post("/assets/{asset_id}/move", response_model=AssetOut)
async def move_asset(
    kind: str,
    asset_id: int,
    payload: AssetMove,
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    try:
        asset = asset_service.move_asset(
            db, kind, asset_id, payload.folder_id
        )
        return serialize_asset(asset)
    except (AssetError, FolderError) as exc:
        _raise_service_error(exc)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(kind: str, asset_id: int, db: Session = Depends(get_db)):
    _check_kind(kind)
    try:
        asset_service.delete_asset(db, kind, asset_id)
    except AssetError as exc:
        _raise_service_error(exc)


@router.post(
    "/assets/{asset_id}/files", status_code=201, response_model=AssetOut
)
async def add_reference(
    kind: str,
    asset_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=422, detail=f"Maximum {MAX_FILES_PER_UPLOAD} files per upload"
        )
    asset = None
    try:
        for upload in files:
            incoming = await prepare_upload(upload)
            asset = await asset_service.add_reference(db, kind, asset_id, incoming)
        return serialize_asset(asset)
    except (AssetError, FolderError) as exc:
        _raise_service_error(exc)


@router.post(
    "/assets/{asset_id}/files/{file_id}/default", response_model=AssetOut
)
async def set_default(
    kind: str, asset_id: int, file_id: int, db: Session = Depends(get_db)
):
    _check_kind(kind)
    try:
        return serialize_asset(
            asset_service.set_default_file(db, kind, file_id)
        )
    except AssetError as exc:
        _raise_service_error(exc)


@router.delete(
    "/assets/{asset_id}/files/{file_id}", response_model=AssetOut
)
async def delete_reference(
    kind: str, asset_id: int, file_id: int, db: Session = Depends(get_db)
):
    _check_kind(kind)
    try:
        return serialize_asset(asset_service.delete_file(db, kind, file_id))
    except AssetError as exc:
        _raise_service_error(exc)
