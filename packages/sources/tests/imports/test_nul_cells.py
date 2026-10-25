"""imp-311 (DEC-287): Postgres text can't hold NUL, so a NUL cell is its row's error and the
file's other rows import, as for any other invalid cell."""

from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import SearchTrend
from pulso_core.settings import Settings
from pulso_sources.imports import commit_import, parse_csv

from .test_merchant import GOOGLE, KEY


def test_a_nul_cell_is_a_row_error_and_the_other_rows_import(
    session: Session, settings: Settings, s3: MagicMock
) -> None:
    body = b"keyword,date,interest\na,2020-01-01,50\nb\x00,2020-01-02,30\nc\td,2020-01-03,20\n"
    run = commit_import(session, "google_trends", body, settings=settings)
    assert (run.status, run.rows_inserted) == ("success", 2)
    assert run.params["errors"] == [
        {"row": 3, "column": "keyword", "message": "Invalid text value"}
    ]
    assert sorted(session.scalars(select(SearchTrend.keyword))) == ["a", "c\td"]


def test_a_nul_in_the_merchant_filters_line_is_every_rows_category_error() -> None:
    parsed = parse_csv(KEY, GOOGLE.replace(b"Category = Home", b"Category = Ho\x00me"))
    assert parsed.rows == []
    assert {(error.row, error.column) for error in parsed.errors} == {
        (row, "category") for row in (2, 3, 4)
    }
