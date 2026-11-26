#!/usr/bin/env bash
# Deploy SceneForge from ~/code/SceneForge to /opt/sceneforge.
# Run on thor128-2 as nmc220. Requires a clean, committed working tree.
set -euo pipefail

SRC="$HOME/code/SceneForge"
DEST=/opt/sceneforge

if [ "$(hostname)" != "thor128-2" ]; then
  echo "Refusing to deploy: must run on thor128-2 (hostname: $(hostname))" >&2
  exit 1
fi

if [ ! -d "$SRC/.git" ]; then
  echo "No repository at $SRC" >&2
  exit 1
fi

if ! git -C "$SRC" diff-index --quiet HEAD --; then
  echo "Working tree is dirty; commit or stash changes first." >&2
  exit 1
fi

rsync -a --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  "$SRC/" "$DEST/"

echo "==> Python environment"
python3 -m venv "$DEST/backend/.venv"
"$DEST/backend/.venv/bin/pip" install --quiet --upgrade pip
"$DEST/backend/.venv/bin/pip" install --quiet -r "$DEST/requirements.txt"

echo "==> Frontend production build"
(cd "$DEST/frontend" && npm install --no-audit --no-fund && npm run build)

echo "Deploy complete: $DEST"
