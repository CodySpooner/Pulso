from typing import Any

import boto3
from botocore.stub import Stubber

from pulso_core.s3 import ensure_bucket


def stubbed_client() -> tuple[Any, Stubber]:
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y"
    )
    return client, Stubber(client)


def test_creates_missing_bucket() -> None:
    client, stub = stubbed_client()
    stub.add_client_error("head_bucket", "404", http_status_code=404)
    stub.add_response("create_bucket", {}, {"Bucket": "pulso-raw"})
    with stub:
        assert ensure_bucket(client, "pulso-raw") is True
    stub.assert_no_pending_responses()


def test_leaves_existing_bucket() -> None:
    client, stub = stubbed_client()
    stub.add_response("head_bucket", {}, {"Bucket": "pulso-raw"})
    with stub:
        assert ensure_bucket(client, "pulso-raw") is False
    stub.assert_no_pending_responses()
