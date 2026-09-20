"""Digital-signage device agent.

Register -> heartbeat + report GPS -> receive content decisions from the server (WebSocket push with
polling fallback) -> download into a local cache -> serve a kiosk display page from that cache.
If the network or server disappears the agent keeps serving the last cached playlist and resyncs on reconnect.

Run:  python agent.py --server http://localhost:8000 --device-id DEV-001 --token DEMO-REG-001 \
                      --route chandigarh,delhi,jaipur,mumbai --port 8101

Every option can also come from environment variables or a `.env` file next to this script
(SERVER_URL, DEVICE_ID, REGISTRATION_TOKEN, DISPLAY_PORT, GPS_MODE, ROUTE, ROUTE_STEPS, ROUTE_DWELL, LAT, LNG,
OPEN_BROWSER, KIOSK) - see .env.example. `./start.sh` / `start.bat` wrap all of this for display laptops.
"""
import argparse
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import psutil
import requests
import websocket

from bootstrap import detect_server, load_dotenv, open_display
from cache import Cache
from display_server import make_server
from gps import FixedGPS, GpsdGPS, SimulatedGPS

VERSION = "1.1.0"
log = logging.getLogger("agent")


class Offline(Exception):
    pass


class DeviceAgent:
    def __init__(self, server, device_id, reg_token, gps, cache_dir, poll_interval=5):
        self.server = server.rstrip("/")
        self.device_id = device_id
        self.reg_token = reg_token
        self.gps = gps
        self.cache = Cache(cache_dir)
        self.poll_interval = poll_interval

        state = self.cache.load_state()
        self.token = state.get("token")
        self.manifest = state.get("manifest") or {"manifest_version": None, "items": [], "zone": None}
        self.config = state.get("config") or {"heartbeat_interval": 10, "location_interval": 3, "mute": True, "fit": "contain"}

        self.sim_offline = False  # simulated network cut (demo control)
        self.connected = False  # last server call succeeded
        self.ws_connected = False
        self.last_sync = None
        self.position = None
        self.server_manifest_version = self.manifest.get("manifest_version")
        self.impressions: list[dict] = []
        self.lock = threading.RLock()
        self.sync_event = threading.Event()
        self.hb_event = threading.Event()  # wake heartbeat early (e.g. right after a content change)
        self.stop = threading.Event()
        self.http = requests.Session()
        self.http.headers["ngrok-skip-browser-warning"] = "1"  # harmless elsewhere; avoids ngrok's browser notice
        self.reg_lock = threading.Lock()  # registration rotates credentials, so only one thread may do it at a time

    # ------------------------------------------------------------------ network helpers
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _request(self, method, path, retry_auth=True, **kw):
        if self.sim_offline:
            self.connected = False
            raise Offline("simulated network outage")
        if not self.token and path != "/device/register":
            self.register()
        try:
            r = self.http.request(method, self.server + path, headers=self._headers(), timeout=6, **kw)
        except requests.RequestException as e:
            self.connected = False
            raise Offline(str(e))
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
            "device_id": self.device_id, "registration_token": self.reg_token, "software_version": VERSION})
        if r.status_code != 200:
            if time.time() - getattr(self, "_reg_warned", 0) > 30:  # visible, but not every retry
                self._reg_warned = time.time()
                try:
                    detail = r.json().get("detail", r.text)
                except ValueError:
                    detail = r.text[:120]
                log.warning("Registration failed (%s): %s - check the Device ID and token (run start.sh --reset to re-enter)", r.status_code, detail)
            raise Offline(f"registration failed: {r.status_code}")
        body = r.json()
        self.token = body["access_token"]
        self.config = body["config"]
        self.cache.save_state(token=self.token, config=self.config)
        log.info("Registered with server as %s", self.device_id)

    # ------------------------------------------------------------------ sync (content decision -> local cache)
    def sync(self):
        r = self._request("GET", f"/device/{self.device_id}/content")
        if r.status_code != 200:
            raise Offline(f"content fetch failed: {r.status_code}")
        remote = r.json()
        self.config = remote["config"]
        items = remote["items"]
        for item in items:
            if not self.cache.has(item):
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
            with self.http.get(self.server + item["url"], headers=self._headers(), stream=True, timeout=15) as r:
                if r.status_code != 200:
                    raise Offline(f"download failed: {r.status_code}")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        f.write(chunk)
        except requests.RequestException as e:
            raise Offline(str(e))
        self.cache.commit(tmp, name)

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
                    "content_names": names, "software_version": VERSION,
                }
                r = self._request("POST", "/device/heartbeat", json=payload)
                if r.status_code == 200:
                    self._note_server_state(r.json())
                self._flush_impressions()
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
                "position": self.position, "pending_impressions": len(self.impressions),
                "last_sync": self.last_sync, "moving": getattr(self.gps, "moving", None),
            }

    def control(self, data):
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
        for fn in (self.sync_loop, self.heartbeat_loop, self.location_loop, self.ws_loop):
            threading.Thread(target=fn, daemon=True).start()
        self.sync_event.set()
        if open_url:
            open_display(open_url, kiosk)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()


def build_gps(args):
    if args.gps == "gpsd":
        return GpsdGPS()
    if args.gps == "fixed":
        return FixedGPS(args.lat, args.lng)
    return SimulatedGPS(args.route.split(","), steps=args.steps, dwell=args.dwell, loop=not args.no_loop)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    p = argparse.ArgumentParser(description="Geo signage device agent")
    p.add_argument("--server", default=os.getenv("SERVER_URL", "http://localhost:8000"))
    p.add_argument("--device-id", default=os.getenv("DEVICE_ID"), required=not os.getenv("DEVICE_ID"))
    p.add_argument("--token", default=os.getenv("REGISTRATION_TOKEN"), required=not os.getenv("REGISTRATION_TOKEN"),
                   help="registration token issued by the admin dashboard")
    p.add_argument("--port", type=int, default=int(os.getenv("DISPLAY_PORT", 8101)))
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--gps", choices=["sim", "fixed", "gpsd"], default=os.getenv("GPS_MODE", "sim"))
    p.add_argument("--route", default=os.getenv("ROUTE", "chandigarh,delhi,jaipur,mumbai"), help="comma separated waypoints (sim GPS)")
    p.add_argument("--steps", type=int, default=int(os.getenv("ROUTE_STEPS", 10)), help="ticks between waypoints")
    p.add_argument("--dwell", type=int, default=int(os.getenv("ROUTE_DWELL", 5)), help="ticks spent at each waypoint")
    p.add_argument("--no-loop", action="store_true")
    p.add_argument("--lat", type=float, default=float(os.getenv("LAT", 28.6139)))
    p.add_argument("--lng", type=float, default=float(os.getenv("LNG", 77.2090)))
    p.add_argument("--open", action="store_true", default=_flag("OPEN_BROWSER"), help="open the display page in a browser")
    p.add_argument("--kiosk", action="store_true", default=_flag("KIOSK"), help="open it fullscreen in Chrome/Edge kiosk mode")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format=f"%(asctime)s [{args.device_id}] %(message)s", datefmt="%H:%M:%S")
    cache_dir = args.cache_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", args.device_id)
    server = detect_server(args.server)
    log.info("Server: %s", server)
    DeviceAgent(server, args.device_id, args.token, build_gps(args), cache_dir).run(
        args.port, open_url=f"http://localhost:{args.port}/" if (args.open or args.kiosk) else None, kiosk=args.kiosk)


if __name__ == "__main__":
    main()
