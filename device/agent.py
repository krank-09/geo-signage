"""Digital-signage device agent.

Register -> heartbeat + report GPS -> receive content decisions from the server (WebSocket push with
polling fallback) -> download into a local cache -> serve a kiosk display page from that cache.
If the network or server disappears the agent keeps serving the last cached playlist and resyncs on reconnect.

Run:  python agent.py --server http://localhost:8000 --device-id DEV-001 --token DEMO-REG-001 \
                      --route chandigarh,delhi,jaipur,mumbai --port 8101

Every option can also come from environment variables or a `.env` file next to this script
(SERVER_URL, DEVICE_ID, REGISTRATION_TOKEN, DISPLAY_PORT, GPS_MODE, PLACE, ROUTE, ROUTE_STEPS, ROUTE_DWELL, LAT, LNG,
OPEN_BROWSER, KIOSK, DEMO_CONTROLS, DISPLAY_BIND) - see .env.example. `./start.sh` / `start.bat` wrap all of this for display laptops.
"""
import argparse
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import psutil
import requests
import websocket
from bootstrap import detect_server, load_dotenv, open_display
from cache import Cache
from discovery import discover, load_identity
from display_server import make_server
from gps import FixedGPS, GpsdGPS, SimulatedGPS, place_coords
from identity import Identity, code_hash, file_sha256, hw_fingerprint, system_info, verify_manifest

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"), encoding="utf-8") as _f:
    VERSION = _f.read().strip()
CAPABILITIES = ["signed-requests", "signed-manifests", "media-hash", "state-mac", "tamper-report"]
CLOCK_ROLLBACK_SECONDS = 120
VERIFY_EVERY = 60
log = logging.getLogger("agent")


class Offline(Exception):
    pass


