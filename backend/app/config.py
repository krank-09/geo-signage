import os


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./signage.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
ADMIN_TOKEN_MINUTES = _int("ADMIN_TOKEN_MINUTES", 12 * 60)
DEVICE_TOKEN_DAYS = _int("DEVICE_TOKEN_DAYS", 30)

DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "1") == "1"
# 1 = seeded devices use the well-known DEMO-REG-00x tokens (local demo / simulator). 0 = random tokens, printed once in the log.
FIXED_DEMO_TOKENS = os.getenv("FIXED_DEMO_TOKENS", "1") == "1"

# Device is marked OFFLINE when no heartbeat/location arrives within this window.
OFFLINE_THRESHOLD_SECONDS = _int("OFFLINE_THRESHOLD_SECONDS", 30)
MONITOR_INTERVAL_SECONDS = _int("MONITOR_INTERVAL_SECONDS", 5)

# Timezone offset (minutes east of UTC) used to evaluate "HH:MM" schedule windows.
# Default is IST (UTC+5:30) to match the Chandigarh/Delhi/Mumbai demo.
SCHEDULE_TZ_OFFSET_MINUTES = _int("SCHEDULE_TZ_OFFSET_MINUTES", 330)

# Storage: "minio" or "local"
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", "./media_store")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "signage-media")
MINIO_SECURE = os.getenv("MINIO_SECURE", "0") == "1"

# Health: a device whose score falls below this (percent) raises an alert; editable at runtime in the dashboard.
HEALTH_ALERT_THRESHOLD = _int("HEALTH_ALERT_THRESHOLD", 50)

# Firebase sign-in (optional). Leave FIREBASE_PROJECT_ID empty to disable it and use the built-in login only.
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID", "")
# Comma-separated emails that become admins automatically on their first (verified) Firebase sign-in.
FIREBASE_ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("FIREBASE_ADMIN_EMAILS", "").split(",") if e.strip()}
# Local development only: accept the unsigned tokens issued by the Firebase Auth emulator (host:port).
FIREBASE_AUTH_EMULATOR_HOST = os.getenv("FIREBASE_AUTH_EMULATOR_HOST", "")

# Device identity keys. "optional": displays with a bound key must sign every request, older displays without one are still
# accepted (and flagged as unprotected). "required": unsigned displays are refused. Use "required" once every display is updated.
DEVICE_AUTH_MODE = os.getenv("DEVICE_AUTH_MODE", "optional").lower()
# Base64 32-byte Ed25519 seed used to sign playlists. If unset, one is generated once and kept in the database.
SERVER_SIGNING_KEY = os.getenv("SERVER_SIGNING_KEY", "")

MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 100)
TRACK_RETENTION_DAYS = _int("TRACK_RETENTION_DAYS", 7)
SCREENSHOT_MAX_KB = _int("SCREENSHOT_MAX_KB", 400)
ALLOWED_EXTENSIONS = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
}
