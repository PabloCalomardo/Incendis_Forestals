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
