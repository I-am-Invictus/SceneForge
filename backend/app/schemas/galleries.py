from datetime import datetime

from pydantic import BaseModel, Field


class GalleryBriefOut(BaseModel):
    id: int
    name: str


class GalleryCover(BaseModel):
    thumbnail_url: str
    original_url: str
    width: int | None = None
    height: int | None = None
    label: str = ""


class GalleryOut(BaseModel):
    id: int
    name: str
    image_count: int = 0
    cover: GalleryCover | None = None
    created_at: datetime
    updated_at: datetime


class GalleryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GalleryRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GalleryOriginal(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None
    alt: str = ""


class GalleryImageOut(BaseModel):
    output_id: int
    job_client_id: str
    job_category: str
    comfyui_filename: str
    prompt: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_url: str
    original_url: str
    # Resolved source image for before/after comparison (null for general
    # generation, or when the source asset no longer exists).
    original: GalleryOriginal | None = None


class OutputGalleriesSync(BaseModel):
    gallery_ids: list[int]
