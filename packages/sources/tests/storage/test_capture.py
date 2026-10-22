import gzip
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, Listing, ListingSnapshot, RawPayload, Source
from pulso_sources import storage
from pulso_sources.storage import presign_capture, read_capture, store_capture

AT = datetime(2026, 10, 22, 12, tzinfo=UTC)
BODY = b'{"products": []}'


def capture_session() -> MagicMock:
    session = MagicMock(spec=Session)
    sources = {1: "shopify_stores", 2: "cj", 3: "aliexpress"}
    session.get.side_effect = lambda model, source_id: (
        Source(id=source_id, key=sources[source_id]) if source_id in sources else None
    )
    return session


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    objects: dict[tuple[str, str], bytes] = {}
    client.objects = objects

    def put_object(**params: Any) -> None:
        key = (params["Bucket"], params["Key"])
        assert params["IfNoneMatch"] == "*"
        if key in objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        objects[key] = params["Body"]

    def get_object(*, Bucket: str, Key: str) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(objects[Bucket, Key])}

    client.put_object.side_effect = put_object
    client.get_object.side_effect = get_object
    monkeypatch.setattr(storage, "make_client", lambda settings: client)
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(s3_bucket_raw="test-raw"))
    return client


def capture(session: Session, **overrides: Any) -> RawPayload:
    values: dict[str, Any] = {
        "source_id": 1,
        "source_key": "shopify_stores",
        "run_id": 1,
        "body": BODY,
        "content_type": "application/json",
        "status_code": 200,
        "etag": '"fixture"',
        "request": {"url": "https://example.test/products.json?limit=250"},
        "captured_at": AT,
    }
    return store_capture(session, **(values | overrides))


def test_identical_captures_reuse_object_but_add_two_rows(s3: MagicMock) -> None:
    session = capture_session()
    first = capture(session)
    second = capture(session)
    assert first is not second
    assert first.storage_key == second.storage_key
    assert len(s3.objects) == 1
    assert [call.args[0] for call in session.add.call_args_list] == [first, second]
    assert session.flush.call_count == 2
    session.commit.assert_not_called()
    assert first.template_version is second.template_version is None
    assert first.source_id == first.run_id == 1
    assert first.status_code == 200 and first.etag == '"fixture"'


@pytest.mark.parametrize(
    "body,content_type,suffix",
    [
        (BODY, "application/json", "json"),
        (b"", "application/problem+json", "json"),
        (b"title,price\nlamp,10\n", "Text/CSV; charset=utf-8", "csv"),
        (b"a,b\n", "application/csv", "csv"),
        (b"<html>blocked</html>", "text/html", "bin"),
        (b"unknown", None, "bin"),
        (BODY, "x" * 200, "bin"),
    ],
)
def test_roundtrip_and_object_metadata(
    s3: MagicMock,
    body: bytes,
    content_type: str | None,
    suffix: str,
) -> None:
    payload = capture(capture_session(), body=body, content_type=content_type)
    digest = hashlib.sha256(body).hexdigest()
    assert payload.storage_key == f"raw/shopify_stores/2026/10/22/{digest}.{suffix}.gz"
    assert payload.bytes == len(body) and payload.sha256 == digest
    assert read_capture(payload) == body
    params = s3.put_object.call_args.kwargs
    assert params["ContentEncoding"] == "gzip"
    assert params["ContentType"] == (content_type or "application/octet-stream")
    assert params["Body"] == gzip.compress(body, mtime=0)


def test_key_date_is_utc_and_objects_are_scoped_by_day_and_source(s3: MagicMock) -> None:
    session = capture_session()
    late = datetime(2026, 10, 21, 23, tzinfo=timezone(timedelta(hours=-4)))
    first = capture(session, captured_at=late)
    second = capture(session, captured_at=AT)
    capture(session, captured_at=AT + timedelta(days=1))
    capture(session, source_id=2, source_key="cj")
    assert first.captured_at == datetime(2026, 10, 22, 3, tzinfo=UTC)
    assert first.storage_key == second.storage_key
    assert len(s3.objects) == 3


@pytest.mark.parametrize(
    "error",
    [
        OSError("fixture upload failure"),
        ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject"),
        ClientError({"Error": {"Code": "ConditionalRequestConflict"}}, "PutObject"),
    ],
)
def test_upload_failure_never_adds_or_flushes_row(s3: MagicMock, error: Exception) -> None:
    s3.put_object.side_effect = error
    session = capture_session()
    with pytest.raises(type(error)):
        capture(session)
    session.add.assert_not_called()
    session.flush.assert_not_called()
    assert not s3.objects


