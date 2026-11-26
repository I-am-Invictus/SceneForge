from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Folder


class FolderError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def list_folders(db: Session, kind: str) -> list[Folder]:
    return list(db.scalars(select(Folder).where(Folder.kind == kind)))


def get_folder(db: Session, kind: str, folder_id: int) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.kind != kind:
        raise FolderError(404, "Folder not found")
    return folder


def create_folder(db: Session, kind: str, name: str, parent_id: int | None) -> Folder:
    name = name.strip()
    if not name:
        raise FolderError(422, "Folder name is required")
    if len(name) > 200:
        raise FolderError(422, "Folder name too long")
    parent = None
    if parent_id is not None:
        parent = get_folder(db, kind, parent_id)
    folder = Folder(kind=kind, name=name, parent_id=parent.id if parent else None)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def rename_folder(db: Session, kind: str, folder_id: int, name: str) -> Folder:
    name = name.strip()
    if not name:
        raise FolderError(422, "Folder name is required")
    if len(name) > 200:
        raise FolderError(422, "Folder name too long")
    folder = get_folder(db, kind, folder_id)
    folder.name = name
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, kind: str, folder_id: int) -> None:
    folder = get_folder(db, kind, folder_id)
    child_assets = db.scalar(select(Asset.id).where(Asset.folder_id == folder.id).limit(1))
    child_folders = db.scalar(
        select(Folder.id).where(Folder.parent_id == folder.id).limit(1)
    )
    if child_assets is not None or child_folders is not None:
        raise FolderError(409, "Folder is not empty")
    db.delete(folder)
    db.commit()
