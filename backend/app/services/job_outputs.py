import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, or_, select
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
from app.services import galleries as gallery_service
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


def remove_job(db: Session, client_id: str) -> str:
    """Remove a job that has not started (``pending``/``dispatching``).

    This is the queue "remove" action and is deliberately distinct from
    deleting generated output or historical job records: a not-started job has
    no outputs and no files, so removing it just drops its queue entry. A job
    that has already reached ComfyUI (``queued``/``running``) must be cancelled
    instead, so it is rejected here.
    """
    job = db.scalar(select(Job).where(Job.client_id == client_id))
    if job is None:
        raise JobError(404, "Job not found")
    if job.status not in ("pending", "dispatching"):
        raise JobError(
            409,
            f"Job has started and cannot be removed (status: {job.status}); "
            "cancel it instead",
        )
    removed = job.client_id
    db.delete(job)
    db.commit()
    return removed


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

    # A file is only removed when no other record references it. Outputs
    # moved into a library share the asset file's stored path, so asset
    # records count as references too (deleting such an output keeps the
    # image in the library).
    removable = []
    for rel_path in candidate_paths:
        output_refs = (
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
        asset_refs = (
            db.query(AssetFile)
            .filter(
                or_(
                    AssetFile.stored_path == rel_path,
                    AssetFile.thumbnail_path == rel_path,
                )
            )
            .count()
        )
        if output_refs == 0 and asset_refs == 0:
            removable.append(rel_path)

    # Drop any gallery memberships first (the foreign key also cascades this);
    # deleting an image must never leave dangling gallery rows.
    removed = gallery_service.cleanup_output_memberships(db, row.id)
    if removed:
        logger.info(
            "Removed %d gallery membership(s) for deleted output %s",
            removed,
            row.id,
        )

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


def _next_sort_order(db: Session, asset_id: int) -> int:
    value = db.scalar(
        select(func.coalesce(func.max(AssetFile.sort_order), -1)).where(
            AssetFile.asset_id == asset_id
        )
    )
    return int(value) + 1


def add_output_to_asset(
    db: Session,
    client_id: str,
    output_id: int,
    kind: str,
    asset_id: int,
    make_default: bool = False,
) -> Job:
    """Attach a generated output to an existing asset's reference collection.

    Unlike :func:`move_output_to_library` (which always creates a new asset),
    this adds the image as a reference of an existing Scene or Character.

    The image bytes are not duplicated: if the output already lives in a
    library (its stored path is shared by another asset reference) the existing
    file is reused as-is. Otherwise the bytes are relocated into the
    destination asset's storage dir, mirroring the "new asset" move. The
    JobOutput row is updated in place so the image stays in the job's results
    and generation history. Existing references, their ordering, and their
    default status are preserved unless ``make_default`` is requested.
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
        raise JobError(409, "Output has no stored file to add")
    asset = db.get(Asset, asset_id)
    if asset is None or asset.kind != kind:
        raise JobError(404, "Asset not found")

    base = get_settings().data_dirs["base"].resolve()
    current = (base / row.stored_path).resolve()
    if not current.is_relative_to(base):
        raise JobError(
            400, f"Refusing to add path outside managed storage: {row.stored_path}"
        )
    if not current.is_file():
        raise JobError(409, "Stored output file is missing")

    # Prevent adding the same image as a second reference of this asset.
    already = (
        db.query(AssetFile)
        .filter(AssetFile.asset_id == asset.id)
        .filter(AssetFile.stored_path == row.stored_path)
        .first()
    )
    if already is not None:
        raise JobError(409, "This image is already a reference of that asset")

    # Does the image already live in a library? If so, share its physical file
    # instead of moving or copying it (avoids duplicate image files).
    existing_ref = (
        db.query(AssetFile).filter(AssetFile.stored_path == row.stored_path).first()
    )

    if existing_ref is not None:
        stored_rel = existing_ref.stored_path
        thumb_rel = existing_ref.thumbnail_path
        width, height = existing_ref.width, existing_ref.height
        size_bytes = existing_ref.size_bytes
        mime = existing_ref.mime
        dest = current  # unchanged, for best-effort thumbnail reuse below
        generate_thumb = False
    else:
        extension = Path(row.stored_path).suffix.lower()
        if extension not in image_service.ALLOWED_EXTENSIONS:
            extension = ".png"
        file_uuid = uuid.uuid4().hex
        stored_rel = f"{asset.storage_dir}/{file_uuid}{extension}"
        thumb_rel = f"thumbnails/{kind}/{file_uuid}.jpg"
        dest = (base / stored_rel).resolve()
        if not dest.is_relative_to(base):
            raise JobError(
                400, f"Refusing to add path outside managed storage: {stored_rel}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Relocate the bytes (same filesystem, atomic rename) before the DB
        # changes so a failure leaves everything untouched.
        shutil.move(str(current), str(dest))
        data = dest.read_bytes()
        width, height = image_service.validate_image_bytes(data)
        size_bytes = len(data)
        mime = image_service.MIME_BY_EXTENSION.get(extension, row.mime or "image/png")
        row.stored_path = stored_rel
        generate_thumb = True

    has_default = any(f.is_default for f in asset.files)
    is_default = make_default or not has_default
    asset_file = AssetFile(
        asset_id=asset.id,
        display_name=image_service.display_name_from_filename(row.comfyui_filename),
        stored_path=stored_rel,
        thumbnail_path=thumb_rel,
        width=width,
        height=height,
        size_bytes=size_bytes,
        mime=mime,
        is_default=is_default,
        sort_order=_next_sort_order(db, asset.id),
    )
    db.add(asset_file)
    db.flush()
    if is_default:
        for f in asset.files:
            if f.id != asset_file.id:
                f.is_default = False
    db.commit()

    if generate_thumb:
        # The asset reference needs its own library thumbnail; a transiently
        # missing one is tolerated (matches the asset-upload convention).
        thumb = (base / thumb_rel).resolve()
        try:
            jpeg_quality, thumb_max_dim = image_settings(db)
            image_service.make_thumbnail(dest, thumb, thumb_max_dim, jpeg_quality)
        except OSError as exc:
            logger.warning("Could not create library thumbnail for %s: %s", stored_rel, exc)

    db.refresh(job)
    return job
