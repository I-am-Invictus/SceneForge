#!/usr/bin/env bash
# SceneForge Phase 1 - one-time host setup for thor128-2
# Run as nmc220 on thor128-2. Prompts for sudo password once per sudo call.
# Idempotent: safe to re-run.
set -euo pipefail

echo "==> 1/5 Creating dedicated service account 'sceneforge'"
if ! id sceneforge &>/dev/null; then
  sudo useradd --system --home-dir /var/lib/sceneforge --shell /usr/sbin/nologin sceneforge
fi

echo "==> 2/5 Creating directory structure"
sudo mkdir -p /opt/sceneforge/{frontend,backend,workflows,scripts,docs}
sudo mkdir -p /var/lib/sceneforge/{database,thumbnails,generated,temporary,backups,logs}
sudo mkdir -p /var/lib/sceneforge/assets/{characters,scenes}
sudo chown -R nmc220:nmc220 /opt/sceneforge
sudo chown -R sceneforge:sceneforge /var/lib/sceneforge
sudo chmod 750 /var/lib/sceneforge

echo "==> 3/5 Installing Node.js 22 LTS (frontend build)"
if command -v node &>/dev/null; then
  echo "    node already present: $(node --version)"
else
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
node --version

echo "==> 4/5 Writing /opt/sceneforge/.env (if absent)"
if [ ! -f /opt/sceneforge/.env ]; then
  sudo tee /opt/sceneforge/.env >/dev/null <<'EOF'
SCENEFORGE_HOST=0.0.0.0
SCENEFORGE_PORT=8080

COMFYUI_HTTP_URL=http://127.0.0.1:8188
COMFYUI_WS_URL=ws://127.0.0.1:8188/ws

SCENEFORGE_DATA_DIR=/var/lib/sceneforge
EOF
  sudo chown sceneforge:sceneforge /opt/sceneforge/.env
  sudo chmod 600 /opt/sceneforge/.env
else
  echo "    /opt/sceneforge/.env already exists, leaving it untouched"
fi

echo "==> 5/5 Installing systemd unit (NOT enabled/started yet)"
sudo tee /etc/systemd/system/sceneforge.service >/dev/null <<'EOF'
[Unit]
Description=SceneForge Studio
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sceneforge
Group=sceneforge
WorkingDirectory=/opt/sceneforge/backend
EnvironmentFile=/opt/sceneforge/.env
ExecStart=/opt/sceneforge/backend/.venv/bin/python -m uvicorn app.main:app --host ${SCENEFORGE_HOST} --port ${SCENEFORGE_PORT}
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

echo
echo "Setup complete."
id sceneforge
ls -la /opt/sceneforge
ls -la /var/lib/sceneforge
