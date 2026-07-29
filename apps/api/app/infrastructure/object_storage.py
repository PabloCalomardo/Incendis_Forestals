import boto3
from botocore.client import BaseClient

from app.core.config import get_settings


def create_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )


def check_object_storage() -> bool:
    settings = get_settings()
    try:
        client = create_s3_client()
        buckets = client.list_buckets()
        names = {bucket["Name"] for bucket in buckets.get("Buckets", [])}
        return settings.minio_bucket_raw in names or bool(buckets)
    except Exception:
        return False


def put_text_object(key: str, content: str, content_type: str = "text/plain") -> str:
    settings = get_settings()
    client = create_s3_client()
    client.put_object(
        Bucket=settings.minio_bucket_raw,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType=content_type,
    )
    return f"s3://{settings.minio_bucket_raw}/{key}"


def put_binary_object(key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
    settings = get_settings()
    client = create_s3_client()
    client.put_object(
        Bucket=settings.minio_bucket_raw,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return f"s3://{settings.minio_bucket_raw}/{key}"
