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

[ "${1:-}" = "--reset" ] && rm -f .env .cache/identity.json .cache/discovery_secret

if [ ! -f .env ]; then
  echo "First-time setup - the presenter gives you the first three values."
  read -r -p "Server URL (e.g. https://name.trycloudflare.com/api): " SERVER_URL
  echo "Device ID and token: type them if the presenter gave them, or just press Enter to let the dashboard find this display."
  read -r -p "Device ID (e.g. DEV-001, or Enter to be found automatically): " DEVICE_ID
  REGISTRATION_TOKEN=""
  if [ -n "${DEVICE_ID// }" ]; then
    read -r -p "Registration token (e.g. A1B2-C3D4-E5F6): " REGISTRATION_TOKEN
  fi
  SERVER_URL=$(echo "$SERVER_URL" | tr -d '[:space:]')
  DEVICE_ID=$(echo "$DEVICE_ID" | tr -d '[:space:]')
  REGISTRATION_TOKEN=$(echo "$REGISTRATION_TOKEN" | tr -d '[:space:]')
  echo
  echo "Laptops have no GPS, so this display uses a simulated position."
  echo "In the demo one display drives a route and the others stay put. Ask the presenter which this one is."
  read -r -p "Should this display MOVE along a route? [y/N]: " MOVES
  if [[ "$MOVES" =~ ^[Yy] ]]; then
    GPS_LINES=$'GPS_MODE=sim\nROUTE=chandigarh,delhi,jaipur,mumbai\nROUTE_STEPS=8\nROUTE_DWELL=6'
  else
    read -r -p "Which place is it in? (chandigarh, delhi, jaipur, mumbai, ahmedabad) [delhi]: " PLACE
    PLACE=$(echo "${PLACE:-delhi}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    GPS_LINES=$'GPS_MODE=fixed\nPLACE='"$PLACE"
  fi
  {
    echo "SERVER_URL=$SERVER_URL"
    [ -n "$DEVICE_ID" ] && echo "DEVICE_ID=$DEVICE_ID"
    [ -n "$REGISTRATION_TOKEN" ] && echo "REGISTRATION_TOKEN=$REGISTRATION_TOKEN"
    echo "DISPLAY_PORT=8101"
    echo "OPEN_BROWSER=1"
    echo "KIOSK=0"
    echo "DEMO_CONTROLS=1"   # the demo panel (press d); remove this line on a real display
    echo "$GPS_LINES"
  } > .env
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
