"""S3-compatible object storage backend (AWS S3, Cloudflare R2, MinIO).

Uses :mod:`aiobotocore` for native async S3 access. Cloudflare R2 and
MinIO are reached through the same S3 API by pointing ``S3_ENDPOINT_URL``
at the service (R2: ``https://<account>.r2.cloudflarestorage.com``,
MinIO: ``http://localhost:9000``) and enabling path-style addressing.

The client is created lazily on first use so constructing the backend is
free of network I/O (the factory and unit tests never touch the wire).
"""

from __future__ import annotations

from typing import Any

import botocore.config
from botocore.exceptions import ClientError

from meeting_notes_ai.config import Settings, settings as default_settings


class S3StorageBackend:
    """S3/R2/MinIO implementation of the ObjectStorageBackend contract.

    All configuration comes from :class:`meeting_notes_ai.config.Settings`
    (env vars ``S3_*`` / ``STORAGE_BACKEND``); nothing is hard-coded so a
    single code path serves AWS S3, Cloudflare R2, and MinIO (AC6).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the backend from *settings* (defaults to the singleton)."""
        self.settings = settings or default_settings
        self._client: Any | None = None
        self._client_ctx: Any | None = None

    # ── Client lifecycle ──────────────────────────────────────────────────────

    async def _get_client(self) -> Any:
        """Return the aiobotocore S3 client, creating it on first use.

        aiobotocore >= 3.x ``create_client`` returns an async context
        manager; we enter it once and keep the client for the app's life.
        """
        if self._client is None:
            import aiobotocore.session

            session = aiobotocore.session.AioSession()
            client_kwargs: dict[str, Any] = {
                "service_name": "s3",
                "region_name": self.settings.s3_region or "us-east-1",
                "config": botocore.config.Config(
                    s3={
                        "addressing_style": (
                            "path" if self.settings.s3_force_path_style else "auto"
                        )
                    }
                ),
            }
            if self.settings.s3_endpoint_url:
                client_kwargs["endpoint_url"] = self.settings.s3_endpoint_url
            if self.settings.s3_access_key_id:
                client_kwargs["aws_access_key_id"] = self.settings.s3_access_key_id
            if self.settings.s3_secret_access_key:
                client_kwargs["aws_secret_access_key"] = self.settings.s3_secret_access_key
            self._client_ctx = session.create_client(**client_kwargs)
            self._client = await self._client_ctx.__aenter__()
        return self._client

    @property
    def bucket(self) -> str:
        """Bucket name for this backend."""
        return self.settings.s3_bucket or "meeting-notes-ai"

    async def close(self) -> None:
        """Close the underlying S3 client if it was created."""
        if self._client is not None and self._client_ctx is not None:
            await self._client_ctx.__aexit__(None, None, None)
            self._client = None
            self._client_ctx = None

    # ── ObjectStorageBackend implementation ──────────────────────────────────

    async def _ensure_bucket(self, client: Any) -> None:
        """Create the bucket when it does not exist (idempotent).

        Makes a fresh dev MinIO stack work out of the box; in production
        the bucket is pre-provisioned and this is a cheap head check.
        """
        try:
            await client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if not _is_not_found(exc):
                raise
            try:
                await client.create_bucket(Bucket=self.bucket)
            except ClientError as create_exc:
                if create_exc.response.get("Error", {}).get("Code") not in (
                    "BucketAlreadyOwnedByYou",
                    "BucketAlreadyExists",
                ):
                    raise

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Store *data* under *key* in the configured bucket."""
        client = await self._get_client()
        await self._ensure_bucket(client)
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
        await client.put_object(**kwargs)

    async def get(self, key: str) -> bytes:
        """Return the bytes stored under *key*.

        Raises:
            KeyError: If no object exists for *key* (S3 404/NoSuchKey).
        """
        client = await self._get_client()
        try:
            response = await client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise KeyError(key) from None
            raise
        body = response.get("Body")
        if body is None:
            raise KeyError(key)
        return await body.read()

    async def delete(self, key: str) -> None:
        """Remove the object under *key* (idempotent — S3 delete is a no-op
        for missing keys)."""
        client = await self._get_client()
        await client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        """Return True when an object exists under *key*."""
        client = await self._get_client()
        try:
            await client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise

    async def list(self, prefix: str) -> list[str]:
        """Return all object keys under *prefix* (paginated)."""
        client = await self._get_client()
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                keys.append(obj["Key"])
        return keys


def _is_not_found(exc: ClientError) -> bool:
    """Return True when a ClientError represents a missing object."""
    error_code = exc.response.get("Error", {}).get("Code", "")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error_code in ("NoSuchKey", "404", "NotFound") or status == 404
