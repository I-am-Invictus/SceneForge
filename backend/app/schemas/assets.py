from datetime import datetime

from pydantic import BaseModel


class FolderOut(BaseModel):
    id: int
    kind: str
    name: str
    parent_id: int | None


class FolderCreate(BaseModel):
    name: str
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str


class AssetFileOut(BaseModel):
    id: int
    display_name: str
    width: int
    height: int
    size_bytes: int
    mime: str
    is_default: bool
    sort_order: int
    created_at: datetime
    thumbnail_url: str
    original_url: str


class AssetOut(BaseModel):
    id: int
    kind: str
    name: str
    folder_id: int | None
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
    files: list[AssetFileOut] = []
    thumbnail_url: str | None = None
    reference_count: int = 0


class AssetPatch(BaseModel):
    name: str | None = None
    is_favorite: bool | None = None


class AssetMove(BaseModel):
    folder_id: int | None = None
