#!/usr/bin/env bash
# Build the ESP32 firmware and flash it over USB, from the Pi.
#   ./scripts/flash.sh            build + flash
#   ./scripts/flash.sh monitor    raw serial monitor (Ctrl+C to quit)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SMARTBIN_PORT:-/dev/smartbin}"
PIO="$REPO/.venv/bin/pio"

[ -e "$PORT" ] || { echo "No ESP32 at $PORT. Is the USB cable a data cable? Try: ls -l /dev/ttyUSB* /dev/ttyACM*"; exit 1; }

# The hub keeps the port open, so stop it while we use the port.
was_running=0
if systemctl is-active --quiet smartbin-hub; then
  was_running=1
  sudo systemctl stop smartbin-hub
fi
restart() { if [ "$was_running" = 1 ]; then sudo systemctl start smartbin-hub && echo "hub restarted"; fi; }
trap restart EXIT

if [ "${1:-}" = "monitor" ]; then
  "$PIO" device monitor -d "$REPO/firmware" -p "$PORT"
else
  "$PIO" run -d "$REPO/firmware" -t upload --upload-port "$PORT"
  echo "Flashed. If upload kept failing at 'Connecting...', hold the BOOT button while it connects."
fi
