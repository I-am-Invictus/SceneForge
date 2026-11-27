#!/usr/bin/env python3
"""Reset SceneForge user image data to a clean state.

Deletes every image file under the managed storage tree (assets/, thumbnails/,
generated/, temporary/) and the image-bearing database rows (assets,
asset_files, jobs, job_outputs, galleries, gallery_images). Non-image data is
preserved: folders, settings, the workflow registry/configs, and ComfyUI
models. Orphaned and stale image files are removed along with the rest.

The database file is hot-backed-up before any change. By default the script
runs a dry-run and prints a report; pass --yes to apply. Run with the service
stopped (the DB should not be written to concurrently during the reset).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def find_base(explicit: str | None) -> Path:
    if explicit:
        base = Path(explicit).expanduser().resolve()
    else:
        env = os.environ.get("SCENEFORGE_DATA_DIR")
        if not env:
            sys.exit("ERROR: pass --base or set SCENEFORGE_DATA_DIR")
        base = Path(env).expanduser().resolve()
    if not (base / "database" / "sceneforge.db").is_file():
        sys.exit(f"ERROR: {base}/database/sceneforge.db not found; refusing to run")
    return base


def disk_files(base: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sub in IMAGE_SUBDIRS:
        d = base / sub
        files = []
        if d.exists():
            for root, _, names in os.walk(d):
                for name in names:
                    p = os.path.join(root, name)
                    files.append(os.path.relpath(p, base))
        out[sub] = sorted(files)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset SceneForge image data.")
    ap.add_argument("--base", help="SceneForge data dir (default $SCENEFORGE_DATA_DIR)")
    ap.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    base = find_base(args.base)
    db = base / "database" / "sceneforge.db"

    con = sqlite3.connect(db)
    cur = con.cursor()
    before = {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    refs: set[str] = set()
    for t, c in (
        ("asset_files", "stored_path"),
        ("asset_files", "thumbnail_path"),
        ("job_outputs", "stored_path"),
        ("job_outputs", "thumbnail_path"),
    ):
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({t})")}
        if c not in cols:
            continue
        for (v,) in cur.execute(f"SELECT {c} FROM {t} WHERE {c} IS NOT NULL"):
            refs.add(v)
    con.close()

    disk = disk_files(base)
    all_disk = {p for files in disk.values() for p in files}
    orphans = all_disk - refs
    broken = refs - all_disk

    print(f"SceneForge data dir: {base}")
    print(f"Mode: {'APPLY' if args.yes else 'DRY-RUN'}")
    print("\n-- Database rows (will be cleared) --")
    for t in TABLES:
        print(f"  {t:16} {before[t]}")
    print("\n-- Image files on disk (will be removed) --")
    for sub in IMAGE_SUBDIRS:
        print(f"  {sub:12} {len(disk[sub])}")
    print(f"\n  orphaned (on disk, not in DB): {len(orphans)}")
    print(f"  broken DB refs (in DB, not on disk): {len(broken)}")

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to apply the reset.")
        return

    # 1. Hot-backup the database before touching anything.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = base / "backups" / f"sceneforge.db.{ts}.pre-reset"
    backup.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(db)
    dst = sqlite3.connect(backup)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    print(f"\nBacked up database -> {backup}")

    # 2. Remove image files (catches orphans and stale files too).
    for sub in IMAGE_SUBDIRS:
        d = base / sub
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        print(f"Emptied {sub}/")

    # 3. Clear image-bearing rows in a single transaction.
    con = sqlite3.connect(db)
    cur = con.cursor()
    try:
        for t in TABLES:
            cur.execute(f"DELETE FROM {t}")
        con.commit()
    except Exception:
        con.rollback()
        raise
    after = {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    con.close()

    print("\n-- After reset --")
    for t in TABLES:
        print(f"  {t:16} {before[t]} -> {after[t]}")
    leftover = sum(len(v) for v in disk_files(base).values())
    print(f"  image files on disk: {leftover}")
    if all(after[t] == 0 for t in TABLES) and leftover == 0:
        print("\nReset complete: image data cleared, non-image data preserved.")
    else:
        print("\nWARNING: reset did not reach a clean state; inspect the report above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
