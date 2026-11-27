import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ASSET_KINDS,
    Asset,
    AssetFile,
    Job,
    JobOutput,
)
from app.schemas import JobError
from app.services import images as image_service
from app.services.settings import image_settings

logger = logging.getLogger(__name__)


def _unlink(base: Path, rel_path: str) -> None:
    try:
        (base / rel_path).resolve().unlink(missing_ok=True)
    except OSError as exc:
        # The DB row is already gone; an orphaned file is cosmetic and must
        # not fail the deletion.
        logger.warning("Could not remove %s: %s", rel_path, exc)


def delete_output(db: Session, client_id: str, output_id: int) -> Job:
    """Permanently delete a single generated output.

    Only the selected output row and its physical files (when unreferenced)
    are removed. The job, its other outputs, and any source asset are
    untouched.
    """
    job = db.query(Job).filter(Job.client_id == client_id).first()
    if job is None:
        raise JobError(404, "Job not found")
    row = db.get(JobOutput, output_id)
    if row is None or row.job_id != job.id:
        raise JobError(404, "Output not found for this job")

    base = get_settings().data_dirs["base"].resolve()
    candidate_paths = [p for p in (row.stored_path, row.thumbnail_path) if p]

    # Refuse to touch anything outside SceneForge-managed storage.
    for rel_path in candidate_paths:
        if not (base / rel_path).resolve().is_relative_to(base):
            raise JobError(
                400, f"Refusing to delete path outside managed storage: {rel_path}"
            )

    # A file is only removed when no other output record references it.
    # (Generated outputs are never referenced by asset-library records;
    # those live under separate, disjoint storage paths.)
    removable = []
    for rel_path in candidate_paths:
        referenced = (
            db.query(JobOutput)
            .filter(JobOutput.id != row.id)
            .filter(
                or_(
                    JobOutput.stored_path == rel_path,
                    JobOutput.thumbnail_path == rel_path,
                )
            )
            .count()
        )
        if referenced == 0:
            removable.append(rel_path)

    # Commit the DB change first so a storage failure can never leave the
    # database inconsistent with the gallery.
    db.delete(row)
    db.commit()
    for rel_path in removable:
        _unlink(base, rel_path)
    db.refresh(job)
    return job


def move_output_to_library(
    db: Session, client_id: str, output_id: int, kind: str
) -> Job:
    """Move a generated output into the Characters or Scenes library.

    The image bytes are relocated into the destination library's storage
    tree and registered as a new asset, so the image immediately appears in
    that library. The JobOutput row is updated in place, so the image stays
    available in the job's results and in generation history. The job's
    source asset is never touched, and the destination is always a fresh
    storage dir, so no existing file can be overwritten or duplicated.
    """
    if kind not in ASSET_KINDS:
        raise JobError(422, f"Unknown library: {kind}")
    job = db.query(Job).filter(Job.client_id == client_id).first()
    if job is None:
        raise JobError(404, "Job not found")
    row = db.get(JobOutput, output_id)
    if row is None or row.job_id != job.id:
        raise JobError(404, "Output not found for this job")
    if not row.stored_path:
        raise JobError(409, "Output has no stored file to move")

    base = get_settings().data_dirs["base"].resolve()
    current = (base / row.stored_path).resolve()
    if not current.is_relative_to(base):
        raise JobError(
            400, f"Refusing to move path outside managed storage: {row.stored_path}"
        )
    if not current.is_file():
        raise JobError(409, "Stored output file is missing")

    extension = Path(row.stored_path).suffix.lower()
    if extension not in image_service.ALLOWED_EXTENSIONS:
        extension = ".png"
    file_uuid = uuid.uuid4().hex
    asset_dir = f"assets/{kind}/{uuid.uuid4().hex}"
    stored_rel = f"{asset_dir}/{file_uuid}{extension}"
    thumb_rel = f"thumbnails/{kind}/{file_uuid}.jpg"
    dest = (base / stored_rel).resolve()
    thumb = (base / thumb_rel).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # If this output was previously moved into a library, that old entry
    # (located at the current stored_path) is replaced by this move.
    old_file = (
        db.query(AssetFile).filter(AssetFile.stored_path == row.stored_path).first()
    )

    # Relocate the bytes first (same filesystem, so an atomic rename); if
    # this fails, nothing in the database has changed yet.
    shutil.move(str(current), str(dest))

    data = dest.read_bytes()
    width, height = image_service.validate_image_bytes(data)

    if old_file is not None:
        old_asset = old_file.asset
        old_thumb_rel = old_file.thumbnail_path
        db.delete(old_file)
        if not [f for f in old_asset.files if f.id != old_file.id]:
            db.delete(old_asset)
        _unlink(base, old_thumb_rel)

    name = (job.prompt or row.comfyui_filename)[:200] or "Generated image"
    asset = Asset(
        kind=kind,
        name=name,
        folder_id=None,
        storage_dir=asset_dir,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    db.add(
        AssetFile(
            asset_id=asset.id,
            display_name=image_service.display_name_from_filename(
                row.comfyui_filename
            ),
            stored_path=stored_rel,
            thumbnail_path=thumb_rel,
            width=width,
            height=height,
            size_bytes=len(data),
            mime=image_service.MIME_BY_EXTENSION.get(extension, row.mime or "image/png"),
            is_default=True,
            sort_order=0,
        )
    )
    row.stored_path = stored_rel
    db.commit()

    # Thumbnail generation follows the asset-upload convention: the record is
    # committed first, a transiently missing thumbnail is tolerated.
    try:
        jpeg_quality, thumb_max_dim = image_settings(db)
        image_service.make_thumbnail(dest, thumb, thumb_max_dim, jpeg_quality)
    except OSError as exc:
        logger.warning("Could not create library thumbnail for %s: %s", stored_rel, exc)
    db.refresh(job)
    return job
