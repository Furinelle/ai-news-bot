from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True)
class R2UploadResult:
    bucket: str
    key: str
    url: str = ""


def build_r2_key(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip().strip("/")
    clean_name = filename.strip().lstrip("/")
    return f"{clean_prefix}/{clean_name}" if clean_prefix else clean_name


def build_public_url(public_base_url: str, key: str) -> str:
    if not public_base_url:
        return ""
    return f"{public_base_url.rstrip('/')}/{quote(key, safe='/')}"


def build_s3_client(endpoint_url: str, access_key_id: str, secret_access_key: str) -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def create_presigned_get_url(
    bucket: str,
    key: str,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    expires_seconds: int = 604800,
    client: Any | None = None,
) -> str:
    if client is None:
        client = build_s3_client(endpoint_url, access_key_id, secret_access_key)
    return str(
        client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    )


def upload_file_to_r2(
    path: str | Path,
    bucket: str,
    key: str,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    public_base_url: str = "",
    content_type: str = "text/markdown; charset=utf-8",
    client: Any | None = None,
) -> R2UploadResult:
    if client is None:
        client = build_s3_client(endpoint_url, access_key_id, secret_access_key)

    extra_args = {"ContentType": content_type}
    client.upload_file(str(path), bucket, key, ExtraArgs=extra_args)
    return R2UploadResult(bucket=bucket, key=key, url=build_public_url(public_base_url, key))
