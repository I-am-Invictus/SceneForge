#!/usr/bin/env bash
# SceneForge Phase 1 - one-time host setup for thor128-2
# Run as nmc220 on thor128-2. Prompts for sudo password (cached after first use).
# Idempotent: safe to re-run.
set -euo pipefail

RUN_USER=nmc220

echo "==> 1/4 Creating directory structure"
sudo mkdir -p /opt/sceneforge/{frontend,backend,workflows,scripts,docs}
sudo mkdir -p /var/lib/sceneforge/{database,thumbnails,generated,temporary,backups,logs}
sudo mkdir -p /var/lib/sceneforge/assets/{characters,scenes}
sudo chown -R "$RUN_USER:$RUN_USER" /opt/sceneforge
sudo chown -R "$RUN_USER:$RUN_USER" /var/lib/sceneforge
sudo chmod 750 /var/lib/sceneforge

echo "==> 2/4 Installing Node.js 22 LTS (frontend build only)"
if command -v node &>/dev/null; then
  echo "    node already present: $(node --version)"
else
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
node --version

echo "==> 3/4 Writing /opt/sceneforge/.env (if absent)"
if [ ! -f /opt/sceneforge/.env ]; then
  sudo tee /opt/sceneforge/.env >/dev/null <<EOF
SCENEFORGE_HOST=0.0.0.0
SCENEFORGE_PORT=8080

COMFYUI_HTTP_URL=http://127.0.0.1:8188
COMFYUI_WS_URL=ws://127.0.0.1:8188/ws

SCENEFORGE_DATA_DIR=/var/lib/sceneforge
EOF
  sudo chown "$RUN_USER:$RUN_USER" /opt/sceneforge/.env
  sudo chmod 600 /opt/sceneforge/.env
else
  echo "    /opt/sceneforge/.env already exists, leaving it untouched"
fi

echo "==> 4/4 Installing systemd unit (NOT enabled/started yet)"
sudo tee /etc/systemd/system/sceneforge.service >/dev/null <<EOF
[Unit]
Description=SceneForge Studio
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=/opt/sceneforge/backend
EnvironmentFile=/opt/sceneforge/.env
ExecStart=/opt/sceneforge/backend/.venv/bin/python -m uvicorn app.main:app --host \${SCENEFORGE_HOST} --port \${SCENEFORGE_PORT}
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
ls -la /opt/sceneforge
ls -la /var/lib/sceneforge
