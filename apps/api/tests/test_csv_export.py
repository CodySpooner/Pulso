from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from pulso_api.csv_export import cell, major


@pytest.mark.parametrize("text", ["=1+1", "+1", "-2", "@SUM(A1)", "\tx", "\rx"])
def test_a_text_cell_a_spreadsheet_would_run_gets_a_quote(text: str) -> None:
    assert cell(text) == f"'{text}"


def test_cells_format_one_way() -> None:
    assert cell(None) == ""
    assert (cell(True), cell(False)) == ("true", "false")
    assert cell(datetime(2026, 10, 25, 9, 30, tzinfo=timezone(timedelta(hours=2)))) == (
        "2026-10-25T07:30:00Z"
    )
    assert cell(datetime(2026, 10, 25, tzinfo=UTC)) == "2026-10-25T00:00:00Z"
    assert (cell(-3), cell(Decimal("-3.39")), cell(0.5)) == ("-3", "-3.39", "0.5")  # numbers
    assert cell(UUID(int=1)) == "00000000-0000-0000-0000-000000000001"
    assert cell("Sunset lamp, 2-pack") == "Sunset lamp, 2-pack"  # csv quotes the comma


def test_money_is_major_units_exactly() -> None:
    assert [str(major(v)) for v in (1503, 1500, -339, 0, 7)] == [
        "15.03",
        "15.00",
        "-3.39",
        "0.00",
        "0.07",
    ]
    assert str(major(500, exponent=0)) == "500"  # JPY
    assert major(None) is None
