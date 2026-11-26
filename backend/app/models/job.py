from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base
from app.models.setting import utcnow

JOB_STATUSES = ("queued", "running", "completed", "failed", "interrupted")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    comfyui_prompt_id: Mapped[str | None] = mapped_column(String(64), index=True)
    workflow_id: Mapped[str] = mapped_column(String(100), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1)
    workflow_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    prompt: Mapped[str | None] = mapped_column(Text)
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    outputs: Mapped[list["JobOutput"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobOutput(Base):
    __tablename__ = "job_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(32))
    comfyui_filename: Mapped[str] = mapped_column(String(512))
    subfolder: Mapped[str] = mapped_column(String(512), default="")
    source_type: Mapped[str] = mapped_column(String(16), default="output")
    stored_path: Mapped[str | None] = mapped_column(String(512))
    thumbnail_path: Mapped[str | None] = mapped_column(String(512))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    job: Mapped[Job] = relationship(back_populates="outputs")
