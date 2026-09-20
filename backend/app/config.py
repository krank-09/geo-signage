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

MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 100)
ALLOWED_EXTENSIONS = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
}
