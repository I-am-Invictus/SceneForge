"""Reusable application-data reset.

This is the single implementation behind both the developer UI
(``POST /api/developer/reset``) and the ``scripts/reset_image_data.py`` CLI.

A reset returns SceneForge to an empty first-run state: it clears the
image-bearing database rows and the image files under managed storage, while
preserving the database file, schema, workflow registry/configs/versions,
application settings, folders, and everything outside ``/var/lib/sceneforge``
(ComfyUI models, custom nodes, etc.).

The service is self-contained (stdlib only) and operates on an explicit data
directory, so it runs with or without the web app. It is guarded by a lock so a
reset and a data-writing request can never interleave, and it returns a
structured report instead of raising.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Image-only storage subdirectories (safe to wipe entirely).
IMAGE_SUBDIRS = ("assets", "thumbnails", "generated", "temporary")
# Image-bearing tables, in foreign-key-safe (children-first) order.
TABLES = (
    "gallery_images",
    "galleries",
    "job_outputs",
    "jobs",
    "asset_files",
    "assets",
)
# Tables deliberately left untouched (non-image application data).
PRESERVED_TABLES = ("folders", "settings", "workflows")

_REF_COLUMNS = (
    ("asset_files", "stored_path"),
    ("asset_files", "thumbnail_path"),
    ("job_outputs", "stored_path"),
    ("job_outputs", "thumbnail_path"),
)


class ResetInProgress(RuntimeError):
    """Raised when a data-writing request races a reset in flight."""


# A single lock serialises the reset against data-writing requests. The reset
# holds it for its whole duration; writers take it non-blocking and refuse.
_RESET_LOCK = threading.Lock()


@contextmanager
def reset_exclusive():
    """Held for the entire reset; blocks new writers for that window."""
    _RESET_LOCK.acquire()
    try:
        yield
    finally:
        _RESET_LOCK.release()


@contextmanager
def writer_guard():
    """Used by create/upload/generate paths; refuses while a reset runs."""
    if not _RESET_LOCK.acquire(blocking=False):
        raise ResetInProgress(
            "Application data reset is in progress; please retry in a moment."
        )
    try:
        yield
    finally:
        _RESET_LOCK.release()


def reset_in_progress() -> bool:
    """Non-blocking peek (used by background tasks that must not recreate
    data mid-reset, e.g. the job monitor storing outputs)."""
    if _RESET_LOCK.acquire(blocking=False):
        _RESET_LOCK.release()
        return False
    return True


@dataclass
class ResetReport:
    ok: bool
    before: dict[str, int] = field(default_factory=dict)
    after: dict[str, int] = field(default_factory=dict)
    files_removed: int = 0
    orphans_removed: int = 0
    backup_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "before": self.before,
            "after": self.after,
            "files_removed": self.files_removed,
            "orphans_removed": self.orphans_removed,
            "backup_path": self.backup_path,
            "error": self.error,
        }


def _db_path(base: Path) -> Path:
    return base / "database" / "sceneforge.db"


def _counts(db: Path, tables: tuple[str, ...]) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        out = {}
        for t in tables:
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({t})")}
            out[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if cols else 0
        return out
    finally:
        con.close()


def _referenced_paths(db: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    refs: set[str] = set()
    try:
        cur = con.cursor()
        for t, c in _REF_COLUMNS:
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({t})")}
            if c not in cols:
                continue
            for (v,) in cur.execute(f"SELECT {c} FROM {t} WHERE {c} IS NOT NULL"):
                refs.add(v)
        return refs
    finally:
        con.close()


def _disk_image_files(base: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sub in IMAGE_SUBDIRS:
        d = base / sub
        files = []
        if d.exists():
            for root, _dirs, names in os.walk(d):
                for name in names:
                    p = Path(root) / name
                    files.append(str(p.relative_to(base)))
        out[sub] = sorted(files)
    return out


def snapshot(base: Path) -> dict:
    """Read-only summary of current image data (used for dry runs/reporting)."""
    db = _db_path(base)
    if not db.is_file():
        return {"ok": False, "error": f"database not found: {db}"}
    before = _counts(db, TABLES)
    refs = _referenced_paths(db)
    disk = _disk_image_files(base)
    all_disk = {p for files in disk.values() for p in files}
    return {
        "ok": True,
        "before": before,
        "disk": {sub: len(files) for sub, files in disk.items()},
        "orphans": len(all_disk - refs),
        "broken_refs": len(refs - all_disk),
    }


def _backup(db: Path, base: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = base / "backups" / f"sceneforge.db.{ts}.pre-reset"
    backup.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db)
    dst = sqlite3.connect(backup)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup


def reset_image_data(base: Path) -> ResetReport:
    """Return the application to an empty first-run state.

    Never raises; failures are reported via ``ResetReport.ok`` / ``.error``.
    """
    base = Path(base).expanduser().resolve()
    db = _db_path(base)
    if not db.is_file():
        return ResetReport(
            ok=False,
            error=f"database not found: {db}",
        )

    try:
        with reset_exclusive():
            before = _counts(db, TABLES)
            refs = _referenced_paths(db)
            disk = _disk_image_files(base)
            all_disk = {p for files in disk.values() for p in files}
            orphans = len(all_disk - refs)
            files_before = len(all_disk)

            # 1. Back up the database before touching anything.
            backup_path = _backup(db, base)

            # 2. Clear image-bearing rows in one transaction (DB clean first,
            #    so no dangling references can be left if file removal stalls).
            con = sqlite3.connect(db)
            try:
                cur = con.cursor()
                for t in TABLES:
                    cur.execute(f"DELETE FROM {t}")
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()

            # 3. Remove image files (catches orphans and stale files too).
            for sub in IMAGE_SUBDIRS:
                d = base / sub
                if d.exists():
                    shutil.rmtree(d)
                d.mkdir(parents=True, exist_ok=True)

            after = _counts(db, TABLES)
            leftover = sum(len(v) for v in _disk_image_files(base).values())
            ok = all(after[t] == 0 for t in TABLES) and leftover == 0

            report = ResetReport(
                ok=ok,
                before=before,
                after=after,
                files_removed=max(0, files_before - leftover),
                orphans_removed=orphans,
                backup_path=str(backup_path),
                error=None if ok else "reset did not reach a clean state",
            )
            logger.info("Reset complete: %s", report.to_dict())
            return report
    except Exception as exc:  # noqa: BLE001 - report, don't raise
        logger.exception("Reset failed")
        return ResetReport(
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
