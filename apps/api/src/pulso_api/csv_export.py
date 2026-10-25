"""CSV export (WF-7, DEC-316): a table's `?format=csv` streams its own query through here, so
every export has one format: UTF-8 with a BOM, ISO 8601 UTC times, money in major units."""

import csv
import io
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, Select, func, select
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from pulso_api.errors import APIError

MAX_ROWS = 50_000
CHUNK = 500  # rows per server-side fetch, and per batch of the caller's lookups
FORMULA = ("=", "+", "-", "@", "\t", "\r")  # a spreadsheet runs a cell starting so as a formula


def major(minor: int | None, exponent: int = 2) -> Decimal | None:
    """Minor units in major units, exactly: 1503 is 15.03 at exponent 2. Formatting, no math."""
    return None if minor is None else Decimal(minor).scaleb(-exponent)


def cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, int | float | Decimal):
        return str(value)  # a number is never a formula, so a loss stays -3.39
    text = str(value)
    # Titles and names come from competitor stores: untrusted (OWASP CSV injection).
    return f"'{text}" if text.startswith(FORMULA) else text


def csv_response(
    session: Session,
    table: str,
    header: Sequence[str],
    query: Select[Any],
    rows: Callable[[Sequence[Row[Any]]], Iterable[Sequence[object]]],
) -> StreamingResponse:
    """`query`'s rows as pulso_<table>_<date>.csv. Counted first, so a set over MAX_ROWS is a 422
    and no file; then streamed CHUNK rows at a time off a server-side cursor, `rows` turning each
    chunk into cells (a chunk at a time, so it can batch its lookups)."""
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    if total > MAX_ROWS:
        raise APIError(
            422,
            "export_too_large",
            f"{total:,} rows exceed the {MAX_ROWS:,} export limit. Narrow your filters.",
        )

    def body() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield "﻿" + buffer.getvalue()  # the BOM makes Excel on Windows read UTF-8
        for chunk in session.execute(query.execution_options(yield_per=CHUNK)).partitions():
            buffer.seek(0)
            buffer.truncate()
            writer.writerows([cell(value) for value in row] for row in rows(chunk))
            yield buffer.getvalue()

    filename = f"pulso_{table}_{datetime.now(UTC).date().isoformat()}.csv"
    return StreamingResponse(
        body(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Total-Count": str(total),  # the web says "Preparing N rows…" while the body streams
        },
    )
