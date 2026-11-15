#!/data/data/com.termux/files/usr/bin/bash
# Termux (Android) - installe le bot et le garde actif en arriere-plan.
# Usage : bash deploy/termux-setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

pkg update -y
pkg install -y python ffmpeg libopus termux-api || pkg install -y python ffmpeg

pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

termux-wake-lock
cd "$APP_DIR"
nohup python -u bot.py >> bot.log 2>&1 &
echo "PID $! - logs : $APP_DIR/bot.log"
sleep 6
tail -n 15 bot.log
