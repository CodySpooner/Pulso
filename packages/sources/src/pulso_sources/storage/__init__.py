"""Raw capture evidence; callers own the database transaction (DEC-061)."""

import gzip
import hashlib
import re
from contextlib import closing
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from pulso_core.models import RawPayload
from pulso_core.s3 import make_client
from pulso_core.settings import get_settings

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

# shortcut: known credential names only; extend when a source adds a different auth field.
_SECRET_NAMES = {
    "auth",
    "authorization",
    "proxyauthorization",
    "cookie",
    "cookies",
    "setcookie",
    "token",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "cjaccesstoken",
    "xauthtoken",
    "authtoken",
    "xshopifyaccesstoken",
    "apikey",
    "xapikey",
    "key",
    "appkey",
    "appsecret",
    "clientsecret",
    "password",
    "passwd",
    "secret",
    "credentials",
    "credential",
    "signature",
    "sig",
    "awsaccesskeyid",
    "accesskey",
    "accesskeyid",
    "secretaccesskey",
    "csrftoken",
    "xcsrftoken",
    "xsrftoken",
    "xxsrftoken",
    "xamzcredential",
    "xamzsignature",
    "xamzsecuritytoken",
    "xgoogcredential",
    "xgoogsignature",
}


def _name(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _query(query: str) -> str:
    return urlencode(
        [
            (key, _clean(value))
            for key, value in parse_qsl(query, keep_blank_values=True)
            if _name(key) not in _SECRET_NAMES
        ]
    )


def _clean(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _query(item)
            if _name(key) in {"query", "querystring"} and isinstance(item, str)
            else _clean(item)
            for key, item in value.items()
            if _name(key) not in _SECRET_NAMES
        }
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str) and ("://" in value or "?" in value or value.startswith("/")):
        try:
            url = urlsplit(value)
        except ValueError:
            raise ValueError("Invalid request metadata URL") from None
        return urlunsplit(
            (url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, _query(url.query), "")
        )
    return value


def store_capture(
    session: Session,
    *,
    source_id: int,
    source_key: str,
    run_id: int,
    body: bytes | None,
    content_type: str | None,
    status_code: int | None,
    etag: str | None,
    request: dict[str, JsonValue],
    captured_at: datetime,
) -> RawPayload:
    """Upload first, then add and flush one row; never commit or deduplicate captures.

    None means no response body; 304 also normalizes empty bytes to None. Bodyless
    evidence uses the empty-byte digest and size 0, distinguished by storage_key=None.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", source_key):
        raise ValueError("Invalid source key")
    if source_key == "aliexpress":
        raise ValueError("AliExpress raw storage is forbidden (DEC-037)")
    if captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)
    if status_code == 304:
        if body:
            raise ValueError("304 captures cannot have a body")
        body = None
    metadata = _clean(request)
    digest = hashlib.sha256(body if body is not None else b"").hexdigest()
    storage_key = None
    if body is not None:
        media_type = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
        suffix = "csv" if media_type in {"text/csv", "application/csv"} else "bin"
        if media_type == "application/json" or media_type.endswith("+json"):
            suffix = "json"
        storage_key = f"raw/{source_key}/{captured_at:%Y/%m/%d}/{digest}.{suffix}.gz"
        settings = get_settings()
        with closing(make_client(settings)) as client:
            try:
                client.put_object(
                    Bucket=settings.s3_bucket_raw,
                    Key=storage_key,
                    Body=gzip.compress(body, mtime=0),
                    ContentType=content_type or "application/octet-stream",
                    ContentEncoding="gzip",
                    IfNoneMatch="*",
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
                    raise
    payload = RawPayload(
        source_id=source_id,
        run_id=run_id,
        captured_at=captured_at,
        request=metadata,
        status_code=status_code,
        content_type=content_type,
        etag=etag,
        bytes=len(body) if body is not None else 0,
        sha256=digest,
        storage_key=storage_key,
        template_version=None,
    )
    session.add(payload)
    session.flush()
    return payload


def read_capture(payload: RawPayload) -> bytes:
    """Fetch and decompress the object, rejecting bodyless evidence or a hash mismatch."""
    if payload.storage_key is None:
        raise ValueError("Capture has no stored body")
    settings = get_settings()
    with closing(make_client(settings)) as client:
        response = client.get_object(Bucket=settings.s3_bucket_raw, Key=payload.storage_key)
        with closing(response["Body"]) as stream:
            body = gzip.decompress(stream.read())
    if hashlib.sha256(body).hexdigest() != payload.sha256:
        raise ValueError("Raw capture SHA-256 mismatch")
    return body


def presign_capture(payload: RawPayload) -> str | None:
    """Return a 15-minute GET URL, or None for evidence without an object."""
    if payload.storage_key is None:
        return None
    settings = get_settings()
    with closing(make_client(settings)) as client:
        url: str = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_raw, "Key": payload.storage_key},
            ExpiresIn=900,
        )
    return url
