"""Object storage abstraction: MinIO (S3-compatible) or local disk fallback."""
import os
import re
import time
from typing import Iterator

from . import config


class Storage:
    def put(self, key: str, path: str, mime: str) -> None: ...
    def size(self, key: str) -> int: ...
    def read(self, key: str, start: int, length: int) -> Iterator[bytes]: ...
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _p(self, key: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", key):
            raise ValueError("bad key")
        return os.path.join(self.root, key)

    def put(self, key, path, mime):
        with open(path, "rb") as src, open(self._p(key), "wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)

    def size(self, key):
        return os.path.getsize(self._p(key))

    def read(self, key, start, length):
        with open(self._p(key), "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def delete(self, key):
        try:
            os.remove(self._p(key))
        except FileNotFoundError:
            pass


class MinioStorage(Storage):
    def __init__(self):
        from minio import Minio

        self.client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
        )
        self.bucket = config.MINIO_BUCKET
        for attempt in range(30):  # MinIO may still be starting when the backend boots
            try:
                if not self.client.bucket_exists(self.bucket):
                    self.client.make_bucket(self.bucket)
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)

    def put(self, key, path, mime):
        self.client.fput_object(self.bucket, key, path, content_type=mime)

    def size(self, key):
        return self.client.stat_object(self.bucket, key).size

    def read(self, key, start, length):
        resp = self.client.get_object(self.bucket, key, offset=start, length=length)
        try:
            yield from resp.stream(256 * 1024)
        finally:
            resp.close()
            resp.release_conn()

    def delete(self, key):
        self.client.remove_object(self.bucket, key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = MinioStorage() if config.STORAGE_BACKEND == "minio" else LocalStorage(config.LOCAL_STORAGE_DIR)
    return _storage
