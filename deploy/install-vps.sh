#!/usr/bin/env bash
# Ubuntu / Debian - installe le bot et le fait tourner 24/7 via systemd.
# Usage : bash deploy/install-vps.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE=discord-music

echo "[1/4] paquets systeme"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip ffmpeg libopus0

echo "[2/4] environnement python"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[3/4] service systemd"
sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<EOF
[Unit]
Description=Discord music selfbot (24/7)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -u bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"

echo "[4/4] etat"
sleep 4
sudo systemctl --no-pager --lines=20 status "$SERVICE" || true