class DeviceAgent:
    def __init__(self, server, device_id, reg_token, gps, cache_dir, poll_interval=5):
        self.server = server.rstrip("/")
        self.device_id = device_id
        self.reg_token = reg_token
        self.gps = gps
        self.lock = threading.RLock()
        self.hb_event = threading.Event()  # wake heartbeat early (e.g. right after a content change)
        self.identity = Identity(cache_dir)
        self._code_hash = code_hash()
        self.cache = Cache(cache_dir, identity=self.identity)
        self.poll_interval = poll_interval
        self.boot_id = secrets.token_hex(8)
        self.control_token = os.getenv("CONTROL_TOKEN") or secrets.token_urlsafe(24)   # protects /api/control on this machine
        self.demo_controls = os.getenv("DEMO_CONTROLS", "").strip().lower() in ("1", "true", "yes", "on")
        self.tamper_queue: list[dict] = []
        self._tamper_seen: dict[str, float] = {}

        state = self.cache.load_state()
        self.token = state.get("token")
        self.server_key = state.get("server_key")      # pinned at first registration
        self.tamper_queue = state.get("tamper_queue") or []
        if self.cache.state_tampered:
            self.report_tamper("config_tampered", "Saved state failed its integrity check; starting clean")
        self._check_restart(state)
        self.manifest = state.get("manifest") or {"manifest_version": None, "items": [], "zone": None}
        self.config = state.get("config") or {"heartbeat_interval": 10, "location_interval": 3, "mute": True, "fit": "contain"}

        self.sim_offline = False  # simulated network cut (demo control)
        self.connected = False  # last server call succeeded
        self.ws_connected = False
        self.last_sync = None
        self.position = None
        self.server_manifest_version = self.manifest.get("manifest_version")
        self.broadcasts: list[dict] = []  # live announcements; each has a local `deadline` (None = until ended)
        self.impressions: list[dict] = []
        self.sync_event = threading.Event()
        self.stop = threading.Event()
        self.http = requests.Session()
        self.http.headers["ngrok-skip-browser-warning"] = "1"  # harmless elsewhere; avoids ngrok's browser notice
        self.reg_lock = threading.Lock()  # registration rotates credentials, so only one thread may do it at a time

    # ------------------------------------------------------------------ network helpers
    def _headers(self, method="GET", path="", body=b""):
        h = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return {**h, **self.identity.sign_headers(method, path, body)}

    # ------------------------------------------------------------------ tamper reporting
    def report_tamper(self, kind, detail):
        """Queue a detection for the server (kept on disk until delivered) and log it. Repeats within a minute are one incident."""
        now = time.time()
        if now - self._tamper_seen.get(kind + detail[:40], 0) < 60:
            return
        self._tamper_seen[kind + detail[:40]] = now
        log.warning("TAMPER DETECTED [%s] %s", kind, detail)
        with self.lock:
            self.tamper_queue.append({"kind": kind, "detail": detail[:500], "at": datetime.now(timezone.utc).isoformat()})
            del self.tamper_queue[:-50]
        try:
            self.cache.save_state(tamper_queue=self.tamper_queue)
        except OSError:
            pass
        self.hb_event.set()

    def _flush_tamper(self):
        with self.lock:
            batch = list(self.tamper_queue[:50])
        if not batch:
            return
        r = self._request("POST", "/device/tamper", json={"events": batch})
        if r.status_code == 200:
            with self.lock:
                del self.tamper_queue[: len(batch)]
            self.cache.save_state(tamper_queue=self.tamper_queue)

    def _check_restart(self, state):
        """A start with the 'running' marker still present means the last run did not shut down cleanly."""
        marker = os.path.join(self.cache.root, "running")
        if os.path.exists(marker):
            self.report_tamper("unexpected_restart", "The agent was not shut down cleanly (power cut, kill or crash)")
        with open(marker, "w", encoding="ascii") as f:
            f.write(self.boot_id)
        last = state.get("last_clock")
        if last and time.time() < last - CLOCK_ROLLBACK_SECONDS:
            self.report_tamper("clock_rollback", f"System clock is {int(last - time.time())}s behind where it was before the restart")

    def _watch_clock(self):
        last = getattr(self, "_last_clock", None)
        now = time.time()
        if last and now < last - CLOCK_ROLLBACK_SECONDS:
            self.report_tamper("clock_rollback", f"System clock moved back {int(last - now)}s")
        self._last_clock = now
        self.cache.save_state(last_clock=now)

    def _inventory(self):
        return {**system_info(), "software_version": VERSION, "capabilities": CAPABILITIES, "code_hash": self._code_hash, "boot_id": self.boot_id}

    def _learn_clock(self, r):
        """Sign with the server's idea of time, so a wrong local clock does not lock this display out."""
        try:
            self.identity.clock_offset = parsedate_to_datetime(r.headers["Date"]).timestamp() - time.time()
        except (KeyError, TypeError, ValueError):
            pass

    def _request(self, method, path, retry_auth=True, **kw):
        if self.sim_offline:
            self.connected = False
            raise Offline("simulated network outage")
        if not self.token and path != "/device/register":
            self.register()
        body = b""
        if "json" in kw:
            body = json.dumps(kw.pop("json")).encode()
            kw["data"] = body
        try:
            r = self.http.request(method, self.server + path, headers={**self._headers(method, path, body), "Content-Type": "application/json"},
                                  timeout=6, **kw)
        except requests.RequestException as e:
            self.connected = False
            raise Offline(str(e))
        self._learn_clock(r)
        if r.status_code == 401 and retry_auth and path != "/device/register":
            log.warning("Token rejected (revoked/expired) - re-registering")
            self.register(stale=self.token)
            return self._request(method, path, retry_auth=False, **kw)
        self.connected = True
        return r

    def register(self, stale=None):
        with self.reg_lock:
            if self.token and self.token != stale:
                return  # another thread already (re-)registered
            self._register()

    def _register(self):
        r = self._request("POST", "/device/register", retry_auth=False, json={
            "device_id": self.device_id, "registration_token": self.reg_token, "public_key": self.identity.public_b64,
            "hw_fingerprint": hw_fingerprint(), **self._inventory()})
        if r.status_code != 200:
            if time.time() - getattr(self, "_reg_warned", 0) > 30:  # visible, but not every retry
                self._reg_warned = time.time()
                try:
                    detail = r.json().get("detail", r.text)
                except ValueError:
                    detail = r.text[:120]
                if r.status_code == 409:
                    log.error("%s In the dashboard open the device and choose 'Rotate token', then run ./start.sh --reset with the new token.", detail)
                else:
                    log.warning("Registration failed (%s): %s - check the Device ID and token (run start.sh --reset to re-enter)", r.status_code, detail)
            raise Offline(f"registration failed: {r.status_code}")
        body = r.json()
        self.token = body["access_token"]
        self.config = body["config"]
        key = body.get("server_public_key")
        if key and not self.server_key:
            self.server_key = key                 # trust on first use; from now on only playlists signed by this key play
        elif key and key != self.server_key:
            self.report_tamper("manifest_signature_invalid", "The server's signing key changed since this display was set up "
                                                             "(use ./start.sh --reset if the server was rebuilt on purpose)")
        self.cache.save_state(token=self.token, config=self.config, server_key=self.server_key)
        log.info("Registered with server as %s", self.device_id)

    # ------------------------------------------------------------------ sync (content decision -> local cache)
    def sync(self):
        r = self._request("GET", f"/device/{self.device_id}/content")
        if r.status_code != 200:
            raise Offline(f"content fetch failed: {r.status_code}")
        remote = r.json()
        if self.server_key:
            try:
                signed = verify_manifest(remote["signed"], self.server_key, self.device_id) if remote.get("signed") else None
                if signed is None:
                    raise ValueError("playlist arrived without a signature")
            except ValueError as e:
                self.report_tamper("manifest_signature_invalid", str(e))
                raise Offline("rejected an unsigned or wrongly signed playlist; keeping the last good one")
            remote = signed                       # only the signed content is used
        self.config = remote["config"]
        items = remote["items"]
        now = time.time()
        self.broadcasts = [
            {**b, "deadline": None if b["remaining_seconds"] is None else now + b["remaining_seconds"]}
            for b in remote.get("broadcasts", [])
        ]
        for item in items:
            if not self.cache.has(item):
                self._download(item)
            elif item.get("sha256") and not self._intact(item):
                self._download(item)
        keep = {self.cache.filename(i) for i in items}
        with self.lock:
            changed = remote["manifest_version"] != self.manifest.get("manifest_version")
            self.manifest = {k: remote[k] for k in ("manifest_version", "zone", "reason", "emergency", "items")}
            self.server_manifest_version = remote["manifest_version"]
            self.last_sync = time.time()
        self.cache.save_state(manifest=self.manifest, config=self.config)
        self.cache.gc(keep)
        if changed:
            self.hb_event.set()
            log.info("Content updated -> %s (%s)", ", ".join(i["name"] for i in items) or "nothing", remote["reason"])

    def _download(self, item):
        name = self.cache.filename(item)
        tmp = self.cache.new_tmp(name)
        log.info("Downloading %s (v%s)", item["name"], item["version"])
        if self.sim_offline:
            raise Offline("simulated network outage")
        try:
            with self.http.get(self.server + item["url"], headers=self._headers("GET", item["url"]), stream=True, timeout=15) as r:
                if r.status_code != 200:
                    raise Offline(f"download failed: {r.status_code}")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        f.write(chunk)
        except requests.RequestException as e:
            raise Offline(str(e))
        want = item.get("sha256")
        if want and file_sha256(tmp) != want:
            os.remove(tmp)
            self.report_tamper("media_hash_mismatch", f"{item['name']} did not match the signed hash; download discarded")
            raise Offline("downloaded media failed its integrity check")
        self.cache.commit(tmp, name)

    def _intact(self, item):
        """True if the cached file still matches the hash the server signed. A changed file is deleted and reported."""
        name = self.cache.filename(item)
        p = self.cache.path(name)
        if p and file_sha256(p) == item["sha256"]:
            return True
        if p:
            self.cache.remove(name)
            self.report_tamper("cache_tampered", f"{item['name']} in the local cache was modified; removed and re-downloading")
        return False

    def verify_loop(self):
        """Re-check the cached files against the signed hashes now and then, so a file swapped while the display is running
        (or while it is offline) is removed before it can play again."""
        while not self.stop.wait(VERIFY_EVERY):
            try:
                with self.lock:
                    items = [i for i in self.manifest.get("items", []) if i.get("sha256") and self.cache.has(i)]
                bad = [i for i in items if not self._intact(i)]
                if bad:
                    self.sync_event.set()
                if code_hash() != self._code_hash:
                    self.report_tamper("code_modified", "The agent's own files changed while it was running")
                    self._code_hash = code_hash()
            except Exception:
                log.exception("integrity check failed")

    def sync_loop(self):
        while not self.stop.is_set():
            self.sync_event.wait(self.poll_interval)  # push wakes us early; otherwise poll as a fallback
            self.sync_event.clear()
            if self.stop.is_set():
                return
            try:
                if not self.token:
                    self.register()
                self.sync()
            except Offline as e:
                log.debug("sync deferred: %s", e)
            except Exception:
                log.exception("sync failed")

    # ------------------------------------------------------------------ heartbeat / location
    def _note_server_state(self, body):
        self.config = body.get("config", self.config)
        if body.get("manifest_version") != self.server_manifest_version:
            self.server_manifest_version = body.get("manifest_version")
            self.sync_event.set()  # location change or admin edit -> fetch the new playlist now

    def heartbeat_loop(self):
        psutil.cpu_percent(None)
        while not self.stop.is_set():
            try:
                if not self.token:
                    self.register()
                with self.lock:
                    names = ", ".join(i["name"] for i in self.manifest["items"])
                    ver = self.manifest.get("manifest_version")
                    pos = self.position
                payload = {
                    "cpu": psutil.cpu_percent(None), "memory": psutil.virtual_memory().percent,
                    "network": "connected", "gps": pos is not None, "content_version": ver or "",
                    "content_names": names, **self._inventory(),
                }
                self._watch_clock()
                r = self._request("POST", "/device/heartbeat", json=payload)
                if r.status_code == 200:
                    self._note_server_state(r.json())
                self._flush_impressions()
                self._flush_tamper()
            except Offline as e:
                log.debug("heartbeat failed: %s", e)
            self.hb_event.wait(self.config.get("heartbeat_interval", 10))
            self.hb_event.clear()

    def location_loop(self):
        while not self.stop.is_set():
            pos = self.gps.read()
            with self.lock:
                self.position = pos
            if pos:
                try:
                    r = self._request("POST", "/device/location", json={"latitude": pos[0], "longitude": pos[1], "device_id": self.device_id})
                    if r.status_code == 200:
                        self._note_server_state(r.json())
                except Offline:
                    pass
            self.stop.wait(self.config.get("location_interval", 3))

    def ws_loop(self):
        backoff = 1
        while not self.stop.is_set():
            if not self.token or self.sim_offline:
                self.ws_connected = False
                self.stop.wait(1)
                continue
            url = self.server.replace("http", "ws", 1) + f"/ws/device/{self.device_id}?token={self.token}"
            try:
                ws = websocket.create_connection(url, timeout=10, header=["ngrok-skip-browser-warning: 1"])
                ws.settimeout(1)
                self.ws_connected, backoff = True, 1
                while not self.stop.is_set() and not self.sim_offline:
                    try:
                        msg = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not msg:
                        break
                    if json.loads(msg).get("type") == "sync":
                        self.sync_event.set()
                ws.close()
            except Exception as e:
                log.debug("ws error: %s", e)
            self.ws_connected = False
            self.stop.wait(backoff)
            backoff = min(backoff * 2, 15)

    # ------------------------------------------------------------------ impressions (buffered while offline)
    def record_impression(self, data):
        try:
            entry = {"content_id": int(data["content_id"]), "duration": float(data.get("duration", 0)),
                     "zone_id": (self.manifest.get("zone") or {}).get("id"),
                     "started_at": data.get("started_at") or datetime.now(timezone.utc).isoformat()}
        except (KeyError, ValueError, TypeError):
            return
        with self.lock:
            self.impressions.append(entry)
            del self.impressions[:-1000]

    def _flush_impressions(self):
        with self.lock:
            batch = self.impressions[:200]
        if not batch:
            return
        r = self._request("POST", "/device/impressions", json={"items": batch})
        if r.status_code == 200:
            with self.lock:
                del self.impressions[: len(batch)]

    # ------------------------------------------------------------------ display + demo controls
    def display_state(self):
        with self.lock:
            m = self.manifest
            items = [{**i, "src": "/media/" + self.cache.filename(i)} for i in m.get("items", []) if self.cache.has(i)]
            return {
                "device_id": self.device_id, "online": self.connected and not self.sim_offline,
                "sim_offline": self.sim_offline, "ws": self.ws_connected,
                "manifest_version": m.get("manifest_version"), "zone": m.get("zone"), "reason": m.get("reason"),
                "emergency": bool(m.get("emergency")), "items": items, "config": self.config,
                "broadcasts": [{k: b[k] for k in ("id", "message", "style", "severity")} for b in self.broadcasts
                               if b["deadline"] is None or b["deadline"] > time.time()],
                "position": self.position, "pending_impressions": len(self.impressions),
                "last_sync": self.last_sync, "moving": getattr(self.gps, "moving", None),
                "demo_controls": self.demo_controls, "control_token": self.control_token if self.demo_controls else None,
                "tamper_pending": len(self.tamper_queue), "version": VERSION,
            }

    def control(self, data):
        if not self.demo_controls:
            return {"ok": False, "error": "demo controls are switched off (set DEMO_CONTROLS=1)"}
        if "offline" in data:
            self.sim_offline = bool(data["offline"])
            log.info("Simulated network %s", "CUT" if self.sim_offline else "RESTORED")
            if not self.sim_offline:
                self.sync_event.set()
        if "goto" in data and isinstance(self.gps, SimulatedGPS):
            if not self.gps.goto(str(data["goto"])):
                return {"ok": False, "error": "unknown place"}
        if "moving" in data and isinstance(self.gps, SimulatedGPS):
            self.gps.set_moving(bool(data["moving"]))
        return {"ok": True, "sim_offline": self.sim_offline, "moving": getattr(self.gps, "moving", None)}

    def run(self, port, open_url=None, kiosk=False):
        srv = make_server(self, port)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("Display page: http://localhost:%d/   (press 'd' on it for demo controls)", port)
        for fn in (self.sync_loop, self.heartbeat_loop, self.location_loop, self.ws_loop, self.verify_loop):
            threading.Thread(target=fn, daemon=True).start()
        self.sync_event.set()
        if open_url:
            open_display(open_url, kiosk)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()
        finally:
            try:
                os.remove(os.path.join(self.cache.root, "running"))   # a clean stop, so the next start is not reported
            except OSError:
                pass


