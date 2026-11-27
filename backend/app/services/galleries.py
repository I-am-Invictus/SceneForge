import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AssetFile, Gallery, GalleryImage, Job, JobOutput

logger = logging.getLogger(__name__)

MAX_GALLERY_NAME = 200


class GalleryError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise GalleryError(422, "Gallery name is required")
    if len(name) > MAX_GALLERY_NAME:
        raise GalleryError(422, f"Gallery name too long (max {MAX_GALLERY_NAME})")
    return name


def get_gallery(db: Session, gallery_id: int) -> Gallery:
    gallery = db.get(Gallery, gallery_id)
    if gallery is None:
        raise GalleryError(404, "Gallery not found")
    return gallery


def create_gallery(db: Session, name: str) -> Gallery:
    gallery = Gallery(name=_clean_name(name))
    db.add(gallery)
    db.commit()
    db.refresh(gallery)
    return gallery


def rename_gallery(db: Session, gallery_id: int, name: str) -> Gallery:
    gallery = get_gallery(db, gallery_id)
    gallery.name = _clean_name(name)
    db.commit()
    db.refresh(gallery)
    return gallery


def delete_gallery(db: Session, gallery_id: int) -> None:
    """Delete a gallery and its membership rows only.

    The referenced job outputs — and their files, source assets, and history —
    are left untouched. Membership rows cascade with the gallery (ORM
    delete-orphan and DB ``ondelete=CASCADE``).
    """
    gallery = get_gallery(db, gallery_id)
    db.delete(gallery)
    db.commit()
    logger.info("Deleted gallery %s (%s)", gallery_id, gallery.name)


def list_galleries(db: Session) -> list[Gallery]:
    return list(db.scalars(select(Gallery).order_by(Gallery.name.asc())))


def get_output(db: Session, output_id: int) -> JobOutput:
    row = db.get(JobOutput, output_id)
    if row is None:
        raise GalleryError(404, "Image not found")
    return row


def gallery_members(db: Session, gallery_id: int) -> list[GalleryImage]:
    get_gallery(db, gallery_id)
    return list(
        db.scalars(
            select(GalleryImage)
            .where(GalleryImage.gallery_id == gallery_id)
            .order_by(GalleryImage.added_at.asc(), GalleryImage.id.asc())
        )
    )


def _membership(
    db: Session, gallery_id: int, output_id: int
) -> GalleryImage | None:
    return db.scalar(
        select(GalleryImage).where(
            GalleryImage.gallery_id == gallery_id,
            GalleryImage.job_output_id == output_id,
        )
    )


def add_images(db: Session, gallery_id: int, output_ids: list[int]) -> tuple[int, int]:
    """Add outputs to a gallery. Idempotent: existing memberships are skipped.

    Returns ``(added, skipped)``.
    """
    gallery = get_gallery(db, gallery_id)
    added = 0
    skipped = 0
    for output_id in output_ids:
        get_output(db, output_id)  # 404 if the image does not exist
        if _membership(db, gallery.id, output_id) is not None:
            skipped += 1
            continue
        db.add(GalleryImage(gallery_id=gallery.id, job_output_id=output_id))
        added += 1
    db.commit()
    return added, skipped


def remove_image(db: Session, gallery_id: int, output_id: int) -> None:
    """Remove one image from one gallery. The image itself is untouched."""
    gallery = get_gallery(db, gallery_id)
    deleted = (
        db.execute(
            delete(GalleryImage).where(
                GalleryImage.gallery_id == gallery.id,
                GalleryImage.job_output_id == output_id,
            )
        )
        .rowcount
    )
    db.commit()
    if not deleted:
        raise GalleryError(404, "Image is not in this gallery")


def galleries_for_output(db: Session, output_id: int) -> list[Gallery]:
    get_output(db, output_id)
    return list(
        db.scalars(
            select(Gallery)
            .join(GalleryImage, GalleryImage.gallery_id == Gallery.id)
            .where(GalleryImage.job_output_id == output_id)
            .order_by(Gallery.name.asc())
        )
    )


def sync_output_galleries(db: Session, output_id: int, gallery_ids: list[int]) -> None:
    """Set the exact set of galleries an image belongs to.

    Adds the image to galleries it is missing from and removes it from the
    rest. Invalid/unknown gallery ids are ignored. Idempotent.
    """
    get_output(db, output_id)
    valid = {
        g.id
        for g in db.scalars(select(Gallery).where(Gallery.id.in_(gallery_ids)))
    }
    current_ids = {
        row.gallery_id
        for row in db.scalars(
            select(GalleryImage).where(GalleryImage.job_output_id == output_id)
        )
    }
    for gid in current_ids - valid:
        db.execute(
            delete(GalleryImage).where(
                GalleryImage.gallery_id == gid,
                GalleryImage.job_output_id == output_id,
            )
        )
    for gid in valid - current_ids:
        db.add(GalleryImage(gallery_id=gid, job_output_id=output_id))
    db.commit()


def cleanup_output_memberships(db: Session, output_id: int) -> int:
    """Remove all gallery memberships for a deleted output.

    The DB foreign keys already cascade this; this is an explicit, pragma-
    independent guarantee that deleting an image never leaves dangling
    gallery rows.
    """
    deleted = (
        db.execute(
            delete(GalleryImage).where(GalleryImage.job_output_id == output_id)
        )
        .rowcount
    )
    return int(deleted or 0)


def resolve_original(db: Session, job: Job) -> dict | None:
    """Resolve a job's source image for before/after comparison.

    Image modification sources come from ``source_image``; character swap from
    ``scene_image``; general generation has none. Returns ``None`` (graceful
    degrade to generated-only) when there is no source or it no longer exists.
    """
    source_key = {
        "image_modification": "source_image",
        "character_swap": "scene_image",
    }.get(job.category)
    if not source_key:
        return None
    try:
        inputs = json.loads(job.inputs_json or "{}")
    except json.JSONDecodeError:
        return None
    ref = inputs.get(source_key)
    if not isinstance(ref, dict):
        return None
    file_id = ref.get("asset_file_id")
    if not file_id:
        return None
    asset_file = db.get(AssetFile, int(file_id))
    if asset_file is None:
        return None
    return {
        "url": f"/media/assets/{asset_file.id}",
        "width": asset_file.width,
        "height": asset_file.height,
        "alt": asset_file.display_name,
    }
