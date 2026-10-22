"""Raw capture evidence; callers own the database transaction (DEC-061)."""

import gzip
import hashlib
import re
from contextlib import closing
from datetime import UTC, datetime
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from pulso_core.models import RawPayload, Source
from pulso_core.s3 import make_client
from pulso_core.settings import get_settings

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

# Losing optional metadata is preferable to retaining credentials forever.
_SECRET_NAME = re.compile(
    r"token|secret|password|passwd|auth|signature|credential|cookie|session"
    r"|key(?:id)?$|^(?:bearer|sid|sig)$"
)


def _name(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _query(query: str) -> str:
    return "&".join(
        part
        for part in query.split("&")
        if not _SECRET_NAME.search(_name(unquote_plus(part.split("=", 1)[0])))
    )


def _clean(value: JsonValue, field: str = "") -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _clean(item, key)
            for key, item in value.items()
            if not _SECRET_NAME.search(_name(key))
        }
    if isinstance(value, list):
        return [
            _clean(item)
            for item in value
            if not (
                isinstance(item, list)
                and len(item) == 2
                and isinstance(item[0], str)
                and _SECRET_NAME.search(_name(item[0]))
            )
        ]
    if not isinstance(value, str):
        return value
    if _name(field) in {"query", "querystring", "body", "data", "form"} and "=" in value:
        return _query(value)
    if _name(field).endswith("url") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        try:
            url = urlsplit(value)
        except ValueError:
            raise ValueError("Invalid request metadata URL") from None
        if not _name(field).endswith("url") and not (url.scheme and url.netloc):
            return value
        clean = url._replace(
            netloc=url.netloc.rsplit("@", 1)[-1],
            query=_query(url.query),
            fragment=_query(url.fragment),
        )
        return value if clean == url else urlunsplit(clean)
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
    if content_type is not None and len(content_type) > 200:
        raise ValueError("Content-Type must be at most 200 characters")
    with session.no_autoflush:
        source = session.get(Source, source_id)
    if source is None or source.key != source_key:
        raise ValueError("Source id and key must match an existing source")
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
            for attempt in range(2):
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
                    code = exc.response["Error"]["Code"]
                    if code == "ConditionalRequestConflict" and attempt == 0:
                        continue
                    if code not in {"PreconditionFailed", "412"}:
                        raise
                break
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
            data = stream.read()
            body = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
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
