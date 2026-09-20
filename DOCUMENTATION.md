# Geo Signage: documentation

Geographical digital signage management: displays in many places, one control room. A display reports its GPS position, the server
works out which **geofence zone** it is in, the zone decides **what to play**, and the display caches and plays it,
**even when its internet drops**.

This is the only documentation file. Project context for coding assistants lives in `CLAUDE.md`.

## Contents

- [Part A: Overview and quick start](#part-a-overview-and-quick-start)
  - [A1. What it does, in one loop](#a1-what-it-does-in-one-loop)
  - [A2. Run it](#a2-run-it)
  - [A3. Code layout](#a3-code-layout)
  - [A4. Tests and known limits](#a4-tests-and-known-limits)
- [Part B: Technical reference](#part-b-technical-reference)
  - [B1. Architecture](#b1-architecture)
  - [B2. Data model](#b2-data-model)
  - [B3. How content gets chosen](#b3-how-content-gets-chosen)
  - [B4. Device agent internals](#b4-device-agent-internals)
  - [B5. Security](#b5-security)
  - [B6. Real-time flow](#b6-real-time-flow)
  - [B7. Public demo over a tunnel](#b7-public-demo-over-a-tunnel)
- [Part C: Presenter laptop setup](#part-c-presenter-laptop-setup)
  - [C1. What you need](#c1-what-you-need)
  - [C2. Check your laptop](#c2-check-your-laptop)
  - [C3. Free the ports and clear any old stack](#c3-free-the-ports-and-clear-any-old-stack)
  - [C4. Create your settings file](#c4-create-your-settings-file)
  - [C5. Build and start the server](#c5-build-and-start-the-server)
  - [C6. Collect the device tokens](#c6-collect-the-device-tokens)
  - [C7. Log in and check the dashboard](#c7-log-in-and-check-the-dashboard)
  - [C8. Prepare demo content](#c8-prepare-demo-content)
  - [C9. Build the display kit](#c9-build-the-display-kit)
  - [C10. Open the public tunnel](#c10-open-the-public-tunnel)
  - [C11. Send each display laptop its details](#c11-send-each-display-laptop-its-details)
  - [C12. Confirm the displays are connected](#c12-confirm-the-displays-are-connected)
  - [C13. Rehearse the demo](#c13-rehearse-the-demo)
  - [C14. On the day: run of show](#c14-on-the-day-run-of-show)
  - [C15. After the demo: shut down](#c15-after-the-demo-shut-down)
  - [C16. Troubleshooting](#c16-troubleshooting)
  - [C17. Command cheat sheet](#c17-command-cheat-sheet)
- [Part D: Display laptop setup](#part-d-display-laptop-setup)
  - [D0. What you need](#d0-what-you-need)
  - [D1. Install Python (skip if you already have 3.10+)](#d1-install-python-skip-if-you-already-have-310)
  - [D2. Unpack the kit](#d2-unpack-the-kit)
  - [D3. Start the display](#d3-start-the-display)
  - [D4. Show the display fullscreen](#d4-show-the-display-fullscreen)
  - [D5. Check that it works](#d5-check-that-it-works)
  - [D6. Demo controls (press `d`)](#d6-demo-controls-press-d)
  - [D7. Everyday commands](#d7-everyday-commands)
  - [D8. Troubleshooting](#d8-troubleshooting)
  - [D9. Optional: run with Docker instead of Python](#d9-optional-run-with-docker-instead-of-python)
  - [D10. Pre-demo checklist](#d10-pre-demo-checklist)
- [Part E: Demo](#part-e-demo)
  - [E1. Slide-by-slide talking points](#e1-slide-by-slide-talking-points)
  - [E2. Demo script, minute by minute](#e2-demo-script-minute-by-minute)
- [Part F: Questions and honesty](#part-f-questions-and-honesty)
  - [F1. Likely judge questions](#f1-likely-judge-questions)
  - [F2. What was tested and what was not](#f2-what-was-tested-and-what-was-not)
- [Part G: Reference](#part-g-reference)
  - [G1. Environment variables](#g1-environment-variables)
  - [G2. API surface](#g2-api-surface)
  - [G3. Ports and files](#g3-ports-and-files)

---

## Part A: Overview and quick start

### A1. What it does, in one loop

**Problem.** A company has screens in Chandigarh, Delhi and Mumbai (and a van that drives between them). Today someone
has to change each screen's content by hand. Screens go dark when the internet drops, and nobody knows a screen is
down until a customer complains.

**Solution.** One control room. Each display runs a small agent that reports its GPS position. The server works out
which **geofence zone** the position falls in, the zone decides **what to play**, and the display downloads it into a
local cache and plays it.

```
 GPS position ──▶ which zone? ──▶ which content? ──▶ download + cache ──▶ play
   (device)         (server)         (server)            (device)        (device)
                                                                            │
              internet drops? ── keep playing the cache ◀───────────────────┘
```

#### The three ideas that carry the demo

| Idea | What the audience sees | Why it matters |
|---|---|---|
| **Geofence switching** | The van crosses from Chandigarh into Delhi and its screen changes on its own, seconds later. | No one touches a screen. Content follows location. |
| **Offline caching** | Wi-Fi is switched off and the display keeps playing. It resyncs by itself when the network returns. | A dead connection never means a black screen. |
| **Live monitoring** | Devices flip to Offline on the dashboard, the event log fills, and the map moves in real time. | Operators find out before customers do. |

#### Side by side

| On screen | Say |
|---|---|
| Title slide with one line: *"Content follows location. Screens never go dark."* | "We built a control room for screens that are spread across cities. The content each screen shows is decided by where it physically is." |
| The loop diagram above | "Everything comes down to one loop: the device reports its position, the server picks the zone, the zone picks the content, the device caches and plays it. If the internet dies, the last step keeps working from the cache." |
| The three-idea table | "Three things carry the demo: content switches when a screen crosses a boundary, screens keep playing offline, and you see all of it live." |

### A2. Run it

**With Docker (full stack: Postgres, MinIO, backend, nginx + dashboard):**

```bash
docker compose --profile sim up --build
```

| What | Where |
|---|---|
| Admin dashboard | http://localhost:3000  (login `admin` / `admin123`) |
| API docs | http://localhost:8000/docs |
| Simulated device displays | http://localhost:8101 · 8102 · 8103 (press **d** for demo controls) |

Without `--profile sim` you get only the server; run devices yourself (below). First start seeds an admin,
3 devices (`DEV-001..003`, registration tokens `DEMO-REG-001..003`), 3 city zones, generated slides and an alert slide.
Set `SECRET_KEY` and `ADMIN_PASSWORD` in `.env` for anything beyond a demo (see [C4](#c4-create-your-settings-file)).
The `sim` profile needs the well-known tokens, so keep `FIXED_DEMO_TOKENS=1` (the default) when you use it.

**Without Docker (SQLite + local disk storage):**

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# dashboard (proxies /api and /ws to :8000)
cd frontend && npm install && npm run dev            # http://localhost:3000

# 3 simulated devices with an interactive prompt (offline / goto / move / stop / status)
pip install -r device/requirements.txt && python simulator/run_all.py
```

Single device / real hardware: `python device/agent.py --server http://SERVER:8000 --device-id DEV-001 --token <registration token> --port 8101`
then open `http://localhost:8101` in Chromium kiosk mode
(`chromium --kiosk --autoplay-policy=no-user-gesture-required http://localhost:8101`).
Use `--gps gpsd` for a real receiver, `--gps fixed --lat .. --lng ..`, or the default simulated route.
`--server` accepts the backend URL, a tunnel root, or a tunnel root plus `/api`; the agent finds the right one.

### A3. Code layout

```
geo-signage/
├── CLAUDE.md               context for coding assistants
├── DOCUMENTATION.md        this file (the only documentation)
├── docker-compose.yml      db, minio, backend, frontend; profiles: sim, tunnel, ngrok
├── .env.example            copy to .env (never commit .env)
├── backend/                FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py         app wiring only: lifespan, CORS, routers, /health
│   │   ├── config.py       every environment setting, in one place
│   │   ├── models.py  schemas.py  database.py  security.py  realtime.py  storage.py  seed.py
│   │   ├── api/            one router per area
│   │   │   auth  users  devices  device_api (called by agents)  content  zones
│   │   │   assignments (+ emergency)  monitoring  ws (WebSockets)  deps (shared 404 helpers)
│   │   └── services/       geo (point in polygon)  resolver (what to play)  device_service
│   │                       zone_service  media (upload checks + range streaming)  monitor (offline sweep)
│   ├── tests/              pytest against a temporary SQLite database
│   ├── requirements.txt    runtime only        requirements-dev.txt  tests + ruff        pyproject.toml
├── frontend/               Vite + React + TypeScript + Tailwind v4
│   └── src/
│       ├── App.tsx  main.tsx  index.css (design tokens, motion)
│       ├── services/api.ts   axios instance, auth helpers        types.ts   shared interfaces
│       ├── hooks/            useLive (admin WebSocket)   useDevices (device list + live merge)
│       ├── components/       ui  charts  Layout (nav + page transitions)  MapView  AssignmentForm
│       │   ├── dashboard/    Kpi  DeviceDetailPanel
│       │   └── devices/      TokenBox  AddDeviceModal  DeviceDetailModal
│       └── pages/            one lazy-loaded page per route
├── device/                 the display agent (also what display laptops receive)
│   ├── agent.py            DeviceAgent: register, heartbeat, location, sync, push, impressions
│   ├── bootstrap.py        .env loading, server discovery, opening the browser
│   ├── cache.py  display_server.py  gps.py  display/index.html
│   └── start.sh  start.bat  Dockerfile  .env.example  requirements.txt
├── simulator/run_all.py    starts several agents with simulated GPS and a control prompt
└── scripts/
    ├── tunnel.sh           public URL via ngrok, Cloudflare or Pinggy (start | url | which | stop)
    └── make-device-kit.sh  builds dist/device-kit.zip (agent + GUIDE.md taken from Part D)
```

### A4. Tests and known limits

**Tests and checks.** Backend: `cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q` (geofencing, scheduling windows, priority, emergency override, device auth and revocation, offline detection, upload validation, media Range requests, roles, password change, timeline) and `.venv/bin/ruff check app tests`. Frontend: `cd frontend && npm run build` (strict type-check, including unused code, then the production build).

**Known limits of the prototype.** Zone geometry uses ray-casting in Python (no PostGIS; fine for hundreds of zones). Schemas are created with `create_all` (no migrations). Registration tokens are reusable until rotated. Impressions are reported by the display page. The agent's display server is plain HTTP on the device itself.

The full tested / not-tested list is in [Part F](#part-f-questions-and-honesty), section F2.

---

## Part B: Technical reference

### B1. Architecture

```
 ┌──────────────────────────┐
 │  Admin dashboard (React) │  Overview · Devices · Content · Zones & map · Schedules · Emergency · Monitoring · Users
 └────────────┬─────────────┘
              │ HTTPS  +  WebSocket (/api/ws/admin)
              ▼
 ┌──────────────────────────┐
 │  nginx  (serves the UI,  │  strips the /api prefix and forwards REST + WebSocket
 │  proxies /api)           │
 └────────────┬─────────────┘
              ▼
 ┌────────────────────────────────────────────────────────────┐
 │  FastAPI backend (one process, "modular monolith")         │
 │  auth · devices · content · zones · assignments · monitoring│
 │  services: geo (point-in-polygon) · resolver · device · media│
 │  realtime hub (WebSocket fan-out) · offline monitor task    │
 └───────┬───────────────────────────────┬────────────────────┘
         │ SQL                            │ S3 API
         ▼                                ▼
 ┌───────────────┐                 ┌────────────────┐
 │  PostgreSQL   │                 │  MinIO         │  images and videos
 └───────────────┘                 └────────────────┘

        ▲  REST + WebSocket (/ws/device/<id>)  ── device credentials, outbound only
        │
 ┌──────┴───────────────────────────────────────────────┐
 │  Device agent (Python) on each display laptop / Pi   │
 │  GPS source · heartbeat · sync · disk cache          │
 │  local web server ──▶ Chromium fullscreen display    │
 └──────────────────────────────────────────────────────┘
```

#### Why each piece was chosen

| Piece | Choice | Reason |
|---|---|---|
| Backend | **FastAPI** (Python) | Fast to build, built-in WebSocket support, automatic API docs at `/docs`, easy to add analytics later. |
| Shape | **One modular monolith** | A hackathon team gets one thing to deploy and debug, not ten services. The code is still split by responsibility (`api/`, `services/`, `models.py`). |
| Database | **PostgreSQL** | Real relational data (devices, zones, assignments, logs). SQLite is used only for local no-Docker development. |
| Media | **MinIO** (S3-compatible) | Large videos do not belong in the database. Swapping to S3 or R2 later needs only configuration. |
| Dashboard | **React + TypeScript + Tailwind, react-leaflet** | Typed UI, fast styling, and Leaflet gives a free OpenStreetMap map with polygon zones. |
| Live updates | **WebSocket, plus polling as a fallback** | Push makes the demo feel instant. Polling means a missed push repairs itself within seconds. |
| Display | **Local web page served by the agent** | The browser only talks to `localhost`, so playback never depends on the internet. This is what makes offline behaviour real, not simulated. |
| Front door | **nginx** | Serves the built UI and forwards `/api` (including WebSocket). One public port is enough for the tunnel. |
| Devices dial out | **No inbound ports on displays** | Displays behind any router or hotspot work, and the tunnel only needs to expose the server. |

#### Side by side

| On screen | Say |
|---|---|
| The architecture diagram | "Browser on top, one FastAPI backend in the middle, Postgres for data and MinIO for media underneath. Devices connect from the side, and always outbound." |
| The "why" table, highlighting *Display* | "The important design choice is the display page. It is served by the agent on the laptop itself, from a disk cache. So when the internet dies, nothing in the playback path is missing." |
| Highlight *Modular monolith* | "We deliberately did not build microservices. For this scale, one service with clean modules is easier to run and easier to explain." |

### B2. Data model

Eight tables. Foreign keys are shown with arrows.

```
 users                 device_groups            zones
 ─────                 ─────────────            ─────
 id                    id                       id
 username (unique)     name (unique)            name (unique)
 password_hash         │                        polygon  [[lat,lng], …]  (JSON)
 role: admin|viewer    │                        priority
                       │                        color
                       │                           │
 devices ──────────────┘                           │
 ───────                                           │
 device_id (unique)  group_id ─▶ device_groups     │
 registration_token_hash  token_version            │
 status  last_seen  latitude  longitude            │
 current_zone_id ────────────────────────────────▶ zones
 current_content_version / names, cpu, memory, network, gps_ok
 config (JSON: heartbeat, gps interval, mute, fit)
                                                    │
 content                       assignments          │
 ───────                       ───────────          │
 id  name  type: image|video   content_id ─▶ content│
 storage_key  mime  size       zone_id ────────────▶ zones   (nullable)
 duration (s, for images)      group_id ─▶ device_groups (nullable)
 version (bumped on change)    start_time / end_time  "HH:MM" (nullable)
                               priority
 device_logs                   is_emergency   active
 ───────────
 device_id  ts  kind  message      impressions
 (online / offline / zone /        ───────────
  register / config …)             device_id  content_id  zone_id  started_at  duration
```

#### How the tables relate

- A **device** belongs to at most one **group** and reports a position. The server stores which **zone** it is currently in.
- An **assignment** is the only place content is connected to a place. It links one **content** item to a **zone**, a **group**, or neither.
  A row with neither is the global default.
- **content.version** goes up whenever a file is replaced or its duration changes. Devices use it to know they need to download again.
- **device_logs** is an append-only history. The dashboard event feed, the zone-visit counts and the 24-hour uptime figure are all computed from it.
- **impressions** is what displays report after they finish playing an item. It feeds the "views" charts.

#### Side by side

| On screen | Say |
|---|---|
| The schema diagram | "Eight tables. The heart of it is one table, assignments. It says: this content, for this zone, for this group, in this time window, at this priority." |
| Highlight the nullable columns on *assignments* | "Leave the zone empty and it applies everywhere. Leave the group empty and it applies to every device. Leave both empty and you have a default." |
| Highlight *device_logs* | "We do not store uptime as a number. We log online and offline events and compute uptime from that history, so it is always explainable." |

### B3. How content gets chosen

Every time a device reports in, the server runs `resolve()` (`backend/app/services/resolver.py`).

**Step 1: collect candidates.** Keep an assignment only if all of these hold:

1. it is active,
2. its zone contains the device's position (or it has no zone),
3. its group matches the device's group (or it has no group),
4. the current time is inside its window (or it has no window).

**Step 2: rank the candidates.** Each candidate gets a score `(emergency, priority, specificity)`, compared in that order:

| Order | Field | Meaning |
|---|---|---|
| 1st | **emergency** | An emergency assignment beats everything that is not an emergency. |
| 2nd | **priority** | Higher number wins. |
| 3rd | **specificity** | Zone **and** group (2) beats zone or group (1) beats "everywhere" (0). |

**Step 3: play the winners.** Everything that ties at the top score plays together as a **playlist**, in assignment order,
with duplicates removed. The result carries a short `manifest_version` hash, so a device only downloads when the hash
changes.

#### Worked examples

Assume DEV-001 is inside *Delhi Zone*, in group *North India*.

| # | Assignments that match | Winner | Why |
|---|---|---|---|
| 1 | "Welcome" (everywhere, priority 0) and "Delhi Ad" (Delhi zone, priority 10) | **Delhi Ad** | Higher priority, and also more specific. |
| 2 | "Flash Sale" (everywhere, priority **50**) and "Delhi Ad" (Delhi zone, priority 10) | **Flash Sale** | Priority is compared *before* specificity, so a high-priority global item can override a local one. This is deliberate and easy to demo. |
| 3 | "Delhi Ad" and "Delhi Festival" (both Delhi zone, priority 10) | **Both, as a playlist** | Exact tie, so they rotate. |
| 4 | "Delhi Ad" (priority 10) and "Alert" (everywhere, priority 0, **emergency**) | **Alert** | Emergency outranks priority. Several emergencies rank among themselves by priority. |
| 5 | "Delhi Ad" (Delhi zone) but the device is in Jaipur, outside every zone | **Welcome** | Only the global default matches. |
| 6 | "Delhi Ad" with the assignment paused (`active` off) | Next best | Inactive rows are ignored. |

#### Time windows, including ones that cross midnight

A window is two `HH:MM` values. Both empty means always.

| Window | Meaning |
|---|---|
| `10:00`–`14:00` | Active from 10:00 up to, but not including, 14:00. |
| `22:00`–`06:00` | **Crosses midnight.** Active from 22:00 until 06:00 the next morning. Internally: active if `now ≥ 22:00` **or** `now < 06:00`. |
| `09:00`–`09:00` | Start equals end is treated as always active. |

> **Time zone.** Windows are evaluated on the **server** in a fixed offset (default IST, UTC+5:30, `SCHEDULE_TZ_OFFSET_MINUTES`),
> not in the device's own time zone. Example from the test suite: 20:00 UTC is 01:30 IST the next day, so a `22:00`–`06:00` window is active.

#### Side by side

| On screen | Say |
|---|---|
| The three-row ranking table (emergency, priority, specificity) | "Three rules, in order. Emergency first. Then the priority number. Then how specific the match is." |
| Example 2 (Flash Sale vs Delhi Ad) | "Notice priority beats specificity. That is intentional: an operator can override local content everywhere by giving it a higher number. We can show it live." |
| Example 3 (tie) | "If two items tie, they play as a playlist. No hidden tie-breaker, and that is why one zone can have a rotation." |
| The midnight window row | "Night-time promotions cross midnight, so `22:00` to `06:00` works. Windows use server time, so every screen follows the same clock." |

### B4. Device agent internals

The agent (`device/agent.py`) is one Python process with a small local web server and four background loops. Startup helpers (`.env` loading, server discovery, opening the browser) live in `device/bootstrap.py`.

```
  ┌─────────────────────────── device agent ────────────────────────────┐
  │  location loop   every 3 s   POST /device/location   ─┐             │
  │  heartbeat loop  every 10 s  POST /device/heartbeat  ─┼─▶ reply carries manifest_version + config
  │  websocket loop  always on   /ws/device/<id>  ───────┐│             │
  │  sync loop       wakes on push, else every 5 s ◀─────┴┘ hash changed? → fetch playlist
  │                                                                      │
  │  disk cache  media/<content>-v<version>.<ext>  +  state.json         │
  │  local web server :8101  →  display page reads /api/state           │
  └──────────────────────────────────────────────────────────────────────┘
```

#### Lifecycle

| Stage | What happens |
|---|---|
| **Registration** | The admin creates a device in the dashboard and gets a one-time **registration token**. The agent sends device ID plus token to `/device/register` and receives a **device JWT** (valid 30 days). Both are saved in `state.json`. |
| **Server discovery** | `detect_server()` accepts the tunnel root, the root plus `/api`, or a direct backend URL and finds the one whose `/health` answers. |
| **Heartbeat** | Every 10 s (configurable from the dashboard): CPU, memory, network, GPS status, and which playlist version it is showing. The server records `last_seen`. |
| **Location** | Every 3 s the GPS source is read and posted. Laptops use a **simulated route**. The code also supports a fixed point or a real receiver through gpsd (untested). |
| **Push plus polling** | The server pushes `{"type":"sync"}` over WebSocket on any change. The agent also polls every 5 s and compares `manifest_version` on every heartbeat/location reply, so a lost push is repaired within seconds. |
| **Sync** | Fetch the playlist, download any missing files (streamed to a `.part` file, then renamed), save the manifest, trigger an immediate heartbeat so the dashboard's "now playing" updates. |
| **Cache** | Files are named `<content id>-v<version>.<ext>`, so a replaced file is a new name and cannot be confused with the old one. Old files are removed when more than 20 accumulate. |
| **Display** | The page polls the agent's local `/api/state` every second, plays images for their duration and videos to their end, cross-fades, and reports each finished item as an **impression**. |

#### Offline and reconnect

| Moment | Behaviour |
|---|---|
| **Internet drops** | Every request to the server fails. The agent marks itself disconnected. The display **keeps playing the last cached playlist**. The status pill turns red: *OFFLINE - playing cached content*. |
| **On the server** | No heartbeat arrives. A background task (runs every 5 s) marks the device **Offline** once `last_seen` is older than the threshold (**30 s** by default, **45 s** in the tunnel setup). It writes an `offline` log row and pushes an update to the dashboard. |
| **Changes made while offline** | They are not received. For example an emergency alert sent during the outage does **not** appear on that screen yet. |
| **Impressions while offline** | Buffered in memory (up to 1,000) and sent when the connection is back. |
| **Internet returns** | The next heartbeat succeeds, the device logs `online`, the agent compares `manifest_version`, downloads what is new and switches. In our test, the alert sent during the outage appeared on reconnect. |
| **Credentials revoked** | A rejected token makes the agent re-register automatically with its registration token. Registration is serialized with a lock, because each registration rotates the credential and concurrent attempts would invalidate each other. |
| **Agent restart with no network** | The saved manifest and cached files are reloaded from disk, so the display can resume. *Designed this way; not explicitly tested.* |

#### Side by side

| On screen | Say |
|---|---|
| The agent box diagram | "Four loops. Location every three seconds, heartbeat every ten, a WebSocket for instant pushes, and a sync loop that polls as a safety net." |
| The lifecycle row *Push plus polling* | "We use both on purpose. Push feels instant in a demo. Polling means if a push is ever lost, the screen repairs itself within five seconds." |
| The offline table | "When the network dies, nothing about playback changes, because the browser only talks to the agent on the same laptop. The dashboard notices within half a minute, and the moment the network returns the screen catches up." |
| Point at *Changes made while offline* | "Be honest about this: a screen that is offline cannot receive new instructions. It shows the last thing it knew. That is the right trade-off for signage." |

### B5. Security

#### Two kinds of login

| | **Administrators** | **Devices** |
|---|---|---|
| Identity | Username and password | Device ID and registration token |
| Secret storage | Password hashed with **Argon2** | Registration token hashed with **Argon2** |
| Session | Signed **JWT**, valid 12 hours, `typ=admin` | Signed **JWT**, valid 30 days, `typ=device` |
| Roles | `admin` (full control), `viewer` (read-only) | Single role, can only call `/device/*` for **its own** ID |
| Cross-use | An admin token is rejected on device endpoints (enforced by the token type check; not covered by a test) | A device token is rejected on admin endpoints (covered by a test on `/devices`) |
| Brute force | 5 failed logins per username per minute, then HTTP 429 | Registration returns the same error for an unknown device and a wrong token, so IDs cannot be enumerated |

#### Revoking a device

Each device row has a `token_version`. Every device JWT carries the version it was issued under.
**Re-registering** or the dashboard's **Revoke and re-issue token** increases the version, so every older credential
stops working immediately. The old token cannot be used to connect again until re-registered.

#### Uploads

| Check | Detail |
|---|---|
| File type allow-list | `.jpg .jpeg .png .mp4 .webm` only |
| Content check | The first bytes must match the extension (JPEG, PNG, MP4 and WebM signatures), so a renamed `.exe` is refused |
| Size limit | 100 MB by default (`MAX_UPLOAD_MB`), enforced while streaming, not after |
| Storage names | Random UUID keys, never the user's file name |
| Delivery | Media is streamed through the API, so every read is authenticated, and HTTP range requests work for video |

#### What changes when the server is public

| Risk | What we did | Still open |
|---|---|---|
| Guessable admin password | `ADMIN_PASSWORD` from the environment, plus **Change my password** on the Users page, plus a startup warning if the default is still in place | No password policy beyond a minimum length of 8, and no multi-factor login |
| Guessable device tokens | `FIXED_DEMO_TOKENS=0` generates random tokens printed once in the log | Tokens are **reusable** until rotated (see limits below) |
| Default signing key | `SECRET_KEY` from the environment, plus a startup warning for the built-in default | Changing it logs everyone out; there is no key rotation |
| Traffic in the clear | The tunnel gives HTTPS and secure WebSockets | The agent's local display page on `localhost` is plain HTTP (never leaves the machine) |
| Exposed surface | MinIO ports are no longer published; only the web port is tunnelled | The whole admin API is reachable through the tunnel and protected only by login throttling and JWTs |

**Known weak spots to mention if asked:** WebSocket tokens travel in the query string (they can appear in proxy logs);
login throttling is in memory and per username, not per IP; CORS is open to any origin; admin logout only discards the
token on the client.

#### Side by side

| On screen | Say |
|---|---|
| The two-column admin / device table | "Two completely separate login types. Each token carries its type, and the server checks it: a device token cannot open the dashboard's API, and we have a test for that." |
| The revocation paragraph | "If a screen is stolen or compromised, one click bumps its token version and its credentials die instantly. It has to be re-registered." |
| The "public server" table | "Putting a demo on the internet changes the risk. We removed default passwords and default tokens from the public path and added a warning when the defaults are still in use." |
| The weak-spots list | "Here is what we know is not production-grade: tokens in WebSocket URLs, per-user rate limiting, and open CORS." |

### B6. Real-time flow

Two separate WebSocket channels: one to **dashboards**, one to **displays**.

#### To the dashboard (`/api/ws/admin`)

| Event | Sent when | Effect on the UI |
|---|---|---|
| `device_update` | A device registers, sends a heartbeat or a location, changes config, is created, or is marked offline by the monitor | The device row, map dot, KPI cards and the "Recent activity" feed update without a refresh |
| `device_removed` | A device is deleted | It disappears from the list |
| `assignments_changed` | An assignment, zone, content item, group or emergency changes | Zone and alert counters refresh |

The dashboard also re-fetches the device list every 15 s, so a missed event does not leave stale data.

#### To the displays (`/ws/device/<id>`)

The server sends one message type, `{"type":"sync","reason":…}`. The agent reacts to **any** sync by re-fetching its playlist.

| Reason | Sent to | Triggered by |
|---|---|---|
| `assignments` | **All** connected devices | Any assignment, zone or group change, and starting or clearing an emergency |
| `content` | **All** connected devices | Content uploaded (replace), renamed, retimed or deleted |
| `config` | The **one** device | Its remote configuration or name/group was edited |
| `manual` | The **one** device | The **Force sync** button |

#### End-to-end timing you can expect

| Action | Result on the display |
|---|---|
| Admin creates an emergency alert | Display switches almost immediately (WebSocket push). At worst within about 5 s (polling fallback). |
| Device crosses a zone boundary | Within about one location tick (3 s): the location reply carries a new `manifest_version`, the agent syncs, the display changes. |
| Device loses the network | Display: no change. Dashboard: **Offline** after 30–45 s. |

#### Side by side

| On screen | Say |
|---|---|
| The two-channel table | "Two channels. The dashboard listens to what devices do. The displays listen for one word: sync." |
| The timing table | "An emergency alert reaches the screens almost instantly. A boundary crossing takes about three seconds. An outage takes half a minute to show up on the dashboard, because we wait for missed heartbeats before crying wolf." |

### B7. Public demo over a tunnel

**Goal.** Dashboard on the presenter's laptop, displays on other laptops anywhere with internet.
Displays only make outbound connections, so **only the server needs a public address**.

```
 Display laptop ──HTTPS/WSS──▶  https://<random>.<tunnel domain>/api ─┐
 Presenter browser ─HTTPS────▶  https://<random>.<tunnel domain>/     ├─▶ tunnel ─▶ nginx :3000 ─▶ backend ─▶ Postgres + MinIO
                                                                      ┘
```

#### Three tunnel options

| | **ngrok** | **Cloudflare quick tunnel** | **Pinggy (SSH over port 443)** |
|---|---|---|---|
| Account | Free account and authtoken | None | None |
| Install | Docker container | Docker container | The `ssh` that is already installed |
| Outbound port | 443 | **7844** (QUIC or TCP) | 443 |
| URL | **Fixed** if you claim a free static domain, otherwise changes on restart | Changes on restart | Changes every 60 minutes |
| Lifetime | Until stopped | Until stopped | **60 minutes**, then a new URL |
| Browser notice | One-time ngrok notice (agents skip it) | None | One-time "Enter site" page (agents skip it) |
| **On the network we tested** | Port reachable; a bad-token run gave a clean error; the success path was **not** tested (needs an account) | **Blocked** | **Worked** |

`./scripts/tunnel.sh start` chooses for you: **ngrok** if `NGROK_AUTHTOKEN` is set, otherwise **Cloudflare** if port 7844 is
reachable, otherwise **Pinggy**. `./scripts/tunnel.sh which` shows the pick without starting anything. **The check and the fallback
were needed for real:** on our network Cloudflare's tunnel URL was created but never connected (error 1033), and port 7844 was
blocked for QUIC and TCP.

#### Setup summary

| Who | Steps |
|---|---|
| **Presenter** | `cp .env.example .env` (set `SECRET_KEY` and `ADMIN_PASSWORD`, keep `FIXED_DEMO_TOKENS=0`), `docker compose up --build -d`, `./scripts/tunnel.sh start`, read tokens with `docker compose logs backend \| grep "Registration token"`, build the kit with `./scripts/make-device-kit.sh` |
| **Each display laptop** | Unzip `device-kit.zip`, run `./start.sh` (macOS/Linux) or `start.bat` (Windows), paste the **Server URL**, **Device ID** and **token**. Full instructions: [Part D](#part-d-display-laptop-setup) |

#### Side by side

| On screen | Say |
|---|---|
| The tunnel diagram | "The displays only dial out, so the only thing that has to be reachable is the server. A tunnel gives it a public HTTPS address." |
| The tunnel comparison table, highlighting the last row | "We found out the hard way that many networks block Cloudflare's tunnel port. So the script checks what the network allows: ngrok if configured, otherwise Cloudflare, otherwise a tunnel that only needs port 443." |
| The setup summary | "Each display laptop needs Python, a zip file and three values: the server address, its own ID and its token." |

---

## Part C: Presenter laptop setup

Sets up **your** laptop as the server and control room for the multi-laptop demo. About 20 minutes the first time (mostly the first Docker build).

```
 Display laptops ──HTTPS──▶  public tunnel URL ──▶ nginx :3000 ──▶ backend :8000 ──▶ Postgres + MinIO
 Your browser  ────────────▶  http://localhost:3000   (same stack, no tunnel needed for you)
```

> Written for **macOS or Linux**. On Windows, run everything inside **WSL2** with Docker Desktop's WSL integration. Not tested on Windows.

### C1. What you need

| Item | Details |
|---|---|
| Laptop | macOS or Linux (Windows via WSL2), about 6 GB free disk, 8 GB RAM recommended |
| **Docker Desktop** (or Docker Engine + Compose v2) | Runs the whole server. No Python or Node install is needed on your laptop. |
| Internet | Any network that allows outbound HTTPS (port 443). Home Wi-Fi, a phone hotspot, or venue Wi-Fi. |
| Terminal tools | `bash`, `ssh`, `curl`, `openssl`, `rsync`, `zip`, `perl`. All ship with macOS. On Debian/Ubuntu: `sudo apt install rsync zip curl openssl perl openssh-client` |
| A browser | Chrome, Edge, or Safari for the dashboard |
| The project folder | `geo-signage/` (everything below is run from inside it) |
| A way to send files | AirDrop, USB stick, chat app, or a shared drive, to give the kit to the display laptops |

Ports used **on your laptop**: `3000` (dashboard) and `8000` (API and docs). Both must be free.

### C2. Check your laptop

Open a terminal and go to the project folder:

```bash
cd path/to/geo-signage
ls
```

You should see `backend  device  docker-compose.yml  docs  frontend  scripts  simulator ...`

Run these checks. Each one should succeed:

```bash
docker --version                 # Docker version 24 or newer
docker compose version           # Docker Compose version v2.x
docker info > /dev/null && echo "Docker is running"
ssh -V                           # any OpenSSH version
```

If `Docker is running` does not appear, start Docker Desktop, wait until its icon says it is running, and try again.

**Check that your network allows the tunnel** (this is the most common surprise at venues):

```bash
# macOS
nc -z -G 5 free.pinggy.io 443 && echo "Pinggy OK (port 443 open)" || echo "port 443 blocked"
# Linux
nc -z -w 5 free.pinggy.io 443 && echo "Pinggy OK (port 443 open)" || echo "port 443 blocked"
```

- `Pinggy OK` means the tunnel will work.
- If it says blocked, switch to a phone hotspot before continuing.

> **Why check this?** On the network we developed on, Cloudflare's tunnel port (7844) was blocked but port 443 was open,
> so the tunnel script uses Pinggy (over 443) when Cloudflare is not reachable. You do not need to choose. The script tests and decides.

- [ ] Docker is running
- [ ] Port 443 is open (or you are on a hotspot)

### C3. Free the ports and clear any old stack

Look for anything already using ports 3000 or 8000:

```bash
lsof -nP -iTCP:3000 -iTCP:8000 -sTCP:LISTEN
docker ps --format '{{.Names}}  {{.Ports}}'
```

**If you see containers named `geo-signage-...`** from earlier runs, they are an older build and hold the same ports. Remove them:

```bash
docker compose --profile sim --profile tunnel down -v
```

> ⚠️ `-v` **deletes the old database and uploaded media**. That is what you want here: passwords and device tokens are only set when
> the database is first created, so an old database would keep the old default password and `DEMO-REG-…` tokens.

If something else (not Docker) holds port 3000 or 8000, quit that program, or change `FRONTEND_PORT` / `BACKEND_PORT` in step 4.

- [ ] `lsof` shows nothing on 3000 and 8000
- [ ] No old `geo-signage-*` containers running

### C4. Create your settings file

The `.env` file holds your secrets. It is read automatically by Docker Compose and is ignored by git.

Create it with a freshly generated secret key. **Change `ADMIN_PASSWORD` to your own password before running this.**

```bash
cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=ChangeMe-Before-Demo-42
FIXED_DEMO_TOKENS=0
MAX_UPLOAD_MB=90
OFFLINE_THRESHOLD_SECONDS=45
FRONTEND_PORT=3000
BACKEND_PORT=8000
EOF
```

Then open `.env` in an editor and replace `ChangeMe-Before-Demo-42` with a strong password you will remember.

What each setting does:

| Setting | Meaning |
|---|---|
| `SECRET_KEY` | Signs login tokens. Long and random. Never share it. |
| `ADMIN_PASSWORD` | Password for the `admin` account. Only applied when the database is **first created**. |
| `FIXED_DEMO_TOKENS=0` | Seeded devices get **random** registration tokens (safe for a public URL). Do not set `1` when using the tunnel. |
| `MAX_UPLOAD_MB=90` | Largest file you can upload. Kept under the tunnel's 100 MB request limit. |
| `OFFLINE_THRESHOLD_SECONDS=45` | How long without a heartbeat before a device shows Offline. 45 s avoids false alarms from brief tunnel hiccups. |
| `FRONTEND_PORT`, `BACKEND_PORT` | Host ports. Change them here if 3000 or 8000 is taken. |
| `NGROK_AUTHTOKEN`, `NGROK_DOMAIN` | Optional. Only for the ngrok tunnel (see [C10](#c10-open-the-public-tunnel)). Leave them out of the file if you do not use ngrok. |

> **Password rules for `.env`:** avoid `$`, `#`, quotes and spaces in `ADMIN_PASSWORD`. Docker Compose treats them specially.
> Letters, digits, `-` and `_` are safe.

- [ ] `.env` exists and has your own password
- [ ] `FIXED_DEMO_TOKENS=0`

### C5. Build and start the server

```bash
docker compose up --build -d
```

**First run takes about 3–8 minutes** (it downloads Postgres and MinIO images and builds the backend and dashboard).
Later runs take seconds.

When it returns, check the services:

```bash
docker compose ps
```

Expected: four services running, `db` shown as `healthy`.

```
NAME                   SERVICE    STATUS
geo-signage-db-1       db         Up (healthy)
geo-signage-minio-1    minio      Up
geo-signage-backend-1  backend    Up
geo-signage-frontend-1 frontend   Up
```

Confirm the API answers (allow up to 30 seconds after start):

```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

If it does not answer yet, wait a few seconds and try again. If it never does, see [Troubleshooting](#c16-troubleshooting).

Check the startup log for warnings:

```bash
docker compose logs backend | grep -E "WARNING|seed"
```

You should see the seeding lines (`Created default admin user`, `Seeded demo data`) and the three token lines from step 6.
You should **not** see `SECRET_KEY is the built-in default` or `Admin password is the default 'admin123'`.
If you do, `.env` was not picked up: check it is in the same folder as `docker-compose.yml`, then run
`docker compose down -v && docker compose up --build -d`.

- [ ] `docker compose ps` shows 4 services up
- [ ] `curl` returns `{"status":"ok"}`
- [ ] No default-secret or default-password warnings

### C6. Collect the device tokens

Three demo devices were created with **random registration tokens that are printed once in the log**:

```bash
docker compose logs backend | grep "Registration token"
```

Output looks like:

```
Registration token for DEV-001: A1B2-C3D4-E5F6
Registration token for DEV-002: B2C3-D4E5-F6A1
Registration token for DEV-003: C3D4-E5F6-A1B2
```

**Copy these into a note now.** They are what you send to the display laptops in step 11.

| Device | Seeded name | Seeded group | Registration token |
|---|---|---|---|
| `DEV-001` | Roadshow Van | North India | *(paste)* |
| `DEV-002` | Connaught Place Kiosk | North India | *(paste)* |
| `DEV-003` | Bandra Billboard | West India | *(paste)* |

- **Need more than three laptops?** In the dashboard open **Devices → + Add device**. The token is shown **once**, so copy it right away.
- **Lost a token?** Open the device in **Devices** and click **Revoke & re-issue token**. This also disconnects that laptop until it is re-entered.

> **One laptop = one Device ID.** Two laptops sharing an ID keep knocking each other offline.

- [ ] Three tokens saved somewhere safe

### C7. Log in and check the dashboard

Open **http://localhost:3000** in your browser.

- Username: `admin`
- Password: the one you put in `.env`

> Use `localhost` for your own browser. It skips the tunnel, so you avoid the tunnel's warning page and get the fastest response.
> Only the display laptops use the public address.

What you should see on **Overview**:

| Element | Expected right now |
|---|---|
| **Devices online** | `0 / 3` (no display laptop is connected yet) |
| **Zones & alerts** | `3 geofences`, "No active emergency alerts" |
| Live map | Three zone circles (Chandigarh, Delhi, Mumbai) |
| Displays list | `DEV-001`, `DEV-002`, `DEV-003`, all Offline |

Also check the other pages load: **Content** (five slides), **Zones & map**, **Schedules** (four assignments), **Emergency**.

**Optional:** change the password from the **Users** page (**Change my password**).

- [ ] Logged in on `http://localhost:3000`
- [ ] Overview shows 3 devices, 3 zones

### C8. Prepare demo content

The seeded content is generated colour slides for Chandigarh (blue), Delhi (green), Mumbai (red), a grey **Welcome** default, and a red **EMERGENCY ALERT**.
The demo also uses a **Flash Sale** item to show priority overriding location.

1. Go to **Content**.
2. In **Upload**, choose an image (`.jpg` or `.png`) or a short video (`.mp4` or `.webm`, under 90 MB).
3. Set **Display name** to `Flash Sale`. For images set **Seconds** (for example `8`). Videos play to their end.
4. Click **Upload**.

**Do not assign it yet.** You will do that live in the demo (Schedules → new assignment: Flash Sale → Delhi Zone → priority 50).

Optional extras: upload your own city videos and assign them to zones under **Zones & map** or **Schedules**.

- [ ] `Flash Sale` uploaded, not assigned

### C9. Build the display kit

This packages the device agent, start scripts and the display-laptop guide into one zip:

```bash
./scripts/make-device-kit.sh
```

Expected:

```
Created dist/device-kit.zip (24K)
```

The file is `geo-signage/dist/device-kit.zip`. It includes `GUIDE.md`, generated from [Part D](#part-d-display-laptop-setup) of this document, so the display laptops get the right guide without needing this file. Send it to every display laptop (AirDrop, USB, chat, or a shared drive).
It contains **no secrets**. Tokens are sent separately in step 11.

- [ ] `dist/device-kit.zip` exists

### C10. Open the public tunnel

**Do this as late as possible before the demo.** Free tunnels expire (see the note below).

```bash
./scripts/tunnel.sh start
```

The script tests which tunnel works on your network and starts it. Typical output:

```
Network check: using pinggy
Starting Pinggy tunnel to localhost:3000 ...

  Dashboard (open in your browser) : https://abcde-1-2-3-4.free.pinggy.net
  Server URL for display laptops   : https://abcde-1-2-3-4.free.pinggy.net/api

  Notes: free Pinggy tunnels expire after 60 minutes (the URL then changes - run './scripts/tunnel.sh url').
         Browsers see a one-time 'Enter site' notice on the dashboard; display agents are not affected.
```

**Copy the `Server URL for display laptops`.** That, with a device ID and token, is what each laptop needs.

Verify it from your own laptop:

```bash
curl -s https://YOUR-URL.free.pinggy.net/api/health
# {"status":"ok"}
```

| Tunnel | What to know |
|---|---|
| **ngrok** (used automatically when `NGROK_AUTHTOKEN` is set) | Needs a free account. With a **static domain** the URL never changes, so display laptops are set up once. Browsers see a one-time ngrok notice; agents do not. |
| **Cloudflare** (used when port 7844 is open) | No time limit, no warning page, no account. Runs as a Docker container. URL changes if the container is recreated. |
| **Pinggy** (used when Cloudflare's port is blocked) | Free tunnels last **60 minutes**, then the URL changes. Browsers see a one-time **Enter site** page. Agents do not. |

**Optional: a URL that never changes (ngrok, about 5 minutes).**

1. Create a free account at <https://dashboard.ngrok.com/signup> and copy your authtoken (*Your Authtoken* page).
2. Under *Domains*, claim your free static domain, for example `your-name.ngrok-free.app`.
3. Add both to `.env`:
   ```
   NGROK_AUTHTOKEN=your-token
   NGROK_DOMAIN=your-name.ngrok-free.app
   ```
4. Run `./scripts/tunnel.sh start` (it picks ngrok because the token is set) or `./scripts/tunnel.sh start ngrok`.

The server URL for display laptops is then always `https://your-name.ngrok-free.app/api`, across restarts and network changes.
This path was **not** tested end to end (it needs a real account); the missing-token and wrong-token errors were.

Useful tunnel commands:

```bash
./scripts/tunnel.sh url      # show the current URL again
./scripts/tunnel.sh which    # which tunnel `start` would use
./scripts/tunnel.sh stop     # close the tunnel
```

> **If the URL changes** (Pinggy after 60 minutes, or any restart without an ngrok static domain) each display laptop must re-enter it:
> `./start.sh --reset` (or `start.bat --reset`). Plan to start the tunnel within about 20 minutes of presenting, or use an ngrok static domain.

- [ ] Tunnel started, `Server URL` copied
- [ ] `curl .../api/health` returns `{"status":"ok"}`

### C11. Send each display laptop its details

Each display laptop needs the **kit zip** plus **three values**. Copy this message and fill it in for each laptop:

```
Hi! Please set up the display laptop:

1. Unzip device-kit.zip and open GUIDE.md inside it. It is a short step-by-step.
2. Run ./start.sh (Mac/Linux) or double-click start.bat (Windows).
3. When it asks, enter:

   Server URL:          https://abcde-1-2-3-4.free.pinggy.net/api
   Device ID:           DEV-001
   Registration token:  A1B2-C3D4-E5F6

You need Python 3.10+ and internet. Leave the window open once it is running.
```

Do not reuse one Device ID on two laptops. Send the token privately (not in a public chat).

| Laptop | Device ID | Token | Sent? |
|---|---|---|---|
| 1 | `DEV-001` | | ☐ |
| 2 | `DEV-002` | | ☐ |
| 3 | `DEV-003` | | ☐ |

### C12. Confirm the displays are connected

As each laptop starts, watch your dashboard **Overview** (`http://localhost:3000`):

- **Devices online** climbs `1 / 3`, `2 / 3`, `3 / 3`.
- The **Recent activity** feed shows `Device registered` then `Device came online`.
- Click a device in the dark list. Its panel shows **Live push**, its zone, and what it is playing.
- The map dot appears and starts moving (the display laptops follow a simulated road trip).

On each **display laptop** the top-right pill should say **ONLINE - live**.

Terminal view of what your server is doing:

```bash
docker compose logs -f backend      # Ctrl+C to stop watching
```

| Symptom | First thing to check |
|---|---|
| A laptop never appears | Its Server URL, Device ID and token. See the display guide's troubleshooting, or [C16](#c16-troubleshooting). |
| It appears then flips Offline | Two laptops share one Device ID. |
| Shows `Waiting for content` | Online but nothing assigned to its location. Check **Schedules** has a default (Welcome). |

- [ ] All display laptops show **ONLINE - live**
- [ ] Dashboard shows the expected number online

### C13. Rehearse the demo

Run the whole script once with the real laptops before the audience arrives. Full script with timings is in [E2](#e2-demo-script-minute-by-minute). The essentials:

| Step | What to do | You should see |
|---|---|---|
| Geofence switch | On a display press `d`, click **Delhi** | Slide changes within about 3 seconds, event feed shows `Entered zone: Delhi Zone` |
| Default content | `d` → **Jaipur** | The grey **Welcome** slide (outside every zone) |
| Priority override | **Schedules** → new assignment: `Flash Sale`, zone **Delhi Zone**, priority `50` | Display in Delhi switches to Flash Sale. Then **Pause** it and the display goes back. |
| Emergency | **Emergency** → pick the alert → **Send emergency alert** | Every display shows the red **ALERT** with a blinking border. Then **Clear all alerts.** |
| Offline | On one laptop turn Wi-Fi off (or `d` → **Cut network**) | Display keeps playing. Dashboard shows **Offline** after 30–45 seconds. |
| Catch-up | Send an emergency while it is offline, then turn Wi-Fi on | Device reconnects and switches to the alert on its own. |

**After rehearsing, reset the state:**

- Clear any active emergency alert.
- Delete or pause the Flash Sale assignment.
- Put display GPS back on the route (`d` → **Resume route**).

### C14. On the day: run of show

#### 30 minutes before

- [ ] Laptop **plugged in** and set to never sleep. On macOS you can keep it awake from a second terminal: `caffeinate -dims`
- [ ] Turn off notifications and screen savers; connect the projector or screen
- [ ] Wi-Fi stable (a phone hotspot is a good backup)
- [ ] `docker compose ps` shows everything up
- [ ] Dashboard open on **Overview** at `http://localhost:3000`, logged in, browser zoomed so it is readable from the back

#### 15–20 minutes before

- [ ] Start the tunnel: `./scripts/tunnel.sh start` (or `url` if it is already running and recent)
- [ ] If the URL changed since the rehearsal, send it to every display laptop and have them run `./start.sh --reset`
- [ ] All displays show **ONLINE - live**; dashboard shows all devices online
- [ ] No emergency alert active; Flash Sale not assigned

#### During the demo

- Keep the terminal window that started the tunnel open (or leave it in the background). Do not restart the tunnel.
- Use `http://localhost:3000` for your own screen.
- If something looks stuck, click **Force sync** on the device panel. The display also self-repairs within about 5 seconds.

### C15. After the demo: shut down

```bash
./scripts/tunnel.sh stop              # close the public address first
docker compose down                   # stop the server, KEEP the data
# or, to wipe everything (database and uploads):
docker compose down -v
```

Also remind display laptops to press `Ctrl+C` in their window. Their cache is only a few MB and can be deleted with the kit folder.

### C16. Troubleshooting

#### Docker and the server

| Symptom | Cause and fix |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop is not running. Start it and wait for it to say it is running. |
| `port is already allocated` or `address already in use` (3000 or 8000) | Something else, often an old `geo-signage-*` stack, is using it. Run `docker compose --profile sim --profile tunnel down -v`, or set different `FRONTEND_PORT` / `BACKEND_PORT` in `.env`. |
| Build fails while pulling images | No internet or DNS problem. Check the connection and rerun `docker compose up --build -d`. |
| `curl localhost:8000/health` fails | The backend is still starting (give it 30 s), or crashed. Run `docker compose logs backend` and read the last lines. |
| Backend keeps restarting | Usually the database was not ready or `.env` has a bad value. Run `docker compose logs backend db`. Check for a `$` or `#` in `ADMIN_PASSWORD`. |
| Login says "Invalid username or password" | The password in `.env` was changed **after** the database was first created. Passwords are only applied at first creation. Run `docker compose down -v && docker compose up --build -d`. |
| Startup warns about the default password or secret | `.env` was not read. It must sit next to `docker-compose.yml`. Recreate and restart as above. |
| Upload is rejected with "exceeds … MB limit" | The file is larger than `MAX_UPLOAD_MB`. Use a smaller file. |
| Out of disk space during build | Free space, or run `docker system prune` (removes unused Docker data, so check what it lists first). |

#### Tunnel

| Symptom | Cause and fix |
|---|---|
| `Could not get a Pinggy URL` | Port 443 or SSH is blocked on this network. Switch to a phone hotspot. Details: `cat .tunnel/pinggy.log` |
| Cloudflare error **1033** in the browser | Cloudflare's tunnel cannot connect (port 7844 is blocked). Run `./scripts/tunnel.sh stop`, then `./scripts/tunnel.sh start pinggy`. |
| Browser shows a "Caution … pinggy.io" page | Normal for free Pinggy tunnels in a browser. Click **Enter site** once. Display agents are not affected. Use `localhost` on your own machine to avoid it. |
| The tunnel URL suddenly stopped working | Free Pinggy tunnels last 60 minutes. The script reconnects on its own but does not announce the new address. Run `./scripts/tunnel.sh url` to see it, then every display laptop needs `./start.sh --reset`. |
| Laptops cannot reach the server | Test the URL from another device with `curl <URL>/api/health`. Check the tunnel is still running: `./scripts/tunnel.sh url`. |
| `NGROK_AUTHTOKEN is not set` | Add it to `.env` (C10), or use `./scripts/tunnel.sh start pinggy`. |
| `ngrok did not start (ERR_NGROK_…)` | The authtoken or `NGROK_DOMAIN` was rejected. Copy the token again from the ngrok dashboard, and check the domain is on your account. Details: `docker compose --profile ngrok logs ngrok`. |
| `tunnel.sh` hangs or prints nothing | Run it again. If it still hangs, `./scripts/tunnel.sh stop` and start with an explicit type: `./scripts/tunnel.sh start pinggy`. |

#### Devices

| Symptom | Cause and fix |
|---|---|
| Device never registers (`Registration failed (401)`) | Wrong Device ID or token, or the token was re-issued. Send the current token and have them run `./start.sh --reset`. |
| Lost a token | **Devices → open device → Revoke & re-issue token.** Copy the new one immediately. |
| Device flips between Online and Offline | Two laptops use the same Device ID. |
| Offline shows only after ~45 seconds | Expected. That is `OFFLINE_THRESHOLD_SECONDS`. Use the wait to explain heartbeats. |
| Display says `Waiting for content` | Nothing is assigned to that location. Make sure the **Welcome (default)** assignment exists on **Schedules** and is not paused. |
| `docker compose logs backend \| grep "Registration token"` prints nothing | The tokens are only printed the first time the database is created. If the logs are gone, use **Revoke & re-issue token** on each device. |

#### Recover to a known state quickly

```bash
./scripts/tunnel.sh stop
docker compose down -v
docker compose up --build -d
docker compose logs backend | grep "Registration token"     # new tokens
./scripts/tunnel.sh start
```

This gives you a fresh database with fresh tokens. Every display laptop then needs `./start.sh --reset` with the new details.

### C17. Command cheat sheet

Run from the `geo-signage` folder.

| I want to… | Command |
|---|---|
| Start the server | `docker compose up --build -d` |
| See what is running | `docker compose ps` |
| Watch the server log | `docker compose logs -f backend` |
| Show the device tokens | `docker compose logs backend \| grep "Registration token"` |
| Check the API | `curl -s http://localhost:8000/health` |
| Open the dashboard | `http://localhost:3000` |
| API documentation | `http://localhost:8000/docs` |
| Start the public tunnel | `./scripts/tunnel.sh start` |
| Force a specific tunnel | `./scripts/tunnel.sh start ngrok`, `... start pinggy` or `... start cloudflare` |
| See which tunnel would be used | `./scripts/tunnel.sh which` |
| Show the tunnel URL again | `./scripts/tunnel.sh url` |
| Stop the tunnel | `./scripts/tunnel.sh stop` |
| Build the display kit | `./scripts/make-device-kit.sh` |
| Stop the server, keep data | `docker compose down` |
| Stop the server, wipe data | `docker compose down -v` |
| Restart just the backend | `docker compose restart backend` |
| Keep the laptop awake (macOS) | `caffeinate -dims` |

#### Ports and files at a glance

| Item | Where |
|---|---|
| Dashboard (your laptop) | `http://localhost:3000` |
| API and docs | `http://localhost:8000`, `http://localhost:8000/docs` |
| Public address | printed by `./scripts/tunnel.sh start` |
| Secrets | `.env` (never share or commit) |
| Display kit | `dist/device-kit.zip` |
| Tunnel log | `.tunnel/pinggy.log` |
| Login | `admin` and the password from `.env` |

---

## Part D: Display laptop setup

> This part is shipped inside `device-kit.zip` as `GUIDE.md` (generated by `scripts/make-device-kit.sh`). Edit it here.

<!-- BEGIN:display-guide -->

This guide turns an ordinary laptop into one signage display. The laptop connects to the presenter's
dashboard over the internet, shows whatever content the dashboard assigns to its location, and
**keeps playing cached content if its internet drops**.

Time needed: about 10 minutes the first time, 30 seconds afterwards.

### D0. What you need

**From the presenter** (three values, usually sent as a message):

| Value | Looks like |
|---|---|
| Server URL | `https://abcde-1-2-3-4.free.pinggy.net` (adding `/api` at the end also works) |
| Device ID | `DEV-001` |
| Registration token | `A1B2-C3D4-E5F6` |

**On your laptop:**

- Windows 10/11, macOS, or Linux
- Internet access (any Wi-Fi or a phone hotspot; no special ports need opening)
- Google Chrome, Microsoft Edge or another Chromium browser
- Python 3.10 or newer (Step 1 covers installing it)
- The `device-kit.zip` file from the presenter

> **One laptop = one Device ID.** Two laptops using the same ID will keep knocking each other offline.

### D1. Install Python (skip if you already have 3.10+)

Check first:

- **macOS / Linux:** open a terminal and run `python3 --version`
- **Windows:** open Command Prompt and run `py -3 --version`

If it prints `Python 3.10` or higher, go to Step 2. Otherwise:

- **Windows:** download from <https://www.python.org/downloads/>, run the installer and **tick "Add python.exe to PATH"** on the first screen, then click *Install Now*.
- **macOS:** download the installer from the same page, or run `brew install python`.
- **Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv python3-pip`

### D2. Unpack the kit

1. Save `device-kit.zip` somewhere easy, such as your Desktop.
2. Unzip it. You get a folder called `device-kit` containing `start.sh`, `start.bat`, `agent.py` and a few other files.

### D3. Start the display

#### Windows

1. Open the `device-kit` folder.
2. Double-click **`start.bat`**.
3. If Windows SmartScreen appears, click **More info → Run anyway**.

#### macOS / Linux

1. Open a terminal in the `device-kit` folder. On macOS, right-click the folder and choose *New Terminal at Folder*.
2. Run:
   ```bash
   ./start.sh
   ```
   If you get "permission denied", run `bash start.sh` instead.

#### First run only: answer three questions

```
Server URL (e.g. https://name.trycloudflare.com/api):   <paste the Server URL>
Device ID (e.g. DEV-001):                                <your Device ID>
Registration token (e.g. A1B2-C3D4-E5F6):                <your token>
```

The answers are saved in a file called `.env`, so next time you just run the start script again.
The script then creates a private Python environment and installs three small libraries (takes 30–60 seconds once).

You should see lines like these:

```
[DEV-001] Server: https://abcde-...pinggy.net/api
[DEV-001] Display page: http://localhost:8101/
[DEV-001] Registered with server as DEV-001
[DEV-001] Downloading Welcome (default) (v1)
```

**Leave this window open.** Closing it stops the display.

### D4. Show the display fullscreen

Your browser opens automatically at **http://localhost:8101**. If it does not, open that address yourself.

- **Fullscreen:** press `F11` (Windows/Linux) or `Ctrl` + `Cmd` + `F` (macOS).
- **Kiosk mode (optional):** open the `.env` file in a text editor, change `KIOSK=0` to `KIOSK=1`, then restart the script. It opens Chrome or Edge fullscreen with no address bar. To leave kiosk mode press `Alt` + `F4` (Windows/Linux) or `Cmd` + `Q` (macOS).

### D5. Check that it works

On the display, look at the two pills:

| Where | What you should see |
|---|---|
| Top right | 🟢 **ONLINE - live** |
| Bottom left | your Device ID, the current zone or reason (for example `DEV-001 \| zone: Delhi Zone`) |

Ask the presenter to look at the dashboard: your device should show **Online** and its content name should match yours.

The display follows a **simulated road trip** (Chandigarh → Delhi → Jaipur → Mumbai) because laptops have no GPS. The content changes as the position crosses each city zone. Jaipur is outside every zone, so you see the default *Welcome* slide there.

### D6. Demo controls (press `d`)

Press **`d`** on the display to show a small control panel:

| Button | What it does |
|---|---|
| **Cut network** | Simulates an internet outage. The pill turns red (*OFFLINE - playing cached content*) and the display keeps playing. The dashboard marks the device offline after roughly 30–45 seconds. |
| **Restore network** | Reconnects, checks for new content and updates the display. |
| **Chandigarh / Delhi / Jaipur / Mumbai** | Jumps the fake GPS to that city and pauses the route. |
| **Resume route / Pause** | Continues or freezes the road trip. |

Press `d` again to hide the panel.

**Real offline test (more convincing):** turn your Wi-Fi off. The display keeps playing. Turn Wi-Fi on again and it reconnects on its own within a few seconds.

### D7. Everyday commands

| I want to… | Do this |
|---|---|
| Start again later | Run `./start.sh` (or double-click `start.bat`) |
| Change the server URL, device ID or token | Run `./start.sh --reset` (or `start.bat --reset`) |
| Change the route | Edit `.env`, for example `ROUTE=delhi,mumbai`. Known places: `chandigarh, delhi, jaipur, mumbai, ahmedabad` |
| Stay in one place | In `.env` set `GPS_MODE=fixed`, `LAT=28.6139`, `LNG=77.2090` |
| Run two displays on one laptop | Copy the folder, give the copy a different `DISPLAY_PORT` (for example `8102`) and a different Device ID |
| Stop | Press `Ctrl` + `C` in the window, or close it |
| Remove everything | Delete the `device-kit` folder |

### D8. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "Python 3.10 or newer is required" | Install Python (Step 1). On Windows make sure "Add python.exe to PATH" was ticked, then reopen the window. |
| "Installing dependencies failed" | No internet, or a company proxy is blocking `pip`. Switch to a phone hotspot and run the script again. |
| `Registration failed (401): Invalid device ID or registration token` | A typo in the ID or token, or the presenter re-issued the token. Get the current one and run `./start.sh --reset`. |
| `Could not reach …/health - continuing anyway` | The Server URL is wrong or the presenter's tunnel has stopped. Check the URL with the presenter. |
| The display was working, then stayed on **OFFLINE** after the presenter restarted things | The tunnel address changed. Free tunnels last 60 minutes. Get the new URL and run `./start.sh --reset`. |
| Screen says **"Waiting for content"** | The device is online but nothing is assigned to its location. Ask the presenter to assign content to a zone, or a default, on the *Schedules* page. |
| Screen is black or shows the browser's error page | The agent is not running. Check the start script's window is still open. |
| Videos play without sound | This is the default. The presenter can switch audio on under *Devices → Remote configuration*. Chrome may also require kiosk mode or one click on the page before it plays sound. |
| "Address already in use" / port 8101 busy | Another program or another display uses it. Set a different `DISPLAY_PORT` in `.env` and open that port instead. |
| A page titled "Caution … served through pinggy.io" appears | Only in a browser pointed at the *dashboard's* tunnel address. Click **Enter site** once. The display at `localhost` never shows it. |
| Two displays flip between online and offline | Two laptops are using the same Device ID. Each laptop needs its own. |

If something else goes wrong, copy the last 10 lines from the start script's window and send them to the presenter.

### D9. Optional: run with Docker instead of Python

If the laptop already has Docker and you would rather not install Python:

```bash
cd device-kit
docker build -t signage-device .
docker run --rm -p 8101:8101 \
  -e SERVER_URL=https://abcde-1-2-3-4.free.pinggy.net \
  -e DEVICE_ID=DEV-001 -e REGISTRATION_TOKEN=A1B2-C3D4-E5F6 \
  -v signage-cache:/app/.cache signage-device
```

Then open <http://localhost:8101> in your browser. The `-v` option keeps the content cache between runs.

### D10. Pre-demo checklist

- [ ] Python 3.10+ works (`python3 --version` or `py -3 --version`)
- [ ] `device-kit` unzipped, and you have your own Device ID and token
- [ ] Ran the start script once with internet, so the first-run setup and content download are done
- [ ] Display shows 🟢 **ONLINE - live** and the presenter sees the device online
- [ ] Browser is fullscreen, and the laptop will not go to sleep (set *never sleep while plugged in*)
- [ ] Laptop is plugged in
- [ ] You know how to cut the network (`d` panel or Wi-Fi switch) for the offline demo

<!-- END:display-guide -->

---

## Part E: Demo

### E1. Slide-by-slide talking points

A compact deck plan. **Left = what is on the slide. Right = what to say.** Roughly 8–9 minutes plus the live demo.

| # | On the slide | Say (about 30–60 seconds each) |
|---|---|---|
| 1 | **Title**: *Geo Signage: content follows location.* Team names. | "Imagine screens in three cities and a van in between. We built the control room that decides what each screen shows based on where it is, and keeps it playing when the internet fails." |
| 2 | **The problem**: three pain points (manual updates, blank screens when offline, no visibility). | "Today someone updates each screen by hand. When a connection drops, the screen goes black. And nobody knows until a customer tells them. We fix all three." |
| 3 | **The loop** diagram (Section 1). | "One loop: position, zone, content, cache, play. Everything else supports that loop." |
| 4 | **Three ideas**: geofence switching · offline caching · live monitoring. | "These are the three things you will see in the demo. If you only remember three things, remember these." |
| 5 | **Architecture** diagram (Section 2). | "React dashboard, one FastAPI backend, Postgres for data, MinIO for media. The display agent connects from the side and only ever dials out." |
| 6 | **How content is chosen**: the three-rule ranking + one example (Section 4). | "Emergency first, then priority, then how specific the match is. Ties become a playlist. Priority beats specificity, which lets an operator override local content everywhere." |
| 7 | **Offline design**: agent box + "browser talks to localhost only". | "The display page is served from the laptop itself, from a disk cache. So an outage changes nothing about playback. It only changes what the dashboard shows." |
| 8 | **Security**: two logins, revocation, upload checks. | "Admins and devices are separate identities. A stolen device can be cut off with one click. Uploads are checked by content, not just by file name." |
| 9 | **Live demo** (Section 10). | "Now let's watch it happen." |
| 10 | **Honest limits and next steps** (Section 11). | "Here is what we would harden next: PostGIS, boundary debouncing, per-device rotating tokens, and a proper key rotation. And here is exactly what we tested and what we did not." |

### E2. Demo script, minute by minute

**Set-up before you start** (do not do this on stage):

- Server running, tunnel started **shortly before** (Pinggy tunnels last 60 minutes).
- Two or three display laptops already running and showing 🟢 **ONLINE - live**.
- The dashboard open on *Overview*, logged in. Click through Pinggy's "Enter site" page **before** the audience arrives.
- One extra image uploaded named something obvious such as **"Flash Sale"**, not yet assigned.
- The display laptops' `d` panel is available in case you need to jump the GPS.

**Total: about 10 minutes.**

| Time | Do | Expect | Say |
|---|---|---|---|
| **0:00** | Show *Overview*. Point at the four cards and the device list. | 3 devices online, live map with three coloured zones and green dots, "Recent activity" filling. | "This is the control room. Three displays, all online. The dots on the map are their real-time positions, and the coloured circles are the geofences." |
| **1:00** | Click **DEV-001** in the dark device list. | Violet detail panel slides in: zone, now playing, GPS, CPU, memory, "Live push". | "Every device reports its own health, location and what it is playing, and we can send it commands from here." |
| **1:45** | Turn to the **display laptop for DEV-001** (the van). Let it run. | Screen shows the current city slide with a status pill (`ONLINE - live`) and zone name. | "This is the actual display. It is a separate laptop on a different network. It is following a simulated road trip." |
| **2:15** | Wait for or trigger the crossing: on the display press `d`, click **Delhi**. | Within about 3 s the slide changes from the Chandigarh slide (blue) to the Delhi slide (green). On the dashboard the dot jumps, the event feed shows **"Entered zone: Delhi Zone"**, and the detail panel updates. | "The van crossed into Delhi. Nobody changed anything. The server saw the position, found the zone, and the screen followed within seconds." |
| **3:15** | Press `d` → **Jaipur**. | A **Welcome** default slide (Jaipur is outside every zone). | "Outside every zone it falls back to the default content. So there is never an empty screen." |
| **3:45** | On the dashboard open **Schedules**, create an assignment: *Flash Sale* to **Delhi Zone**, priority **50**. Move the display back to **Delhi**. | Display switches to *Flash Sale* almost at once. | "Priority beats location, so we can override a whole zone with one rule. Priority 50 beat the Delhi slide at 10. We can also give it a time window, including ones that cross midnight." |
| **4:45** | Pause that assignment (button in the table). | Display returns to the Delhi slide. | "Pause it and it goes back." |
| **5:15** | Open **Emergency**, pick the alert, target **all zones**, **Send emergency alert**. | Every display flips to the red **ALERT** slide with a blinking red border. Dashboard shows **"1 alert live"**. | "Emergency beats everything. All screens, all zones, immediately over the live connection." |
| **6:00** | **Clear all alerts.** | Screens return to their normal content. | "And cleared." |
| **6:15** | **Offline demo.** On one display laptop switch Wi-Fi **off** (or `d` → **Cut network**). Keep talking. | The display keeps playing; its pill turns red: *OFFLINE - playing cached content*. After **30–45 s** the dashboard shows the device **Offline**, the bell gets a red dot, and the feed says *"No heartbeat received - device offline"*. | "I just cut this laptop's internet. Look at the screen. It has not blinked. It is playing from its own cache. The dashboard takes about half a minute to notice, because we wait for missed heartbeats before raising an alarm." |
| **7:15** | While it is offline, trigger the **emergency alert** again for all zones. | The online displays change. The offline one does **not**. | "A screen that is offline cannot receive new instructions, and it says so. It shows the last thing it knew." |
| **7:45** | Turn Wi-Fi **on** (or `d` → **Restore network**). | Within a few seconds: pill turns green, the offline screen switches to the alert, dashboard shows **Online** and *"Device came online"*. | "Network back. It reconnected on its own, saw it had missed something, and caught up. No one touched it." Clear the alert. |
| **8:30** | Open **Monitoring**. | Fleet health table (CPU, memory, heartbeat age), content views, uptime per device, zone visits, full event log. | "Everything that happened is recorded. Uptime, how many times each item played, which zones each device visited." |
| **9:15** | Optionally show **Users → Change my password**. | Password card. | "And because the demo is public, admin credentials can be changed from here." |
| **9:30** | Back to slides: honest limits and next steps. | | "That is the demo. Here is what is still ahead of us." |

#### If something goes wrong

| Problem | Recovery |
|---|---|
| Display does not change after the GPS jump | Wait 5 s. The polling fallback catches it. Then use **Force sync** on the device panel. |
| The dashboard still shows online after Wi-Fi off | Normal for up to 45 s. Keep talking. Use the time to explain heartbeats. |
| A display stays blank ("Waiting for content") | It is online but nothing matches. Check that a default assignment exists. |
| The tunnel URL stopped working | Free Pinggy tunnels last 60 minutes. Run `./scripts/tunnel.sh url`. If it changed, each laptop needs `./start.sh --reset`. **Start the tunnel just before presenting to avoid this.** |
| Every display went offline at once | The internet or the tunnel dropped. Displays keep playing, which is itself a demonstration of the offline design. |

---

## Part F: Questions and honesty

### F1. Likely judge questions

| Question | Honest answer |
|---|---|
| **How does it scale?** | It has not been load-tested, and it is a single backend process. Rough arithmetic: 1,000 devices reporting every 3 seconds is about 330 location requests per second, each running a few database queries and loading all zones and assignments. That would need indexing, caching the resolved result per device, and PostGIS. The WebSocket hub is in memory, so running several backend instances would also need a shared broker such as Redis. It is designed for tens to low hundreds of devices as built. |
| **Why not PostGIS?** | Point-in-polygon is a small function (`services/geo.py`, ray casting) and zones are stored as JSON, which kept setup simple. It is fine for a few hundred zones. For thousands of zones, or radius queries, we would move to PostGIS with a spatial index. |
| **How accurate is the GPS?** | Our demo uses **simulated** GPS, because the laptops have none. Real receivers are roughly 5–10 m accurate in the open and worse between buildings. Our zones are large circles (30–40 km), so error does not matter here. For small zones, such as a single shop, we would need to handle boundary jitter, see the next row. |
| **What happens right on a zone boundary?** | We do **not** debounce. A device hovering on a border could flip content back and forth with each reading. The fix is hysteresis: require the new zone for several consecutive readings or a minimum time. Not built yet. |
| **What if the server goes down?** | Displays keep playing their cached playlist. They retry, and resync when it returns. New instructions cannot arrive until then. |
| **What if MinIO or the database fails?** | Already-cached content keeps playing. New downloads and dashboard actions fail until it recovers. There is no replication in this prototype. |
| **What if a device restarts while offline?** | The manifest and cached files are stored on disk and reloaded, so it should resume playing. We designed for this but did not test it. |
| **Is a stolen device a risk?** | An admin can revoke it in one click (token version bump). Its credentials stop working immediately. But: **registration tokens are reusable** until rotated, so if the token itself leaks, someone can register as that device. A production version would make registration tokens single-use and expiring. |
| **Is it secure enough to be public?** | For a short demo, with the changes described in Section 6. Not for production: WebSocket tokens are in the URL, login throttling is per username in memory, and CORS is open. |
| **Why a tunnel and not a cloud deploy?** | Speed and cost for a demo: no accounts, no infrastructure. A production deploy would be a small VM or a container service with a real domain and TLS. |
| **Why three tunnel options?** | Cloudflare needs outbound port 7844 and our network blocks it. Pinggy needs only 443 but its free URL changes hourly. ngrok gives a fixed URL with a free account. The script picks: ngrok if configured, otherwise whichever the network allows. |
| **How do you handle schema changes?** | We don't yet. Tables are created at startup with no migrations, so a model change means resetting the database. A production version would use Alembic. |
| **What would you do next?** | (1) PostGIS and a resolved-content cache; (2) boundary hysteresis; (3) single-use, expiring registration tokens and key rotation; (4) migrations; (5) a real GPS and a Raspberry Pi test; (6) remote screenshots and OTA agent updates from the original plan; (7) playlist transitions and per-item scheduling. |
| **Which planned features did you skip?** | MQTT, remote screenshots, OTA updates, route-based targeting, and PostGIS. Everything in the original "must have" list and most of "should have" is built. |

#### Side by side

| On screen | Say |
|---|---|
| A slide titled **"What we'd do next"** with the numbered list | "We would rather tell you the limits than have you find them. Scaling, boundary jitter, single-use tokens and migrations are the four things we would fix first." |
| The scaling row | "Built for tens of devices, not thousands. We did the arithmetic but have not load-tested it." |
| The reusable-token row | "If the registration token leaks, someone could register as that device. Revoking is instant, but single-use tokens are the real fix." |

### F2. What was tested and what was not

**Do not claim anything from the second list.**

#### Tested

| Area | How | Result |
|---|---|---|
| Backend logic | **14 automated tests** (`pytest`) | Pass: geofencing, time windows including midnight, priority, emergency, scheduling and pause, device auth, revocation, cross-use of tokens, offline detection, upload validation, media range requests, viewer read-only role, password change, timeline series |
| Live device loop | Real agent processes against a running server | Geofence switching (Chandigarh → default → Delhi → Mumbai), impressions reported, dashboard events |
| Offline and reconnect | Simulated network cut on a running agent | Display kept playing, server marked device offline, an emergency sent during the outage was applied on reconnect |
| Full Docker stack | `docker compose --profile sim up` | Postgres, MinIO, nginx and three simulated devices all working together |
| Video path | A real WebM clip uploaded, stored in MinIO, played by the display page | Playlist rotated image to video with no error |
| Dashboard | Automated headless Chromium on every page | No console errors; page transitions measured (old page fades out, new one fades in); modals open centred and close on Escape |
| Public tunnel (Pinggy) | Isolated Docker project, real tunnel | Dashboard loaded over HTTPS with a working secure WebSocket; agent registered with a **random** token through the tunnel; old default password rejected |
| Display kit | Zip built, unzipped in a clean folder, `start.sh` run with prompts answered | First-run prompts, `.env`, private virtual environment, dependency install, registration, live WebSocket |
| Wrong-token feedback | Agent started with a bad token | A clear warning is shown |
| Code reorganisation | 21-step browser regression: every page, creating and deleting a device and a zone through the UI, an emergency alert reaching a live display and clearing again, the page transition; plus 14 backend tests and linting | Pass |
| Tunnel script | Pinggy start, `url` and `stop` through the rewritten script with a health check through the tunnel; provider auto-selection; ngrok with a wrong token against the real ngrok container | Pass |
| Query cost | SQL statements per location update, before and after the refactor | 5 to 4 |

#### Not tested (be careful)

| Area | Status |
|---|---|
| **Multi-laptop use** | The display kit and the tunnel were only verified **from one machine**. No second physical laptop was used. |
| **Windows** (`start.bat`) | Written, never run. |
| **ngrok success path** | Never connected: it needs an ngrok account. Only the missing-token and wrong-token errors ran. |
| **Cloudflare tunnel connecting** | Never connected: blocked on the network we used. Only the fallback path was proven. |
| **Pinggy after 60 minutes** | The expiry and URL change were not waited out. |
| **Kiosk mode** (`KIOSK=1`) | Not run. |
| **Docker device image** (`device/Dockerfile`) | Not run. |
| **Real GPS** (gpsd) | Not run; all location is simulated. |
| **Raspberry Pi** | Never run on one. |
| **Restart while offline** | Designed to resume from the cache; not exercised. |
| **H.264 MP4 playback** | Only WebM playback was exercised in the headless browser; MP4 depends on the browser's codecs. |
| **Load and scale** | No load test of any kind. |
| **Other browsers and phones** | Only headless Chromium was used for the dashboard. |
| **Long-running stability** | Nothing ran for hours. |

#### One-sentence honest summary

> "The whole system works end to end and is covered by automated tests; we proved the public-tunnel path from a single machine,
> and have not yet run it on multiple physical laptops, on Windows, or at scale."

---

## Part G: Reference

### G1. Environment variables

**Server (`docker-compose.yml` and `.env`)**

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | built-in dev value (warns) | Signs JWTs. Set a long random value. |
| `ADMIN_PASSWORD` | `admin123` (warns) | Password of the seeded `admin`. Only applied when the database is first created. |
| `FIXED_DEMO_TOKENS` | `1` | `1` = seeded devices use `DEMO-REG-001..003`. `0` = random tokens printed once in the backend log. |
| `MAX_UPLOAD_MB` | `100` | Largest upload. |
| `OFFLINE_THRESHOLD_SECONDS` | `30` | Silence before a device is marked offline. |
| `FRONTEND_PORT`, `BACKEND_PORT` | `3000`, `8000` | Host ports. |
| `NGROK_AUTHTOKEN`, `NGROK_DOMAIN` | empty | ngrok tunnel (optional). |

**Backend (`backend/app/config.py`)**

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./signage.db` | Docker sets a PostgreSQL URL. |
| `STORAGE_BACKEND` | `local` | `local` or `minio` (Docker uses `minio`). |
| `LOCAL_STORAGE_DIR` | `./media_store` | Media folder for the `local` backend. |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE` | `localhost:9000`, `minioadmin`, `minioadmin`, `signage-media`, `0` | Object storage. |
| `ADMIN_TOKEN_MINUTES`, `DEVICE_TOKEN_DAYS` | `720`, `30` | Login token lifetimes. |
| `DEFAULT_ADMIN_USER`, `DEFAULT_ADMIN_PASSWORD` | `admin`, `admin123` | Seeded account (Compose maps `ADMIN_PASSWORD` here). |
| `SEED_DEMO_DATA` | `1` | Seed devices, zones and slides on first start. |
| `MONITOR_INTERVAL_SECONDS` | `5` | How often the offline sweep runs. |
| `SCHEDULE_TZ_OFFSET_MINUTES` | `330` | Offset (IST) used for `HH:MM` schedule windows. |

**Device agent (`device/.env`, written by `start.sh` / `start.bat`)**

| Variable | Default | Meaning |
|---|---|---|
| `SERVER_URL` | `http://localhost:8000` | Backend, tunnel root, or tunnel root plus `/api`. |
| `DEVICE_ID`, `REGISTRATION_TOKEN` | required | Identity from the dashboard. |
| `DISPLAY_PORT` | `8101` | Port of the local display page. |
| `GPS_MODE` | `sim` | `sim`, `fixed` or `gpsd`. |
| `ROUTE`, `ROUTE_STEPS`, `ROUTE_DWELL` | `chandigarh,delhi,jaipur,mumbai`, `10`, `5` | Simulated road trip. Places: chandigarh, delhi, jaipur, mumbai, ahmedabad. |
| `LAT`, `LNG` | `28.6139`, `77.2090` | Position for `GPS_MODE=fixed`. |
| `OPEN_BROWSER`, `KIOSK` | off | Open the display page; `KIOSK=1` opens Chrome or Edge fullscreen. |

### G2. API surface

Admin endpoints need `Authorization: Bearer <admin token>` (write actions need the `admin` role). Device endpoints need a device token.
Through nginx everything is under `/api`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Users | `GET/POST /users`, `POST /users/me/password`, `DELETE /users/{id}` |
| Devices | `GET/POST /devices`, `GET/PUT/DELETE /devices/{device_id}`, `POST /devices/{id}/rotate-token`, `POST /devices/{id}/sync`, `GET /devices/{id}/logs` |
| Groups | `GET/POST /groups`, `DELETE /groups/{id}` |
| Content | `GET /content`, `POST /content/upload`, `PUT /content/{id}`, `POST /content/{id}/replace`, `DELETE /content/{id}`, `GET /content/{id}/file` (`?token=` allowed for media tags) |
| Zones | `GET/POST /zones`, `PUT/DELETE /zones/{id}` |
| Assignments | `GET/POST /assignments`, `PUT/DELETE /assignments/{id}`, `POST /zones/{id}/content`, `DELETE /zones/{id}/content/{content_id}` |
| Emergency | `GET/POST/DELETE /emergency` |
| Monitoring | `GET /monitoring/overview`, `/monitoring/logs`, `/monitoring/analytics`, `/monitoring/timeline` |
| Device agent | `POST /device/register`, `/device/heartbeat`, `/device/location`, `/device/impressions`; `GET /device/{id}/configuration`, `/device/{id}/content`, `/device/{id}/media/{content_id}` |
| Realtime | `WS /ws/admin?token=`, `WS /ws/device/{id}?token=` |
| Health | `GET /health`; interactive docs at `http://localhost:8000/docs` |

### G3. Ports and files

| Item | Where |
|---|---|
| Dashboard | `http://localhost:3000` |
| API and docs | `http://localhost:8000`, `http://localhost:8000/docs` |
| Simulated displays (`sim` profile) | `http://localhost:8101`, `8102`, `8103` |
| Secrets | `.env` (never share or commit) |
| Display kit | `dist/device-kit.zip` |
| Tunnel state and log | `.tunnel/` |
