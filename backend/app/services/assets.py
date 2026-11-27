import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Asset,
    AssetFile,
    Folder,
    Job,
    JobOutput,
    KIND_CHARACTER,
    KIND_SCENE,
)
from app.services import images
from app.services.folders import get_folder

logger = logging.getLogger(__name__)

IMAGE_WORKERS = 4
_image_semaphore = asyncio.Semaphore(IMAGE_WORKERS)

MAX_DESCRIPTION_LENGTH = 2000
MAX_TAGS = 20
MAX_TAG_LENGTH = 50


class AssetError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def normalize_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        tag = str(tag).strip()
        if not tag or tag in seen:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise AssetError(422, f"Tag too long (max {MAX_TAG_LENGTH}): {tag[:20]}…")
        seen.add(tag)
        result.append(tag)
    if len(result) > MAX_TAGS:
        raise AssetError(422, f"Too many tags (max {MAX_TAGS})")
    return result


@dataclass
class IncomingFile:
    data: bytes
    display_name: str
    extension: str
    mime: str
    width: int
    height: int


async def prepare_upload(upload: UploadFile) -> IncomingFile:
    chunk_size = 1024 * 1024
    max_bytes = images.MAX_UPLOAD_BYTES + 1
    data = b""
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        data += chunk
        if len(data) > max_bytes:
            raise AssetError(
                413,
                f"File exceeds {images.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
            )
    try:
        extension = images.safe_extension(upload.filename)
        width, height = await asyncio.to_thread(images.validate_image_bytes, data)
    except images.ImageError as exc:
        raise AssetError(422, str(exc)) from exc
    return IncomingFile(
        data=data,
        display_name=images.display_name_from_filename(upload.filename or "image"),
        extension=extension,
        mime=images.MIME_BY_EXTENSION[extension],
        width=width,
        height=height,
    )


def _root() -> Path:
    return get_settings().data_dirs["base"].resolve()


def _resolve_stored(rel_path: str) -> Path:
    root = _root()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root):
        raise AssetError(400, "Invalid storage path")
    return path


def _descendant_folder_ids(db: Session, folder_id: int) -> set[int]:
    ids = {folder_id}
    frontier = [folder_id]
    while frontier:
        child_ids = list(
            db.scalars(select(Folder.id).where(Folder.parent_id.in_(frontier)))
        )
        new = [c for c in child_ids if c not in ids]
        ids.update(new)
        frontier = new
    return ids


def list_assets(
    db: Session,
    kind: str,
    q: str | None = None,
    folder_id: int | None = None,
    favorite_only: bool = False,
) -> list[Asset]:
    stmt = select(Asset).where(Asset.kind == kind)
    if q:
        stmt = stmt.where(Asset.name.ilike(f"%{q.strip()}%"))
    if folder_id is not None:
        stmt = stmt.where(Asset.folder_id.in_(_descendant_folder_ids(db, folder_id)))
    if favorite_only:
        stmt = stmt.where(Asset.is_favorite.is_(True))
    return list(db.scalars(stmt.order_by(Asset.name.asc())))