@pytest.mark.parametrize("status,body", [(304, None), (304, b""), (200, None)])
def test_bodyless_evidence_has_no_object(s3: MagicMock, status: int, body: bytes | None) -> None:
    session = capture_session()
    payload = capture(session, body=body, status_code=status)
    assert payload.storage_key is None and payload.bytes == 0
    assert payload.sha256 == hashlib.sha256(b"").hexdigest()
    assert payload.status_code == status
    session.add.assert_called_once_with(payload)
    session.flush.assert_called_once()
    s3.put_object.assert_not_called()
    assert presign_capture(payload) is None
    with pytest.raises(ValueError, match="no stored body"):
        read_capture(payload)
    s3.get_object.assert_not_called()


@pytest.mark.parametrize(
    "object_body,error",
    [
        (gzip.compress(b"different"), ValueError),
        (b"not gzip", ValueError),
        (b"\x1f\x8bcorrupt gzip", gzip.BadGzipFile),
    ],
)
def test_read_rejects_tampering(s3: MagicMock, object_body: bytes, error: type[Exception]) -> None:
    payload = capture(capture_session())
    s3.objects["test-raw", payload.storage_key] = object_body
    with pytest.raises(error):
        read_capture(payload)


def test_presigned_get_expires_in_fifteen_minutes(s3: MagicMock) -> None:
    payload = capture(capture_session())
    s3.generate_presigned_url.return_value = "https://example.test/fixture-signed-url"
    assert presign_capture(payload) == "https://example.test/fixture-signed-url"
    s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-raw", "Key": payload.storage_key},
        ExpiresIn=900,
    )


@pytest.mark.parametrize("decoded", [False, True])
@pytest.mark.parametrize(
    "put_errors",
    [
        (),
        ("PreconditionFailed",),
        ("412",),
        ("ConditionalRequestConflict", "412"),
        ("ConditionalRequestConflict",),
    ],
)
def test_boto3_store_read_contract(
    s3: MagicMock, monkeypatch: pytest.MonkeyPatch, decoded: bool, put_errors: tuple[str, ...]
) -> None:
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="fixture", aws_secret_access_key="fixture"
    )
    monkeypatch.setattr(storage, "make_client", lambda settings: client)
    key = f"raw/shopify_stores/2026/10/22/{hashlib.sha256(BODY).hexdigest()}.json.gz"
    compressed = gzip.compress(BODY, mtime=0)
    returned = BODY if decoded else compressed
    buffer = io.BytesIO(returned)
    stream = StreamingBody(buffer, len(returned))
    session = capture_session()
    with Stubber(client) as stub:
        params = {
            "Bucket": "test-raw",
            "Key": key,
            "Body": compressed,
            "ContentType": "application/json",
            "ContentEncoding": "gzip",
            "IfNoneMatch": "*",
        }
        for code in put_errors:
            stub.add_client_error(
                "put_object",
                service_error_code=code,
                http_status_code=409 if code == "ConditionalRequestConflict" else 412,
                expected_params=params,
            )
        if not put_errors or put_errors[-1] == "ConditionalRequestConflict":
            stub.add_response("put_object", {}, params)
        stub.add_response("get_object", {"Body": stream}, {"Bucket": "test-raw", "Key": key})
        payload = capture(session)
        session.add.assert_called_once_with(payload)
        session.flush.assert_called_once()
        assert read_capture(payload) == BODY
        stub.assert_no_pending_responses()
    assert buffer.closed


