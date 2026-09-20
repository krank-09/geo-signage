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
- **Demo topology:** exactly one display moves. `DEV-001` drives a route (`GPS_MODE=sim`); `DEV-002` (Delhi) and `DEV-003` (Mumbai) are `GPS_MODE=fixed` with `PLACE=<name>` (`device/gps.py` `place_coords`).
  The simulator (`run_all.py`, hence the Docker `sim` profile) and the kit's `start.sh`/`start.bat` prompt both encode this; the prompt defaults to fixed, because writing the drive route for every laptop made all three displays change content.
  The display's `d` panel hides the GPS jump/route buttons when `moving` is null (fixed). A bad `PLACE` fails immediately with the list of known places.
- **Live broadcasts** (`api/broadcasts.py`, `services/broadcasts.py`): text overlays (ticker/banner/fullscreen) targeted by zone/group/device, optional expiry. They ride the existing sync path: `/device/{id}/content` returns `broadcasts`, and the
  `manifest_version` the server returns is *playlist hash + broadcast hash*, so starting, ending or expiring one is noticed on the next heartbeat/location reply. The display page's playlist signature deliberately ignores `manifest_version`
  (it uses the item URLs), otherwise every broadcast would restart playback. Not video streaming.
- **Health + alerts** (`services/health.py`): score 0-100 = 100 minus CPU>60 / memory>70 / no GPS / late-heartbeat penalties, 0 when offline. `services/monitor.py` runs `evaluate_alerts` every sweep (5 s): raise below the threshold
  (setting `health_alert_threshold`, default 50), resolve at threshold+5, skip devices that never connected; pushes `alert` / `alert_resolved` to dashboards. In-dashboard only (toast + bell); no email/push.
- **Cities** (`data/cities.json`, `services/cities.py`, `scripts/build_cities.py`): 46 cities, 25 real OSM boundaries and 21 15 km circles; the builder rejects matches outside 20-1600 km2. `POST /cities/{id}/zone` creates a zone and calls `relocate_devices`.
- **Discovery** (`services/discovery.py`, `api/discovery.py`, `device/discovery.py`): agents with no device ID announce themselves (secret in, hash out) to an *unauthenticated, capped (100), 45 s-TTL, in-memory* list; `POST /devices` with `discovery_id` claims one and the
  credentials are returned to that agent on its next announce (once). Agent identity persists in `device/.cache/identity.json`; `start.sh --reset` clears it. In-memory means single process only.
- **Firebase auth** (`services/firebase.py`, `api/auth.py`): verifies ID tokens itself with PyJWT RS256 against Google's x509 certs (no SDK), then `POST /auth/firebase` exchanges for our normal JWT, so the rest of the app is unchanged. New people are `pending` (no access, and `security.user_from_token` returns 403 for pending) unless their
  *verified* email is in `FIREBASE_ADMIN_EMAILS`; admins approve on the Users page (`PUT /users/{id}/role`). Same verified email + new uid re-links instead of duplicating. `FIREBASE_AUTH_EMULATOR_HOST` accepts unsigned emulator tokens (dev only). The frontend loads the SDK lazily (`services/firebase.ts`) and only when `/auth/config` says it is enabled.
- **Schema upgrades** (`database.sync_schema`): additive columns/tables/indexes are applied at startup (tested on SQLite and PostgreSQL from the previous version's DB). Still no migrations for anything non-additive.
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

Tested: 45 backend tests (incl. `test_new_features.py`, `test_firebase.py`); live agents (geofence switching, offline/reconnect, emergency applied on reconnect, impressions, WebM playback from MinIO); full Docker stack with the sim profile;
Pinggy tunnel through `tunnel.sh`; display-kit unzip + `start.sh` first run; wrong-token warning; browser regression. **Not tested:** Firebase against a *real* project (only the Auth emulator + self-signed tokens: no real Google certs/consent/email), discovery across networks, health weights on real fleets, two physical laptops, Windows `start.bat`, Cloudflare connecting, ngrok success,
60-minute Pinggy expiry, kiosk mode, the device Docker image, real GPS/gpsd, Raspberry Pi, restart-while-offline, H.264 MP4, load/scale, non-Chromium browsers. Do not claim these; the full list is `DOCUMENTATION.md` F2.
