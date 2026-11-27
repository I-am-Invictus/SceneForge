import logging
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Job, JobOutput
from app.schemas import JobError

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
