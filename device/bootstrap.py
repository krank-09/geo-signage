"""Startup helpers for the device agent: .env loading, server discovery and opening the display page."""
import logging
import os
import shutil
import subprocess
import tempfile
import time
import webbrowser

import requests

log = logging.getLogger("agent")


def load_dotenv(path: str) -> None:
    """Minimal .env reader (KEY=VALUE, # comments). Real environment variables win."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.split(" #")[0].strip().strip("\"'"))
    except FileNotFoundError:
        pass


def detect_server(url: str) -> str:
    """Accepts the tunnel root (https://x.trycloudflare.com), .../api, or a direct backend URL and returns the
    base under which the backend's /health answers."""
    url = url.strip().rstrip("/")
    candidates = [url] if url.endswith("/api") else [url, url + "/api"]
    for _ in range(4):
        for base in candidates:
            try:
                r = requests.get(base + "/health", timeout=6)
                if r.ok and r.json().get("status") == "ok":
                    return base
            except (requests.RequestException, ValueError):
                continue
        time.sleep(3)
    log.warning("Could not reach %s/health - continuing anyway; the agent will keep retrying", url)
    return url


def open_display(url: str, kiosk: bool) -> None:
    if kiosk:
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ] + [shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
        exe = next((c for c in candidates if c and os.path.exists(c)), None)
        if exe:
            subprocess.Popen([exe, "--kiosk", "--autoplay-policy=no-user-gesture-required", "--no-first-run",
                              "--disable-pinch", "--overscroll-history-navigation=0", "--disable-translate", "--disable-features=TranslateUI",
                              "--noerrdialogs", "--disable-infobars", "--disable-session-crashed-bubble", "--disable-dev-tools",
                              "--incognito", f"--user-data-dir={os.path.join(tempfile.gettempdir(), 'signage-kiosk')}", url])
            return
        log.warning("No Chrome/Edge found for kiosk mode - opening the default browser instead (press F11)")
    webbrowser.open(url)
