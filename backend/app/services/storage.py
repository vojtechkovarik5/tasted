"""Object storage for uploaded images (menu photo pages, user dish photos).

One `Storage` protocol, two backends chosen by config:

  S3Storage     when settings.s3_configured — aioboto3, AWS or any
                S3-compatible store (Cloudflare R2, MinIO via aws_endpoint_url)
  LocalStorage  otherwise — writes under settings.upload_dir, so the app runs
                with no cloud creds in local dev

Keys are stored verbatim: `put()` returns the exact key to persist, and
`get()`/`public_url()` take that same key back — no hidden scoping that could
desync the read from the write. Callers namespace keys themselves (see
MenuService), including the app_env prefix so environments don't collide in a
shared bucket.

Everything is bytes in / bytes out; FastAPI's UploadFile is read to bytes at
the router edge, keeping this reusable from Celery and scripts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import aioboto3

from app.config import settings

# File extension by upload content type; anything else falls back to .jpg.
_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def extension_for(content_type: str | None) -> str:
    return _EXTENSIONS.get(content_type or "", ".jpg")


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store bytes under `key`; return the key to persist and read back."""
        ...

    async def get(self, key: str) -> bytes:
        ...

    def public_url(self, key: str) -> str:
        """Browser-reachable URL for the object (for user-facing photos)."""
        ...


class LocalStorage:
    """Disk-backed dev/demo fallback with the same API as S3Storage.

    Writes under `root` (settings.upload_dir → ./backend/uploads locally,
    /app/uploads in Docker). `public_url` points at the `/uploads` static
    mount (see app/main.py), so URLs resolve in the demo without any cloud.
    """

    def __init__(self, root: str):
        self.root = Path(root)

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def public_url(self, key: str) -> str:
        return f"/uploads/{key}"


class S3Storage:
    """aioboto3-backed S3 / S3-compatible storage.

    A fresh session-scoped client per call (no pooling) — matches the async
    context-manager pattern and keeps clients bound to the running loop, which
    is what Celery's per-task event loops need.
    """

    def __init__(self):
        self.bucket = settings.s3_bucket
        self.region = settings.aws_region
        self.endpoint_url = settings.aws_endpoint_url or None

    def _client(self):
        session = aioboto3.Session()
        params = {"service_name": "s3", "region_name": self.region}
        if self.endpoint_url:
            params["endpoint_url"] = self.endpoint_url
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            params["aws_access_key_id"] = settings.aws_access_key_id
            params["aws_secret_access_key"] = settings.aws_secret_access_key
        return session.client(**params)

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        async with self._client() as s3:
            await s3.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self.bucket, Key=key)
            async with obj["Body"] as stream:
                return await stream.read()

    def public_url(self, key: str) -> str:
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        if self.endpoint_url:  # R2/MinIO path-style
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"


def get_storage() -> Storage:
    """The storage backend for this environment (S3 when configured)."""
    if settings.s3_configured:
        return S3Storage()
    return LocalStorage(settings.upload_dir)
