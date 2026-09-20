"""Tiny local HTTP server the Chromium kiosk points at. It serves the display page and cached media,
so playback never depends on the internet."""
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4", ".webm": "video/webm"}


LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def make_server(agent, port: int) -> ThreadingHTTPServer:
    """Listens on this machine only (DISPLAY_BIND=0.0.0.0 to open it up, e.g. in Docker). Requests must carry a local Host
    header, which stops DNS-rebinding pages from talking to it, and /api/control needs the per-run token."""
    extra = {h.strip().lower() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower().rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") \
                else (self.headers.get("Host") or "").lower().split("]")[0] + "]"
            return host in LOCAL_HOSTS or host in extra

        def parse_request(self):
            ok = super().parse_request()
            if ok and not self._host_ok():
                self.send_error(421, "Misdirected request")
                return False
            return ok

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "display", "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                                                            "img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/state":
                self._json(agent.display_state())
            elif path.startswith("/media/"):
                self._media(path[len("/media/"):])
            else:
                self.send_error(404)

        def _media(self, name):
            p = agent.cache.path(name)
            if not p:
                return self.send_error(404)
            total = os.path.getsize(p)
            start, end, code = 0, total - 1, 200
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else total - 1
                else:
                    start = max(total - int(m.group(2)), 0)
                end = min(end, total - 1)
                code = 206
            length = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream"))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(start)
                    left = length
                    while left > 0:
                        chunk = f.read(min(65536, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if self.path == "/api/screenshot":
                if not secrets.compare_digest(self.headers.get("X-Page-Token", ""), agent.page_token):
                    return self._json({"ok": False, "error": "page token required"}, 403)
                if n > 600 * 1024:
                    return self._json({"ok": False, "error": "too large"}, 413)
                return self._json({"ok": agent.accept_screenshot(self.rfile.read(n))})
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            if self.path == "/api/impression":
                agent.record_impression(data)
                self._json({"ok": True})
            elif self.path == "/api/control":
                if not secrets.compare_digest(self.headers.get("X-Control-Token", ""), agent.control_token):
                    return self._json({"ok": False, "error": "control token required"}, 403)
                self._json(agent.control(data))
            else:
                self.send_error(404)

    return ThreadingHTTPServer((os.getenv("DISPLAY_BIND", "127.0.0.1"), port), Handler)
