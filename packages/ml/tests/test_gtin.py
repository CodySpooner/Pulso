import pytest

from pulso_ml.matching.gtin import gtin14

WRIGLEY = "00036000291452"  # UPC-A 036000291452


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("036000291452", WRIGLEY),  # GTIN-12 (UPC-A)
        ("0036000291452", WRIGLEY),  # GTIN-13 (EAN-13) with a leading 0
        ("00036000291452", WRIGLEY),  # GTIN-14
        ("0-36000-29145-2", WRIGLEY),
        (" 036000 291452\n", WRIGLEY),
        ("4006381333931", "04006381333931"),  # EAN-13
        ("96385074", "00000096385074"),  # GTIN-8
        ("10036000291459", "10036000291459"),  # GTIN-14, a case of the UPC above
    ],
)
def test_valid_gtins_pad_to_14_digits(raw: str, expected: str) -> None:
    assert gtin14(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "036000291453",  # wrong check digit
        "0036000291451",
        "96385075",
        "03600029145",  # 11 digits
        "123456789",
        "036000291452A",
        "036000.291452",
        "٠٣٦٠٠٠٢٩١٤٥٢",  # Arabic-Indic digits, not ASCII
        "000000000000",  # placeholders, each with a valid check digit
        "00000000",
        "123456789012",
        "1234567890128",
        "012345678905",
        "987654321098",
        "212345678909",  # GS1 restricted circulation numbers: 020-029, 040-049, 200-299
        "418273645093",
        "2040000123451",
        "01234565",  # RCN-8: GS1-8 prefixes 0 and 2
        "21234569",
    ],
)
def test_invalid_missing_placeholder_and_restricted_gtins_are_ignored(raw: str | None) -> None:
    assert gtin14(raw) is None
