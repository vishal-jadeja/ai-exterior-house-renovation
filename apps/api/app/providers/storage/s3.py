"""S3-compatible object storage (MinIO locally, Cloudflare R2 in the cloud).

Only presigned URLs are ever handed to clients; the bucket stays private.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


class S3Storage:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.s3_bucket
        self.ttl = s.presign_ttl_seconds
        kwargs = dict(
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._client = boto3.client("s3", endpoint_url=s.s3_endpoint_url, **kwargs)
        # Presigned URLs must be reachable from the browser; inside compose the internal
        # hostname (minio:9000) differs from the public one (localhost:9000).
        public = s.s3_public_endpoint_url or s.s3_endpoint_url
        self._signer = boto3.client("s3", endpoint_url=public, **kwargs)

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    def presign(self, key: str, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._signer.generate_presigned_url("get_object", Params=params, ExpiresIn=self.ttl)


@lru_cache
def get_storage() -> S3Storage:
    return S3Storage()