def build_gps(args):
    if args.gps == "gpsd":
        return GpsdGPS()
    if args.gps == "fixed":
        return FixedGPS(*place_coords(args.place)) if args.place else FixedGPS(args.lat, args.lng)
    return SimulatedGPS(args.route.split(","), steps=args.steps, dwell=args.dwell, loop=not args.no_loop)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    p = argparse.ArgumentParser(description="Geo signage device agent")
    p.add_argument("--server", default=os.getenv("SERVER_URL", "http://localhost:8000"))
    p.add_argument("--device-id", default=os.getenv("DEVICE_ID"),
                   help="omit (with --token) to let the dashboard find and claim this display (discovery mode)")
    p.add_argument("--token", default=os.getenv("REGISTRATION_TOKEN"), help="registration token issued by the admin dashboard")
    p.add_argument("--port", type=int, default=int(os.getenv("DISPLAY_PORT", 8101)))
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--gps", choices=["sim", "fixed", "gpsd"], default=os.getenv("GPS_MODE", "sim"))
    p.add_argument("--route", default=os.getenv("ROUTE", "chandigarh,delhi,jaipur,mumbai"), help="comma separated waypoints (sim GPS)")
    p.add_argument("--steps", type=int, default=int(os.getenv("ROUTE_STEPS", 10)), help="ticks between waypoints")
    p.add_argument("--dwell", type=int, default=int(os.getenv("ROUTE_DWELL", 5)), help="ticks spent at each waypoint")
    p.add_argument("--no-loop", action="store_true")
    p.add_argument("--place", default=os.getenv("PLACE", ""), help="for --gps fixed: a known place name (delhi, mumbai, ...)")
    p.add_argument("--lat", type=float, default=float(os.getenv("LAT", 28.6139)))
    p.add_argument("--lng", type=float, default=float(os.getenv("LNG", 77.2090)))
    p.add_argument("--open", action="store_true", default=_flag("OPEN_BROWSER"), help="open the display page in a browser")
    p.add_argument("--kiosk", action="store_true", default=_flag("KIOSK"), help="open it fullscreen in Chrome/Edge kiosk mode")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s [%(label)s] %(message)s", datefmt="%H:%M:%S")
    label = [args.device_id or "unclaimed"]

    class _Label(logging.Filter):  # the prefix changes once discovery assigns a device ID
        def filter(self, record):
            record.label = label[0]
            return True

    for handler in logging.getLogger().handlers:
        handler.addFilter(_Label())
    cache_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    try:  # validate the location settings first so a typo fails immediately, not after the network retries
        gps = build_gps(args)
    except ValueError as e:
        p.error(str(e))
    server = detect_server(args.server)
    log.info("Server: %s", server)
    device_id, token = args.device_id, args.token
    if not (device_id and token):
        identity = load_identity(cache_root)  # claimed on an earlier run
        if identity:
            device_id, token = identity
        else:
            device_id, token = discover(server, gps, cache_root, VERSION, os.getenv("CONNECTION_TYPE") or None)
    label[0] = device_id
    cache_dir = args.cache_dir or os.path.join(cache_root, device_id)
    DeviceAgent(server, device_id, token, gps, cache_dir).run(
        args.port, open_url=f"http://localhost:{args.port}/" if (args.open or args.kiosk) else None, kiosk=args.kiosk)


if __name__ == "__main__":
    main()
