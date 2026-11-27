#!/usr/bin/env python3
"""Reset SceneForge user image data to a clean state (CLI).

Thin wrapper over the shared backend service ``app.services.reset`` (the same
implementation the developer UI uses), so there is a single reset code path.

Deletes every image file under the managed storage tree (assets/, thumbnails/,
generated/, temporary/) and the image-bearing database rows (assets,
asset_files, jobs, job_outputs, galleries, gallery_images). Non-image data is
preserved: folders, settings, the workflow registry/configs/versions, and
ComfyUI models. Orphaned and stale image files are removed along with the rest.

The database file is hot-backed-up before any change. By default this runs a
dry-run and prints a report; pass --yes to apply.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make the backend importable regardless of the current working directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.reset import IMAGE_SUBDIRS, TABLES, reset_image_data, snapshot  # noqa: E402


def find_base(explicit: str | None) -> Path:
    if explicit:
        base = Path(explicit).expanduser().resolve()
    else:
        env = os.environ.get("SCENEFORGE_DATA_DIR")
        if not env:
            sys.exit("ERROR: pass --base or set SCENEFORGE_DATA_DIR")
        base = Path(env).expanduser().resolve()
    return base


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset SceneForge image data.")
    ap.add_argument("--base", help="SceneForge data dir (default $SCENEFORGE_DATA_DIR)")
    ap.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    base = find_base(args.base)

    snap = snapshot(base)
    if not snap["ok"]:
        sys.exit(f"ERROR: {snap['error']}")

    print(f"SceneForge data dir: {base}")
    print(f"Mode: {'APPLY' if args.yes else 'DRY-RUN'}")
    print("\n-- Database rows (will be cleared) --")
    for t in TABLES:
        print(f"  {t:16} {snap['before'][t]}")
    print("\n-- Image files on disk (will be removed) --")
    for sub in IMAGE_SUBDIRS:
        print(f"  {sub:12} {snap['disk'][sub]}")
    print(f"\n  orphaned (on disk, not in DB): {snap['orphans']}")
    print(f"  broken DB refs (in DB, not on disk): {snap['broken_refs']}")

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to apply the reset.")
        return

    report = reset_image_data(base)
    print("\n-- After reset --")
    for t in TABLES:
        print(f"  {t:16} {report.before[t]} -> {report.after[t]}")
    print(f"  image files removed: {report.files_removed}")
    print(f"  orphans removed:     {report.orphans_removed}")
    if report.backup_path:
        print(f"  database backup:     {report.backup_path}")
    if report.ok:
        print("\nReset complete: image data cleared, non-image data preserved.")
    else:
        print(f"\nWARNING: reset failed or incomplete: {report.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
