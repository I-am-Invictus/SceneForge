from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models import Gallery, GalleryImage, JobOutput
from app.schemas.galleries import (
    GalleryBriefOut,
    GalleryCreate,
    GalleryCover,
    GalleryImageOut,
    GalleryOriginal,
    GalleryOut,
    GalleryRename,
    OutputGalleriesSync,
)
from app.services import galleries as gallery_service
from app.services.galleries import GalleryError

router = APIRouter(tags=["galleries"])


def _raise(exc: GalleryError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc))


def _cover(db: Session, members: list[GalleryImage]) -> GalleryCover | None:
    if not members:
        return None
    member = max(members, key=lambda m: (m.added_at, m.id))
    out = db.get(JobOutput, member.job_output_id)
    if out is None or not out.thumbnail_path:
        return None
    job = out.job
    label = (job.prompt if job else None) or out.comfyui_filename
    return GalleryCover(
        thumbnail_url=f"/media/job-thumbnails/{out.id}",
        original_url=f"/media/job-assets/{out.id}",
        width=out.width,
        height=out.height,
        label=label,
    )


def _serialize(db: Session, gallery: Gallery) -> GalleryOut:
    members = list(gallery.images)
    return GalleryOut(
        id=gallery.id,
        name=gallery.name,
        image_count=len(members),
        cover=_cover(db, members),
        created_at=gallery.created_at,
        updated_at=gallery.updated_at,
    )


def _serialize_image(db: Session, member: GalleryImage) -> GalleryImageOut:
    out = db.get(JobOutput, member.job_output_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Image not found")
    job = out.job
    original = gallery_service.resolve_original(db, job) if job else None
    return GalleryImageOut(
        output_id=out.id,
        job_client_id=job.client_id if job else "",
        job_category=job.category if job else "",
        comfyui_filename=out.comfyui_filename,
        prompt=job.prompt if job else None,
        width=out.width,
        height=out.height,
        thumbnail_url=f"/media/job-thumbnails/{out.id}",
        original_url=f"/media/job-assets/{out.id}",
        original=GalleryOriginal(**original) if original else None,
    )


@router.get("/api/galleries", response_model=list[GalleryOut])
async def list_galleries(db: Session = Depends(get_db)):
    return [_serialize(db, g) for g in gallery_service.list_galleries(db)]


@router.get("/api/galleries/{gallery_id}", response_model=GalleryOut)
async def get_gallery(gallery_id: int, db: Session = Depends(get_db)):
    try:
        return _serialize(db, gallery_service.get_gallery(db, gallery_id))
    except GalleryError as exc:
        _raise(exc)


@router.post("/api/galleries", status_code=201, response_model=GalleryOut)
async def create_gallery(
    payload: GalleryCreate, db: Session = Depends(get_db)
):
    try:
        return _serialize(db, gallery_service.create_gallery(db, payload.name))
    except GalleryError as exc:
        _raise(exc)


@router.patch("/api/galleries/{gallery_id}", response_model=GalleryOut)
async def rename_gallery(
    gallery_id: int, payload: GalleryRename, db: Session = Depends(get_db)
):
    try:
        return _serialize(
            db, gallery_service.rename_gallery(db, gallery_id, payload.name)
        )
    except GalleryError as exc:
        _raise(exc)


@router.delete("/api/galleries/{gallery_id}", status_code=204)
async def delete_gallery(gallery_id: int, db: Session = Depends(get_db)):
    try:
        gallery_service.delete_gallery(db, gallery_id)
    except GalleryError as exc:
        _raise(exc)


@router.get(
    "/api/galleries/{gallery_id}/images", response_model=list[GalleryImageOut]
)
async def list_gallery_images(gallery_id: int, db: Session = Depends(get_db)):
    try:
        members = gallery_service.gallery_members(db, gallery_id)
    except GalleryError as exc:
        _raise(exc)
    return [_serialize_image(db, m) for m in members]


@router.delete(
    "/api/galleries/{gallery_id}/images/{output_id}", response_model=GalleryOut
)
async def remove_gallery_image(
    gallery_id: int, output_id: int, db: Session = Depends(get_db)
):
    try:
        gallery_service.remove_image(db, gallery_id, output_id)
        return _serialize(db, gallery_service.get_gallery(db, gallery_id))
    except GalleryError as exc:
        _raise(exc)


@router.get(
    "/api/job-outputs/{output_id}/galleries", response_model=list[GalleryBriefOut]
)
async def output_galleries(output_id: int, db: Session = Depends(get_db)):
    try:
        galleries = gallery_service.galleries_for_output(db, output_id)
    except GalleryError as exc:
        _raise(exc)
    return [GalleryBriefOut(id=g.id, name=g.name) for g in galleries]


@router.put(
    "/api/job-outputs/{output_id}/galleries", response_model=list[GalleryBriefOut]
)
async def sync_output_galleries(
    output_id: int,
    payload: OutputGalleriesSync,
    db: Session = Depends(get_db),
):
    try:
        gallery_service.sync_output_galleries(db, output_id, payload.gallery_ids)
        galleries = gallery_service.galleries_for_output(db, output_id)
    except GalleryError as exc:
        _raise(exc)
    return [GalleryBriefOut(id=g.id, name=g.name) for g in galleries]
