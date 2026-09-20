#!/usr/bin/env bash
# Public HTTPS URL for the dashboard + device API, so display laptops on any network can connect.
#
#   ./scripts/tunnel.sh start [auto|ngrok|cloudflare|pinggy]   default: auto
#   ./scripts/tunnel.sh url                                    print the current URLs again
#   ./scripts/tunnel.sh which                                  show which provider `auto` would pick
#   ./scripts/tunnel.sh stop
#
# ngrok      Docker container. Needs a free account: put NGROK_AUTHTOKEN (and optionally a free static
#            NGROK_DOMAIN) in .env. With a static domain the URL never changes, so display laptops are set up once.
# cloudflare Docker container, no account. Needs outbound port 7844, which many office/venue networks block.
# pinggy     SSH over port 443, no account, no install. Free tunnels last 60 minutes, then the URL changes.
#
# auto = ngrok if NGROK_AUTHTOKEN is set, else cloudflare if port 7844 is reachable, else pinggy.
# The stack itself is started separately (docker compose up). Environment overrides:
#   FRONTEND_PORT      host port of the dashboard (default: from .env, else 3000)
#   COMPOSE_ARGS       extra `docker compose` arguments, e.g. "-p myproject"
#   TUNNEL_STATE_DIR   where pid/log/mode files live (default: .tunnel)
set -euo pipefail
cd "$(dirname "$0")/.."

STATE="${TUNNEL_STATE_DIR:-.tunnel}"
mkdir -p "$STATE"
dc() { docker compose ${COMPOSE_ARGS:-} "$@"; }

# value from the environment, else from .env (last occurrence wins)
setting() {
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f .env ]; then
    v=$(grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed 's/[[:space:]]#.*$//' | tr -d ' \r"'"'" || true)
  fi
  printf '%s' "$v"
}
PORT="$(setting FRONTEND_PORT)"; PORT="${PORT:-3000}"

strip_ansi() { perl -pe 's/\e\[[0-9;]*[A-Za-z]//g'; }

show() {
  echo
  echo "  Dashboard (open in your browser) : $1"
  echo "  Server URL for display laptops   : $1/api"
  echo
}

# Waits until "$1" (a command printing a URL) yields one; prints it. $2 = attempts (2 s apart).
wait_for_url() {
  local url=""
  for _ in $(seq 1 "$2"); do
    url=$("$1" || true)
    [ -n "$url" ] && break
    sleep 2
  done
  printf '%s' "$url"
}

