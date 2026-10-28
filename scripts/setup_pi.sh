#!/usr/bin/env bash
# One-time setup on the Raspberry Pi 5. Run from the repo:  ./scripts/setup_pi.sh
# Safe to run again (e.g. after a git pull).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
cd "$REPO"

echo "==> 1/6 System packages"
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip sqlite3 curl

echo "==> 2/6 Serial port access (dialout group)"
sudo usermod -aG dialout "$USER_NAME"

echo "==> 3/6 Python venv with pyserial + PlatformIO"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r hub/requirements.txt platformio

echo "==> 4/6 udev rule: ESP32 -> /dev/smartbin"
sudo cp scripts/99-smartbin.rules /etc/udev/rules.d/99-smartbin.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty

echo "==> 5/6 Hub settings + systemd service"
[ -f hub/hub.env ] || cp hub/hub.env.example hub/hub.env
mkdir -p data
sed -e "s|__USER__|$USER_NAME|g" -e "s|__REPO__|$REPO|g" scripts/smartbin-hub.service \
  | sudo tee /etc/systemd/system/smartbin-hub.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable smartbin-hub
sudo systemctl restart smartbin-hub

echo "==> 6/6 binctl command"
sudo ln -sf "$REPO/scripts/binctl" /usr/local/bin/binctl
chmod +x scripts/*.sh scripts/binctl

echo
sleep 1
if [ -e /dev/smartbin ]; then
  echo "ESP32 found: /dev/smartbin -> $(readlink -f /dev/smartbin)"
else
  echo "No ESP32 found yet. Plug it in, then check:  ls -l /dev/smartbin"
fi
IP="$(hostname -I | awk '{print $1}')"
echo "Next: ./scripts/flash.sh   (builds + flashes the firmware; first build downloads ~300 MB)"
echo "Dashboard: http://$IP:8080   or   http://$(hostname).local:8080"
echo "If 'groups' does not list dialout yet, log out and SSH back in."
