"""GTIN normaliser for the barcode shortcut (M-4, DEC-255): valid codes only, never guessed."""

import re
from itertools import pairwise


def gtin14(raw: str | None) -> str | None:
    """A valid GTIN-8, -12, -13 or -14 left-padded to 14 digits, else None.

    Spaces and dashes are stripped. Rejected: any other length or character, a wrong GS1
    mod-10 check digit, a placeholder, and a GS1 Restricted Circulation Number.
    """
    digits = re.sub(r"[\s-]", "", raw or "")
    if not re.fullmatch(r"[0-9]{8}|[0-9]{12,14}", digits):
        return None
    code = digits.zfill(14)
    weighted = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(code[-2::-1]))
    if -weighted % 10 != int(code[-1]):
        return None
    # Placeholders: all zeros, one repeated digit, or a 1-2-3 / 9-8-7 run once leading
    # zeros are dropped (123456789012 and 012345678905 carry valid check digits).
    body = code[:-1].lstrip("0")
    steps = {(int(b) - int(a)) % 10 for a, b in pairwise(body)}
    if len(steps) <= 1 and steps <= {0, 1, 9}:
        return None
    # Restricted Circulation Numbers are company- or region-internal, so two vendors can
    # use one for different things: GS1-8 prefixes 0 and 2 (a GTIN-8 pads to six zeros),
    # and GS1 prefixes 020-029, 040-049 and 200-299.
    if code.startswith("000000"):
        return None if code[6] in "02" else code
    return None if code[1] == "2" or code[1:3] in ("02", "04") else code
