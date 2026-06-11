import os
import io
import json
import logging
from dotenv import load_dotenv

load_dotenv()

# Reads STORAGE_BACKEND from env to decide whether to talk to MinIO (local dev)
# or AWS S3 (cloud). The rest of the codebase doesn't need to care which one.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "minio").lower()

logger = logging.getLogger(__name__)


def _get_minio_client():
    from minio import Minio
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    logger.info(f"[Storage] MinIO @ {endpoint}")
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)


def _get_s3_client():
    import boto3
    region = os.getenv("AWS_REGION", "eu-west-1")
    logger.info(f"[Storage] AWS S3 region={region}")
    # Credentials come from env vars or the EC2 IAM role — no hardcoding needed
    return boto3.client("s3", region_name=region)


def get_storage_client():
    if STORAGE_BACKEND == "s3":
        return _get_s3_client()
    return _get_minio_client()


def upload_json(client, bucket: str, key: str, data: list | dict) -> None:
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if STORAGE_BACKEND == "s3":
        client.put_object(Bucket=bucket, Key=key, Body=json_bytes, ContentType="application/json")
    else:
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=io.BytesIO(json_bytes),
            length=len(json_bytes),
            content_type="application/json",
        )
    logger.info(f"[Storage] Uploaded -> s3://{bucket}/{key}")


def read_json(client, bucket: str, key: str) -> list | dict:
    if STORAGE_BACKEND == "s3":
        response = client.get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))
    else:
        response = client.get_object(bucket, key)
        data = json.loads(response.read().decode("utf-8"))
        response.close()
        response.release_conn()
        return data


def list_objects(client, bucket: str, prefix: str) -> list[str]:
    if STORAGE_BACKEND == "s3":
        paginator = client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    else:
        return [obj.object_name for obj in client.list_objects(bucket, prefix=prefix, recursive=True)]


def move_object(client, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
    # Copy then delete — S3/MinIO don't have a native move operation
    if STORAGE_BACKEND == "s3":
        client.copy_object(
            Bucket=dst_bucket,
            Key=dst_key,
            CopySource={"Bucket": src_bucket, "Key": src_key},
        )
        client.delete_object(Bucket=src_bucket, Key=src_key)
    else:
        from minio.commonconfig import CopySource
        client.copy_object(dst_bucket, dst_key, CopySource(src_bucket, src_key))
        client.remove_object(src_bucket, src_key)
    logger.info(f"[Storage] Moved -> s3://{dst_bucket}/{dst_key}")


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        if STORAGE_BACKEND == "s3":
            client.head_object(Bucket=bucket, Key=key)
        else:
            client.stat_object(bucket, key)
        return True
    except Exception:
        return False
