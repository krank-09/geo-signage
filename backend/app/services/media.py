import hashlib
import os
import tempfile
import uuid

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from .. import config
from ..models import Content
from ..storage import get_storage

MAGIC_CHECKS = {
    ".jpg": lambda h: h[:3] == b"\xff\xd8\xff",
    ".jpeg": lambda h: h[:3] == b"\xff\xd8\xff",
    ".png": lambda h: h[:8] == b"\x89PNG\r\n\x1a\n",
    ".mp4": lambda h: h[4:8] == b"ftyp",
    ".webm": lambda h: h[:4] == b"\x1a\x45\xdf\xa3",
}


async def save_upload(file: UploadFile) -> dict:
    """Validate (extension, magic bytes, size) and push to object storage."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}")
    kind, mime = config.ALLOWED_EXTENSIONS[ext]
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    head = b""
    digest = hashlib.sha256()
    fd, tmp = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                digest.update(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_MB} MB limit")
                out.write(chunk)
        if size == 0 or not MAGIC_CHECKS[ext](head):
            raise HTTPException(400, "File content does not match its extension")
        key = f"{uuid.uuid4().hex}{ext}"
        get_storage().put(key, tmp, mime)
    finally:
        os.remove(tmp)
    return {"key": key, "type": kind, "mime": mime, "size": size, "sha256": digest.hexdigest()}


def stream_content(content: Content, request: Request) -> Response:
    storage = get_storage()
    try:
        total = storage.size(content.storage_key)
    except Exception:
        raise HTTPException(404, "Media file missing from storage")
    start, end, status = 0, total - 1, 200
    rng = request.headers.get("range")
    if rng and rng.startswith("bytes="):
        try:
            s, _, e = rng[6:].split(",")[0].partition("-")
            if s == "":  # suffix range
                start = max(total - int(e), 0)
            else:
                start = int(s)
                end = min(int(e), total - 1) if e else total - 1
        except ValueError:
            raise HTTPException(416, "Bad range")
        if start > end or start >= total:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        status = 206
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, max-age=3600",
        "ETag": f'"{content.id}-{content.version}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return StreamingResponse(storage.read(content.storage_key, start, length), status_code=status, media_type=content.mime, headers=headers)


def ensure_hash(db, content: Content) -> str:
    """SHA-256 of a stored file. Content uploaded before hashing existed is hashed once, on first use, and remembered."""
    if content.sha256:
        return content.sha256
    storage, digest = get_storage(), hashlib.sha256()
    total = storage.size(content.storage_key)
    for chunk in storage.read(content.storage_key, 0, total):
        digest.update(chunk)
    content.sha256 = digest.hexdigest()
    db.commit()
    return content.sha256