@pytest.mark.parametrize(
    "credential",
    [
        "17token",
        "X-RapidAPI-Key",
        "Ocp-Apim-Subscription-Key",
        "private_token",
        "bearer",
        "session_id",
        "sid",
        "appsecret_proof",
        "AWSAccessKeyId",
        "CUSTOM-AUTH",
        "SignatureV2",
        "password_hash",
        "cookie_jar",
    ],
)
def test_sanitizes_nested_request_fixture_without_mutation(s3: MagicMock, credential: str) -> None:
    request = {
        "method": "GET",
        "url": "https://FAKE_USER:FAKE_PASS@example.test/products?API%5FKEY=FAKE_URL&limit=250"
        "&blank=&limit=100&X-Amz-Signature=FAKE_SIGN#token=FAKE_FRAGMENT",
        "headers": {
            "Authorization": "Bearer FAKE_AUTH",
            "pRoXy-AuThOrIzAtIoN": "FAKE_PROXY",
            "Cookie": "session=FAKE_COOKIE",
            "Set-Cookie": "FAKE_SET_COOKIE",
            "CJ-Access-Token": "FAKE_CJ",
            "X-API-Key": "FAKE_HEADER",
            "Accept": "application/json",
        },
        "params": {"access_token": "FAKE_ACCESS", "clientSecret": "FAKE_SECRET", "page": 2},
        "query_string": "key=FAKE_QUERY&search=lamp",
        "nested": [{"password": "FAKE_PASSWORD", "safe": True, "auth": {"user": "FAKE_USER"}}],
        "unlisted": {credential: "FAKE_UNLISTED"},
        "header_pairs": [[credential, "FAKE_PAIR"], ["Accept", "application/json"]],
        "body": f"{credential}=FAKE_BODY&page=2",
        "data": f"{credential}=FAKE_DATA&page=2",
        "form": f"{credential}=FAKE_FORM&page=2",
        "next_url": f"/products?{credential}=FAKE_QUERY&q=red%20lamp&fields=id,title",
    }
    original = json.dumps(request)
    payload = capture(capture_session(), request=request)
    assert "FAKE_" not in json.dumps(payload.request)
    assert json.dumps(request) == original
    assert payload.request == {
        "method": "GET",
        "url": "https://example.test/products?limit=250&blank=&limit=100",
        "headers": {"Accept": "application/json"},
        "params": {"page": 2},
        "query_string": "search=lamp",
        "nested": [{"safe": True}],
        "unlisted": {},
        "header_pairs": [["Accept", "application/json"]],
        "body": "page=2",
        "data": "page=2",
        "form": "page=2",
        "next_url": "/products?q=red%20lamp&fields=id,title",
    }


def test_sanitizer_preserves_safe_strings_and_url_encoding(s3: MagicMock) -> None:
    request = {
        "q": "what is this?",
        "keyword": "lamp? cheap",
        "title": "Lamp #1? yes",
        "note": "see https://x.test/a#frag",
        "path": "/example? text",
        "url": "HTTPS://example.test/a?fields=id,title&q=red%20lamp&blank=&q=two#frag",
        "nested": ["https://example.test/a?", "https://example.test/a#"],
        "query": "q=red%20lamp&fields=id,title&page_info=cursor",
        "body": "ordinary text?",
    }
    assert capture(capture_session(), request=request).request == request


@pytest.mark.parametrize(
    "overrides",
    [
        {"captured_at": datetime(2026, 10, 22)},
        {"source_key": "../unsafe"},
        {"source_key": "aliexpress"},
        {"source_id": 999},
        {"source_id": 2},
        {"source_id": 3},
        {"source_id": 3, "source_key": "aliexpress"},
        {"content_type": "x" * 201},
        {"status_code": 304, "body": BODY},
        {"request": {"url": "https://FAKE_USER:FAKE_PASS@[invalid"}},
    ],
)
def test_invalid_inputs_fail_before_any_write(s3: MagicMock, overrides: dict[str, Any]) -> None:
    session = capture_session()
    with pytest.raises(ValueError) as error:
        capture(session, **overrides)
    assert "FAKE_" not in str(error.value)
    s3.put_object.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.db
def test_persisted_capture_rows_and_snapshot_roundtrip(db_engine: Engine, s3: MagicMock) -> None:
    with Session(db_engine) as session:
        run = CollectorRun(source_id=1, trigger="fixture")
        listing = Listing(
            source_id=1, external_id="storage-test", url="https://example.test", title="X"
        )
        session.add_all([run, listing])
        session.flush()
        first = capture(session, run_id=run.id)
        second = capture(session, run_id=run.id)
        bodyless = capture(session, run_id=run.id, status_code=304, body=None)
        session.add(
            ListingSnapshot(
                listing_id=listing.id,
                raw_payload_id=first.id,
                captured_at=AT,
                observed_for=AT.date(),
                values_hash="a" * 64,
                currency="USD",
            )
        )
        session.commit()
        assert first.id != second.id
        assert len(s3.objects) == 1
        assert bodyless.storage_key is None
    with Session(db_engine) as session:
        rows = session.scalars(select(RawPayload).order_by(RawPayload.id)).all()
        assert len(rows) == 3 and rows[0].storage_key == rows[1].storage_key
        assert all(row.template_version is None for row in rows)
        raw = session.scalars(select(RawPayload).join(ListingSnapshot)).one()
        assert read_capture(raw) == BODY
        s3.put_object.side_effect = OSError("fixture failure")
        with pytest.raises(OSError):
            capture(session, run_id=rows[0].run_id, body=b"new capture")
        session.commit()
        assert len(session.scalars(select(RawPayload)).all()) == 3
