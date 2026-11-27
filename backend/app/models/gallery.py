from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base
from app.models.setting import utcnow


class Gallery(Base):
    """An explicit, user-named collection of generated images.

    Membership lives in :class:`GalleryImage` (a many-to-many relationship to
    ``JobOutput``). A gallery is purely organizational: deleting it removes
    only the gallery and its membership rows, never the underlying images,
    source assets, outputs, or history.
    """

    __tablename__ = "galleries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    images: Mapped[list["GalleryImage"]] = relationship(
        back_populates="gallery", cascade="all, delete-orphan"
    )


class GalleryImage(Base):
    """Membership of a generated image (``JobOutput``) in a :class:`Gallery`.

    A single image may belong to many galleries (one row per gallery). The row
    references the output by id and never stores or copies image bytes. Both
    foreign keys cascade, so removing a gallery or deleting an output cleans up
    its memberships automatically.
    """

    __tablename__ = "gallery_images"
    __table_args__ = (
        UniqueConstraint("gallery_id", "job_output_id", name="uq_gallery_output"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gallery_id: Mapped[int] = mapped_column(
        ForeignKey("galleries.id", ondelete="CASCADE"), index=True
    )
    job_output_id: Mapped[int] = mapped_column(
        ForeignKey("job_outputs.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    gallery: Mapped[Gallery] = relationship(back_populates="images")
