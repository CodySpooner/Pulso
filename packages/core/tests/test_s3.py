from contextlib import closing
from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.config import Config
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
@pytest.mark.parametrize("override", [False, True])
def test_presign_uses_sigv4_and_configured_endpoint_without_network(
    region: str, override: bool
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://unused"),
        s3_endpoint_url="https://storage.example.test",
        s3_region=region,
        s3_access_key_id="fixture-key",
        s3_secret_access_key=SecretStr("fixture-secret"),
    )
    config = Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1})
    with closing(
        make_client(settings, config=config) if override else make_client(settings)
    ) as client:
        if override:
            assert client.meta.config.connect_timeout == client.meta.config.read_timeout == 2
            assert client.meta.config.retries["total_max_attempts"] == 2
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
