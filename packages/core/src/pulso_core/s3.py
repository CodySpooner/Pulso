"""S3 helper. `python -m pulso_core.s3 init` creates the raw bucket (RustFS in dev and on the
collector host). Production buckets on Cloudflare R2 are created in its dashboard instead.
"""

import argparse
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from pulso_core.settings import Settings, get_settings


def make_client(settings: Settings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket(client: Any, bucket: str) -> bool:
    """Create `bucket` if it is missing. Returns True when it was created."""
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise  # 403 etc.: wrong credentials or endpoint, not a missing bucket
    client.create_bucket(Bucket=bucket)
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pulso_core.s3", description="Pulso object-storage helper."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create the raw bucket (S3_BUCKET_RAW) if it is missing")
    parser.parse_args(argv)

    settings = get_settings()
    created = ensure_bucket(make_client(settings), settings.s3_bucket_raw)
    print(f"{settings.s3_bucket_raw}: {'created' if created else 'already exists'}")


if __name__ == "__main__":
    main()
