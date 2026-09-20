#!/usr/bin/env bash
# Display-laptop launcher (macOS / Linux). First run asks 3 questions and saves them to .env.
#   ./start.sh            start the display agent
#   ./start.sh --reset    forget the saved answers and ask again
set -euo pipefail
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this again." >&2
  exit 1
fi

[ "${1:-}" = "--reset" ] && rm -f .env

if [ ! -f .env ]; then
  echo "First-time setup - the presenter gives you these three values."
  read -r -p "Server URL (e.g. https://name.trycloudflare.com/api): " SERVER_URL
  read -r -p "Device ID (e.g. DEV-001): " DEVICE_ID
  read -r -p "Registration token (e.g. A1B2-C3D4-E5F6): " REGISTRATION_TOKEN
  SERVER_URL=$(echo "$SERVER_URL" | tr -d '[:space:]')
  DEVICE_ID=$(echo "$DEVICE_ID" | tr -d '[:space:]')
  REGISTRATION_TOKEN=$(echo "$REGISTRATION_TOKEN" | tr -d '[:space:]')
  cat > .env <<ENVEOF
SERVER_URL=$SERVER_URL
DEVICE_ID=$DEVICE_ID
REGISTRATION_TOKEN=$REGISTRATION_TOKEN
DISPLAY_PORT=8101
OPEN_BROWSER=1
KIOSK=0
GPS_MODE=sim
ROUTE=chandigarh,delhi,jaipur,mumbai
ROUTE_STEPS=8
ROUTE_DWELL=6
ENVEOF
  echo "Saved to .env (run ./start.sh --reset to change it)."
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating a private Python environment (one time)..."
  "$PY" -m venv .venv
fi
echo "Checking dependencies..."
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt

echo "Starting the display agent. Press Ctrl+C to stop."
exec .venv/bin/python agent.py
