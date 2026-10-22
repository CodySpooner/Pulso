from contextlib import closing
from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.stub import Stubber
from pydantic import SecretStr

from pulso_core.s3 import ensure_bucket, make_client
from pulso_core.settings import Settings


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


@pytest.mark.parametrize("region", ["auto", "us-east-1"])
def test_presign_uses_sigv4_and_configured_endpoint_without_network(region: str) -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://unused"),
        s3_endpoint_url="https://storage.example.test",
        s3_region=region,
        s3_access_key_id="fixture-key",
        s3_secret_access_key=SecretStr("fixture-secret"),
    )
    with closing(make_client(settings)) as client:
        url = urlsplit(
            client.generate_presigned_url(
                "get_object",
                Params={"Bucket": "test-raw", "Key": "raw/fixture.json.gz"},
                ExpiresIn=900,
            )
        )
    assert url.netloc == "storage.example.test"
    assert url.path == "/test-raw/raw/fixture.json.gz"
    query = parse_qs(url.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["900"]