def get_asset(db: Session, kind: str, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.kind != kind:
        raise AssetError(404, "Asset not found")
    return asset


async def _store_file(
    db: Session,
    asset: Asset,
    incoming: IncomingFile,
    sort_order: int,
    is_default: bool,
) -> AssetFile:
    settings = get_settings()
    file_uuid = uuid.uuid4().hex
    stored_rel = f"{asset.storage_dir}/{file_uuid}{incoming.extension}"
    thumb_rel = f"thumbnails/{asset.kind}/{file_uuid}.jpg"
    stored_path = _resolve_stored(stored_rel)
    thumb_path = _resolve_stored(thumb_rel)
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(stored_path.write_bytes, incoming.data)
    asset_file = AssetFile(
        asset_id=asset.id,
        display_name=incoming.display_name,
        stored_path=stored_rel,
        thumbnail_path=thumb_rel,
        width=incoming.width,
        height=incoming.height,
        size_bytes=len(incoming.data),
        mime=incoming.mime,
        is_default=is_default,
        sort_order=sort_order,
    )
    db.add(asset_file)
    db.commit()
    db.refresh(asset_file)
    async with _image_semaphore:
        await asyncio.to_thread(
            images.make_thumbnail,
            stored_path,
            thumb_path,
            settings.thumb_max_dim,
            settings.jpeg_quality,
        )
    return asset_file


def _next_sort_order(db: Session, asset_id: int) -> int:
    value = db.scalar(
        select(func.coalesce(func.max(AssetFile.sort_order), -1)).where(
            AssetFile.asset_id == asset_id
        )
    )
    return int(value) + 1


async def create_character(
    db: Session,
    name: str,
    folder_id: int | None,
    incoming: list[IncomingFile],
) -> Asset:
    name = name.strip()
    if not name:
        raise AssetError(422, "Character name is required")
    if len(name) > 200:
        raise AssetError(422, "Name too long")
    if not incoming:
        raise AssetError(422, "At least one reference image is required")
    folder = None
    if folder_id is not None:
        folder = get_folder(db, KIND_CHARACTER, folder_id)
    asset = Asset(
        kind=KIND_CHARACTER,
        name=name,
        folder_id=folder.id if folder else None,
        storage_dir=f"assets/{KIND_CHARACTER}/{uuid.uuid4().hex}",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    for index, file in enumerate(incoming):
        await _store_file(db, asset, file, sort_order=index, is_default=index == 0)
    return db.get(Asset, asset.id)


async def create_scenes(
    db: Session,
    name: str | None,
    folder_id: int | None,
    incoming: list[IncomingFile],
) -> list[Asset]:
    if not incoming:
        raise AssetError(422, "At least one image is required")
    folder = None
    if folder_id is not None:
        folder = get_folder(db, KIND_SCENE, folder_id)
    assets = []
    for index, file in enumerate(incoming):
        asset_name = (
            name.strip()
            if (name and name.strip() and len(incoming) == 1)
            else file.display_name
        )
        asset = Asset(
            kind=KIND_SCENE,
            name=asset_name[:200] or "Scene",
            folder_id=folder.id if folder else None,
            storage_dir=f"assets/{KIND_SCENE}/{uuid.uuid4().hex}",
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        await _store_file(db, asset, file, sort_order=index, is_default=True)
        assets.append(db.get(Asset, asset.id))
    return assets


def update_asset(
    db: Session,
    kind: str,
    asset_id: int,
    name: str | None = None,
    folder_id: int | None = None,
    is_favorite: bool | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Asset:
    asset = get_asset(db, kind, asset_id)
    if name is not None:
        name = name.strip()
        if not name:
            raise AssetError(422, "Asset name is required")
        if len(name) > 200:
            raise AssetError(422, "Name too long")
        asset.name = name
    if folder_id is not None:
        asset.folder_id = get_folder(db, kind, folder_id).id
    if is_favorite is not None:
        asset.is_favorite = is_favorite
    if description is not None:
        description = description.strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise AssetError(422, "Description too long")
        asset.description = description or None
    if tags is not None:
        asset.tags = json.dumps(normalize_tags(tags), ensure_ascii=False)
    db.commit()
    db.refresh(asset)
    return asset


def move_asset(
    db: Session, kind: str, asset_id: int, folder_id: int | None
) -> Asset:
    asset = get_asset(db, kind, asset_id)
    if folder_id is not None:
        asset.folder_id = get_folder(db, kind, folder_id).id
    else:
        asset.folder_id = None
    db.commit()
    db.refresh(asset)
    return asset


def _delete_file_on_disk(path_rel: str) -> None:
    try:
        path = _resolve_stored(path_rel)
    except AssetError:
        logger.warning("Refusing to delete file outside managed storage: %s", path_rel)
        return
    try:
        path.unlink(missing_ok=True)
        logger.info("Deleted asset file %s", path_rel)
    except OSError as exc:
        # The DB row is removed by the caller; an orphaned file is cosmetic
        # and must not fail the deletion.
        logger.warning("Could not delete %s: %s", path_rel, exc)


def _path_referenced_by_outputs(db: Session, rel_path: str) -> bool:
    # Outputs moved into a library share the asset file's stored path;
    # deleting the asset must not break job results that still serve it.
    return (
        db.query(JobOutput)
        .filter(
            or_(
                JobOutput.stored_path == rel_path,
                JobOutput.thumbnail_path == rel_path,
            )
        )
        .count()
        > 0
    )


def _file_referenced_by_job_inputs(db: Session, asset_file: AssetFile) -> bool:
    # Image inputs are recorded in each job's input summary as
    # {"asset_file_id": <id>}; historical before/after comparisons rely on
    # the source bytes staying available.
    pattern = f'"asset_file_id": {asset_file.id}'
    return (
        db.query(Job)
        .filter(Job.inputs_json.like(f"%{pattern}%"))
        .count()
        > 0
    )


def delete_asset(db: Session, kind: str, asset_id: int) -> None:
    """Remove an asset from its library.

    The library records are always removed. Image files are only unlinked
    when no other record references them: job outputs (moved results share
    the stored path) and historical job source associations keep their
    bytes, so generated results, job history, and comparisons stay intact.
    """
    asset = get_asset(db, kind, asset_id)
    for asset_file in list(asset.files):
        if (
            _path_referenced_by_outputs(db, asset_file.stored_path)
            or _file_referenced_by_job_inputs(db, asset_file)
        ):
            logger.info(
                "Keeping %s on disk: still referenced by job records",
                asset_file.stored_path,
            )
        else:
            _delete_file_on_disk(asset_file.stored_path)
        if not _path_referenced_by_outputs(db, asset_file.thumbnail_path):
            _delete_file_on_disk(asset_file.thumbnail_path)
    db.delete(asset)
    db.commit()


async def add_reference(
    db: Session,
    kind: str,
    asset_id: int,
    incoming: IncomingFile,
) -> Asset:
    asset = get_asset(db, kind, asset_id)
    if kind != KIND_CHARACTER:
        raise AssetError(409, "Only characters support multiple references")
    has_default = any(f.is_default for f in asset.files)
    await _store_file(
        db,
        asset,
        incoming,
        sort_order=_next_sort_order(db, asset.id),
        is_default=not has_default,
    )
    refreshed = db.get(Asset, asset.id)
    db.refresh(refreshed, ["files"])
    return refreshed


def delete_file(db: Session, kind: str, file_id: int) -> Asset:
    asset_file = db.get(AssetFile, file_id)
    if asset_file is None or asset_file.asset.kind != kind:
        raise AssetError(404, "File not found")
    asset = asset_file.asset
    was_default = asset_file.is_default
    remaining = [f for f in asset.files if f.id != file_id]
    _delete_file_on_disk(asset_file.stored_path)
    _delete_file_on_disk(asset_file.thumbnail_path)
    db.delete(asset_file)
    if was_default and remaining:
        remaining[0].is_default = True
    db.commit()
    refreshed = db.get(Asset, asset.id)
    db.refresh(refreshed, ["files"])
    return refreshed


def set_default_file(db: Session, kind: str, file_id: int) -> Asset:
    asset_file = db.get(AssetFile, file_id)
    if asset_file is None or asset_file.asset.kind != kind:
        raise AssetError(404, "File not found")
    asset = asset_file.asset
    for f in asset.files:
        f.is_default = f.id == asset_file.id
    db.commit()
    return db.get(Asset, asset.id)