check_health() {  # best-effort: confirm the public URL really reaches the backend
  for _ in $(seq 1 10); do
    curl -fsS -m 10 -H 'ngrok-skip-browser-warning: 1' "$1/api/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

# ---------------------------------------------------------------- pinggy
pinggy_url() { strip_ansi < "$STATE/pinggy.log" 2>/dev/null | grep -Eo 'https://[A-Za-z0-9.-]+\.free\.pinggy\.net' | tail -1 || true; }

stop_pinggy() {
  [ -f "$STATE/pinggy.pid" ] && kill "$(cat "$STATE/pinggy.pid")" 2>/dev/null || true
  pkill -f "R0:localhost:$PORT free.pinggy.io" 2>/dev/null || true
  rm -f "$STATE/pinggy.pid"
}

start_pinggy() {
  command -v ssh >/dev/null || { echo "ssh is required for the pinggy tunnel." >&2; exit 1; }
  stop_pinggy
  : > "$STATE/pinggy.log"
  # Reconnects automatically when the 60-minute session ends (the URL changes: run `url` again).
  nohup bash -c "while true; do ssh -p 443 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -R0:localhost:$PORT free.pinggy.io; sleep 3; done" \
      >> "$STATE/pinggy.log" 2>&1 &
  echo $! > "$STATE/pinggy.pid"
  echo pinggy > "$STATE/mode"
  echo "Starting Pinggy tunnel to localhost:$PORT ..."
  local url; url=$(wait_for_url pinggy_url 30)
  [ -n "$url" ] || { echo "Could not get a Pinggy URL - see $STATE/pinggy.log" >&2; exit 1; }
  check_health "$url" || true
  show "$url"
  echo "  Notes: free Pinggy tunnels expire after 60 minutes (the URL then changes: './scripts/tunnel.sh url')."
  echo "         Browsers see a one-time 'Enter site' notice on the dashboard; display agents are not affected."
  echo
}

# ---------------------------------------------------------------- cloudflare
cloudflare_url() {
  local logs; logs=$(dc --profile tunnel logs tunnel 2>/dev/null || true)
  # the URL is announced a few seconds before the connection is really up
  if echo "$logs" | grep -q "Registered tunnel connection"; then
    echo "$logs" | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true
  fi
}

start_cloudflare() {
  echo cloudflare > "$STATE/mode"
  dc --profile tunnel up -d --no-deps tunnel
  local url; url=$(wait_for_url cloudflare_url 30)
  if [ -z "$url" ]; then
    echo "Cloudflare tunnel is not connected." >&2
    dc --profile tunnel logs tunnel 2>/dev/null | grep -q 7844 &&
      echo "This network blocks outbound port 7844 (Cloudflare's tunnel port). Try:  ./scripts/tunnel.sh start pinggy" >&2
    exit 1
  fi
  show "$url"
}

# ---------------------------------------------------------------- ngrok
ngrok_url() {
  dc --profile ngrok logs ngrok 2>/dev/null | grep -Eo 'url=https://[^ ]+' | tail -1 | cut -d= -f2- || true
}

start_ngrok() {
  [ -n "$(setting NGROK_AUTHTOKEN)" ] || {
    echo "NGROK_AUTHTOKEN is not set." >&2
    echo "  1. Create a free account at https://dashboard.ngrok.com/signup and copy your authtoken." >&2
    echo "  2. Add it to .env:  NGROK_AUTHTOKEN=...   (optional: NGROK_DOMAIN=your-name.ngrok-free.app for a fixed URL)" >&2
    exit 1
  }
  command -v docker >/dev/null || { echo "docker is required for the ngrok tunnel." >&2; exit 1; }
  echo ngrok > "$STATE/mode"
  dc --profile ngrok up -d --no-deps ngrok
  local url; url=$(wait_for_url ngrok_url 20)
  if [ -z "$url" ]; then
    local code; code=$(dc --profile ngrok logs ngrok 2>/dev/null | grep -Eo 'ERR_NGROK_[0-9]+' | head -1 || true)
    echo "ngrok did not start${code:+ ($code)}." >&2
    case "$code" in
      ERR_NGROK_105|ERR_NGROK_106|ERR_NGROK_107|ERR_NGROK_4018)
        echo "  The authtoken was rejected. Copy it again from https://dashboard.ngrok.com/get-started/your-authtoken" >&2 ;;
      ERR_NGROK_314) echo "  NGROK_DOMAIN is not a domain on your account: https://dashboard.ngrok.com/domains" >&2 ;;
    esac
    echo "  Details: docker compose --profile ngrok logs ngrok" >&2
    dc --profile ngrok stop ngrok >/dev/null 2>&1 || true
    exit 1
  fi
  check_health "$url" || true
  show "$url"
  if [ -z "$(setting NGROK_DOMAIN)" ]; then
    echo "  Note: no NGROK_DOMAIN set, so this URL changes every time the tunnel restarts."
    echo "        Claim a free static domain at https://dashboard.ngrok.com/domains and add NGROK_DOMAIN=<it> to .env."
  else
    echo "  Fixed domain: display laptops keep working across restarts, no reconfiguration needed."
  fi
  echo "  Browsers see a one-time ngrok notice on the dashboard; display agents are not affected."
  echo
}

# ---------------------------------------------------------------- dispatch
# True if a TCP connection to $1:$2 succeeds within $3 seconds. `nc` alone can hang for a minute on
# silently dropped ports (macOS ignores its connect timeout), so a watchdog kills it. (bash's /dev/tcp is
# no alternative: it stalls on IPv6-first hosts and reports open ports as closed.)
tcp_open() {
  command -v nc >/dev/null || return 1
  nc -z "$1" "$2" >/dev/null 2>&1 &
  local pid=$!
  for _ in $(seq 1 $(( $3 * 10 ))); do
    kill -0 "$pid" 2>/dev/null || { wait "$pid" 2>/dev/null && return 0 || return 1; }
    sleep 0.1
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  return 1
}

choose_kind() {
  if [ -n "$(setting NGROK_AUTHTOKEN)" ] && command -v docker >/dev/null; then echo ngrok; return; fi
  if command -v docker >/dev/null && tcp_open region1.v2.argotunnel.com 7844 5; then echo cloudflare; else echo pinggy; fi
}

cmd="${1:-start}"; kind="${2:-auto}"
case "$cmd" in
  start)
    if [ "$kind" = auto ]; then kind=$(choose_kind); echo "Network check: using $kind"; fi
    case "$kind" in
      ngrok) start_ngrok ;;
      cloudflare) start_cloudflare ;;
      pinggy) start_pinggy ;;
      *) echo "Unknown tunnel '$kind' (use ngrok, cloudflare or pinggy)" >&2; exit 1 ;;
    esac ;;
  which) choose_kind ;;
  url)
    case "$(cat "$STATE/mode" 2>/dev/null || echo pinggy)" in
      ngrok) url=$(ngrok_url) ;;
      cloudflare) url=$(cloudflare_url) ;;
      *) url=$(pinggy_url) ;;
    esac
    [ -n "$url" ] && show "$url" || { echo "No tunnel running. Start one: ./scripts/tunnel.sh start" >&2; exit 1; } ;;
  stop)
    stop_pinggy
    dc --profile tunnel --profile ngrok stop tunnel ngrok >/dev/null 2>&1 || true
    echo "Tunnel stopped." ;;
  *) echo "Usage: $0 start [auto|ngrok|cloudflare|pinggy] | url | which | stop" >&2; exit 1 ;;
esac
