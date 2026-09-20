# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Documentation lives in exactly two Markdown files: this one (context for coding assistants) and `DOCUMENTATION.md` (everything a
human needs: overview, technical reference, presenter and display-laptop setup, demo script, judge Q&A, tested / not tested, env vars,
API list). Do not add more `.md` files. Part D of `DOCUMENTATION.md` (between the `BEGIN/END:display-guide` markers) is extracted into
`GUIDE.md` inside the display kit by `scripts/make-device-kit.sh`, so edit it there and keep the markers. The original brief is
`../Geo_Signage_Hackathon_Solution.md` (the user's file, not ours to edit).

## What this is

A geographical digital signage system (hackathon prototype): displays report GPS, the server maps position to a geofence zone, the zone
decides content, the display caches and plays it and **keeps playing offline**. Stack: FastAPI + SQLAlchemy (SQLite locally, PostgreSQL in
Docker), MinIO or local disk for media, React 19 + TypeScript + Tailwind v4 + react-leaflet dashboard, a Python device agent that serves a
kiosk display page from a local cache, and a simulator. Full map of the tree: `DOCUMENTATION.md` section A3.

## Commands (from the repo root)

```bash
# Full stack (Postgres + MinIO + backend + nginx/dashboard :3000); `sim` adds 3 simulated displays on :8101-8103
docker compose --profile sim up --build          # `sim` needs FIXED_DEMO_TOKENS=1 (the default)
docker compose --profile sim down -v             # wipes data; passwords/tokens are only applied at first DB creation

# No Docker (SQLite + local disk)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8000 --reload
.venv/bin/python -m pytest -q                    # 14 tests, temp SQLite (tests/conftest.py); one test: -k geofence
.venv/bin/ruff check app tests                   # config in backend/pyproject.toml
cd frontend && npm install && npm run dev        # :3000, proxies /api (REST+WS) to :8000 (BACKEND_URL overrides)
cd frontend && npm run build                     # strict tsc (noUnusedLocals/Parameters) then vite build
python simulator/run_all.py [--server URL --base-port N]   # needs device/requirements.txt; prompt: offline|online|goto|move|stop N

# Public demo
./scripts/tunnel.sh start [auto|ngrok|cloudflare|pinggy]   # also: url | which | stop
./scripts/make-device-kit.sh                     # -> dist/device-kit.zip (agent + GUIDE.md from DOCUMENTATION.md Part D)
```

Demo login `admin` / `admin123`; seeded devices `DEV-001..003`, tokens `DEMO-REG-001..003` unless `FIXED_DEMO_TOKENS=0` (then random, printed once
in the backend log). There is no CI. Tests cover the backend only; the agent and frontend are verified by hand / headless browser.

## Architecture (the parts that span files)

- **Core loop.** Agent posts location (`api/device_api.py`) -> `services/device_service.update_location` finds the zone (`services/geo.py`,
  ray casting on `[lat, lng]`) -> `services/resolver.resolve` picks content -> reply carries a `manifest_version` hash -> the agent refetches
  `/device/{id}/content` only if the hash differs. Load `zones` once per request and pass it to both calls (measured: 5 -> 4 SQL statements per location update).
- **Ranking** (`resolver.py`): emergency > `Assignment.priority` > specificity (zone+group 2 > one of them 1 > global 0); exact ties become a
  playlist (assignment id order, deduped). Priority outranks specificity on purpose. `HH:MM` windows use `SCHEDULE_TZ_OFFSET_MINUTES` (IST default), may wrap midnight;
  `start == end` means always.
- **Two auth realms** (`security.py`): admin JWT (`typ=admin`, roles admin/viewer, Argon2 passwords, 5 failed logins/min/user then 429) and device JWT
  (`typ=device`, checked against `Device.token_version`). Re-registration or "rotate token" bumps the version and revokes older tokens. Registration tokens are hashed and
  **reusable until rotated** (known limit). Admin-only `?token=` is accepted on media URLs via `current_user_or_query`.
- **Realtime** (`realtime.py`, `api/ws.py`): sync endpoints run in worker threads and call `notify_admins` / `notify_devices` / `announce_changes`, which bridge into the async hub with
  `anyio.from_thread.run` (a no-op outside a worker thread, e.g. in tests). Dashboards get `device_update`, `device_removed`, `assignments_changed`; displays get `{"type":"sync"}`. The hub is
  in memory (one process). Agents also poll every 5 s and compare `manifest_version` on every reply, so a lost push self-heals.
- **Offline.** `services/monitor.py` marks devices offline when `last_seen` is older than `OFFLINE_THRESHOLD_SECONDS` (30; the tunnel `.env` uses 45) and writes `online`/`offline`
  `DeviceLog` rows, which also feed 24 h uptime. The agent caches media on disk (`device/cache.py`: `<content>-v<version>.<ext>`, `state.json`) and serves the display page and files
  from `display_server.py`, so playback never touches the network. Simulated outage: `POST /api/control {"offline": true}` on the agent (display's `d` panel, `run_all.py`).
- **Agent invariants** (`device/agent.py`): heartbeat, location, websocket and sync loops are threads sharing one token. Registration rotates the credential, so it is serialized with `reg_lock`
  and skipped if another thread already re-registered. Do not remove that lock. `bootstrap.py` holds `.env` loading, `detect_server()` (accepts tunnel root, root + `/api`, or backend URL) and browser/kiosk launch.
- **Storage** (`storage.py`): `STORAGE_BACKEND=minio|local`; media is always streamed through the API with Range support (`services/media.py`), so every read is authenticated. Uploads are checked by extension,
  magic bytes and size while streaming.
- **API base.** Backend routes have no `/api` prefix; nginx and the Vite proxy strip it. Admin websocket: `/api/ws/admin?token=`.
- **Schema.** `Base.metadata.create_all` plus `seed.py` on first start, no migrations: a model change means resetting the DB (`down -v` or delete `backend/signage.db`). Seed slides use a bilinear-upscaled 2x2 gradient (0.24 s, was 2.9 s).

## Conventions

- Backend: one router per area under `api/`; shared 404 handling is `api/deps.get_or_404` / `get_device_or_404`; after anything that changes what displays should play call `realtime.announce_changes()`.
  Endpoints are plain `def` (worker threads), only the websocket and monitor code are async. Runtime deps in `requirements.txt`, test/lint deps in `requirements-dev.txt`.
- Frontend: types in `src/types.ts`, HTTP/auth helpers in `src/services/api.ts` (`isAdmin()`), `hooks/useDevices` for the live device list (pass `onEvent` for extra reactions; one socket per page),
  pages are `lazy()` routes, bigger pieces live in `components/dashboard` and `components/devices`. Design tokens (`ink-*`, `brand-*`, shadows) are in the `@theme` block of `src/index.css`;
  shared primitives in `components/ui.tsx`, charts in `components/charts.tsx` (hand-written SVG). Page roots use `.stagger` for cascade-in.
- **Page transitions** (`components/Layout.tsx`): `AnimatePresence` + a `Frozen` wrapper keeps the outgoing route mounted while it fades. Never put `filter`/`backdrop-filter`/permanent `transform` on that
  wrapper, or `position: fixed` modals break (the wrapper must settle at `transform: none`). Motion honours `prefers-reduced-motion` via `MotionConfig`.
- Follow the audit rules already applied: icon-only buttons need `aria-label`, decorative icons `aria-hidden`, placeholders end with an ellipsis, no `transition: all`, animate only transform/opacity.

## Public demo / tunnels (learned the hard way)

- `tunnel.sh auto` = ngrok if `NGROK_AUTHTOKEN` is set, else Cloudflare if outbound TCP 7844 is reachable, else Pinggy. On the dev network **7844 was blocked** (tunnel URL appeared but never connected, error 1033), 443 open.
  Pinggy (SSH over 443) worked end to end but its free URLs last 60 min and change; the script's loop reconnects but does not announce the new URL (`tunnel.sh url`), and every display laptop then needs `start.sh --reset`.
  ngrok: only the missing-token and bad-token paths were run (`ERR_NGROK_106`); the success path needs a real account. A static `NGROK_DOMAIN` makes the URL permanent.
- Tunnel containers start with `--no-deps`; a tunnel must never create or recreate the stack. Tunnel state lives in `.tunnel/` (`TUNNEL_STATE_DIR` overrides for tests).
- Port probing: macOS `nc -G` and bash `/dev/tcp` are both unreliable (60 s hang / IPv6 stall reports open ports as closed). `tcp_open` in `tunnel.sh` runs `nc -z` under a 5 s watchdog; keep it.
- Public exposure needs real `SECRET_KEY`, `ADMIN_PASSWORD` and `FIXED_DEMO_TOKENS=0`. The API also has known weak spots (tokens in websocket query strings, per-user in-memory throttling, open CORS).

## Working in this environment

- The user runs their own live stack from this folder (Docker on :3000/:8000, a tunnel, real `.env` and `.tunnel/`). **Do not** `docker compose down -v`, restart the tunnel, or edit `.env` without asking.
  Test on other ports (backend 8010, Vite 3010 with `BACKEND_URL`, simulator `--base-port 8111`) or an isolated `docker compose -p <name>` project, and kill by port-specific patterns, never a bare `pkill -f agent.py`.
- The shell is zsh: unquoted variables are not word-split (use `bash -c` for loops over "host port" pairs); there is no `timeout` binary on macOS; `sed -i ''` is the BSD form.
- Headless verification: Playwright Chromium is cached under `~/Library/Caches/ms-playwright`; a 21-step regression (all pages, device and zone CRUD through the UI, emergency onto a live display, transition probe) was used after the refactor.

## Tested vs not tested

Tested: 14 backend tests; live agents (geofence switching, offline/reconnect, emergency applied on reconnect, impressions, WebM playback from MinIO); full Docker stack with the sim profile;
Pinggy tunnel through `tunnel.sh`; display-kit unzip + `start.sh` first run; wrong-token warning; browser regression. **Not tested:** two physical laptops, Windows `start.bat`, Cloudflare connecting, ngrok success,
60-minute Pinggy expiry, kiosk mode, the device Docker image, real GPS/gpsd, Raspberry Pi, restart-while-offline, H.264 MP4, load/scale, non-Chromium browsers. Do not claim these; the full list is `DOCUMENTATION.md` F2.
