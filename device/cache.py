"""On-disk cache so the display keeps working with no connectivity."""
import json
import os
import re
import threading

SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


class Cache:
    def __init__(self, root: str, max_files: int = 20, identity=None):
        self.identity = identity            # signs/verifies state.json so hand edits are noticed
        self.state_tampered = False
        self.root = os.path.abspath(root)
        self.media = os.path.join(self.root, "media")
        os.makedirs(self.media, exist_ok=True)
        self.state_path = os.path.join(self.root, "state.json")
        self.max_files = max_files
        self.lock = threading.Lock()

    # -- credentials + last known manifest -------------------------------------------------
    def load_state(self) -> dict:
        try:
            with open(self.state_path) as f:
                wrapped = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if self.identity is None or "data" not in wrapped:
            return wrapped if self.identity is None else {}   # unsigned or reshaped file: not trusted
        if not self.identity.mac_ok(wrapped["data"], wrapped.get("mac", "")):
            self.state_tampered = True
            return {}
        return json.loads(wrapped["data"])

    def save_state(self, **updates) -> None:
        with self.lock:
            state = self.load_state()
            state.update(updates)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                if self.identity is None:
                    json.dump(state, f)
                else:
                    data = json.dumps(state, sort_keys=True)
                    json.dump({"data": data, "mac": self.identity.mac(data)}, f)
            os.replace(tmp, self.state_path)

    # -- media files ---------------------------------------------------------------------------
    @staticmethod
    def filename(item: dict) -> str:
        ext = ".mp4" if "mp4" in item["mime"] else ".webm" if "webm" in item["mime"] else ".png" if "png" in item["mime"] else ".jpg"
        return f"{item['content_id']}-v{item['version']}{ext}"

    def path(self, name: str) -> str | None:
        if not SAFE.match(name):
            return None
        p = os.path.join(self.media, name)
        return p if os.path.isfile(p) else None

    def has(self, item: dict) -> bool:
        return self.path(self.filename(item)) is not None

    def remove(self, name: str) -> None:
        p = self.path(name)
        if p:
            os.remove(p)

    def new_tmp(self, name: str) -> str:
        return os.path.join(self.media, name + ".part")

    def commit(self, tmp: str, name: str) -> None:
        os.replace(tmp, os.path.join(self.media, name))

    def gc(self, keep: set[str]) -> None:
        files = [f for f in os.listdir(self.media) if not f.endswith(".part")]
        if len(files) <= self.max_files:
            return
        stale = sorted((f for f in files if f not in keep), key=lambda f: os.path.getmtime(os.path.join(self.media, f)))
        for f in stale[: len(files) - self.max_files]:
            os.remove(os.path.join(self.media, f))
