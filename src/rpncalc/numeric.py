"""Number formatting and parsing, shared by both calculator engines.

`format_number` is a port of omacalc's `Backend::formatNumber`; the FIX/SCI/ENG
modes extend it with the HP 50g's display formats. Everything here is pure - the
stack always holds full-precision floats, and formatting happens only at the
display boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, getcontext

# omacalc writes operators with typographic glyphs; tokens carry them verbatim.
MINUS_SIGN = "\u2212"
MULTIPLY_SIGN = "\u00d7"
DIVIDE_SIGN = "\u00f7"
PLUS_SIGN = "+"

# Wide enough that scaling a double never loses a digit to the context.
getcontext().prec = 40

STD = "STD"
FIX = "FIX"
SCI = "SCI"
ENG = "ENG"

# Fifteen significant digits keeps binary-float noise like 0.1 + 0.2 =
# 0.30000000000000004 out of the display while showing every integer the
# 15-digit entry limit can produce exactly.
DISPLAY_PRECISION = 15

# Seventeen significant digits round-trip any double, so chained results carry
# their exact value forward even though the display re-rounds them.
ROUNDTRIP_PRECISION = 17


@dataclass(frozen=True)
class NumberFormat:
    """How results are rendered. `digits` is ignored in STD mode."""

    mode: str = STD
    digits: int = 3

    def __post_init__(self) -> None:
        if self.mode not in (STD, FIX, SCI, ENG):
            raise ValueError(f"unknown number format: {self.mode!r}")
        if not 0 <= self.digits <= 11:
            raise ValueError(f"digits out of range: {self.digits!r}")

    def label(self) -> str:
        return self.mode if self.mode == STD else f"{self.mode} {self.digits}"


def format_number(value: float, fmt: NumberFormat | None = None) -> str:
    """Render `value` for the display.

    Always canonical: ASCII minus, ``.`` as the decimal point, no grouping.
    `localize_number` is what turns that into a comma decimal or thousands
    separators, and only at the QML boundary - ECHO, EDIT, and the command
    line keep this form so they stay parseable.
    """
    if value == 0:
        value = 0.0  # Collapse negative zero.
    if not math.isfinite(value):
        raise ValueError("cannot format a non-finite value")

    fmt = fmt or NumberFormat()
    if fmt.mode == STD:
        return f"{value:.{DISPLAY_PRECISION}g}"
    if fmt.mode == FIX:
        return _format_fix(value, fmt.digits)
    if fmt.mode == SCI:
        return _format_sci(value, fmt.digits)
    return _format_eng(value, fmt.digits)


def localize_number(
    text: str, *, decimal: str = ".", thousands: bool = False
) -> str:
    """Apply a decimal comma and/or thousands grouping to canonical text.

    `text` is what `format_number` returned: ``.`` as the decimal point, an
    optional ``e``/``E`` exponent, no grouping. The thousands mark is the
    other punctuation from `decimal` - comma decimal gets ``.`` grouping,
    and the other way around.
    """
    if decimal not in (".", ","):
        raise ValueError(f"unknown decimal separator: {decimal!r}")
    if decimal == "." and not thousands:
        return text

    thousands_mark = "," if decimal == "." else "."

    sign = ""
    body = text
    if body.startswith("-"):
        sign = "-"
        body = body[1:]

    exponent_at = next((i for i, char in enumerate(body) if char in "eE"), -1)
    if exponent_at >= 0:
        mantissa = body[:exponent_at]
        suffix = body[exponent_at:]
    else:
        mantissa = body
        suffix = ""

    if "." in mantissa:
        integer, fraction = mantissa.split(".", 1)
        frac_part = decimal + fraction
    else:
        integer = mantissa
        frac_part = ""

    if thousands:
        integer = _group_thousands(integer, thousands_mark)

    return sign + integer + frac_part + suffix


def _group_thousands(digits: str, separator: str) -> str:
    if len(digits) <= 3:
        return digits
    groups: list[str] = []
    rest = digits
    while rest:
        groups.append(rest[-3:])
        rest = rest[:-3]
    return separator.join(reversed(groups))


def roundtrip(value: float) -> str:
    """Full-precision text, for carrying an exact value between operations."""
    return f"{value:.{ROUNDTRIP_PRECISION}g}"


def _format_fix(value: float, digits: int) -> str:
    # The 50g falls back to scientific when a number is too wide to show with
    # the requested decimals; 1e12 is where a 12-column display gives out.
    if value != 0 and abs(value) >= 1e12:
        return _format_sci(value, digits)
    quantised = _quantise(Decimal(value), digits)
    text = f"{quantised:.{digits}f}"
    # A small negative that rounds away to nothing must not display as "-0.00".
    if text.startswith("-") and quantised == 0:
        return text[1:]
    return text


def _format_sci(value: float, digits: int) -> str:
    if value == 0:
        return f"{0.0:.{digits}f}E0"
    exponent = _decimal_exponent(value, digits)
    mantissa = _quantise(Decimal(value).scaleb(-exponent), digits)
    return f"{mantissa:.{digits}f}E{exponent}"


def _format_eng(value: float, digits: int) -> str:
    if value == 0:
        return f"{0.0:.{digits}f}E0"

    # Round once, at the end. Rounding to `digits` first and then rescaling the
    # mantissa would round twice and lose the last significant digit.
    exponent = _decimal_exponent(value, digits)
    eng_exponent = 3 * math.floor(exponent / 3)
    # No decade-bump guard is needed here: `_decimal_exponent` already rounds
    # before choosing the exponent, so the mantissa cannot reach 1000. Checked
    # by brute force over ~480k value/digit combinations before removing it.
    decimals = max(digits - (exponent - eng_exponent), 0)
    mantissa = _quantise(Decimal(value).scaleb(-eng_exponent), decimals)
    return f"{mantissa:.{decimals}f}E{eng_exponent}"


def _quantise(value: Decimal, decimals: int) -> Decimal:
    """Round to `decimals` places, half away from zero.

    Calculators round 2.5 to 3, not to 2. Python and IEEE-754 round half to
    even, which is better for accumulating sums and worse for reading a display
    - and the three formats here disagreed with each other about it until this
    became an explicit choice.

    Scaling happens in Decimal rather than by dividing by a power of ten:
    at the ends of the double range that power is itself zero or infinity, and
    5e-324 divided by zero took the whole display down with it.
    """
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def _decimal_exponent(value: float, digits: int) -> int:
    """The power of ten `value` sits on, once rounded to `digits` + 1 figures.

    Rounding first matters: 9.99 to one decimal is 10.0, which belongs in the
    next decade and would otherwise be reported as 10.0E0 instead of 1.0E1.
    """
    exact = Decimal(value)
    if exact == 0:
        return 0
    magnitude = exact.adjusted()
    rounded = exact.quantize(
        Decimal(1).scaleb(magnitude - digits), rounding=ROUND_HALF_UP
    )
    return rounded.adjusted()


def seal_number(entry: str) -> str:
    """Turn a half-typed entry into a plain number.

    Digits are entered raw, so "5." and "-" can linger while typing. Port of
    omacalc's `sealNumber`.
    """
    sealed = entry
    if sealed.endswith("."):
        sealed = sealed[:-1]
    if sealed == "" or sealed == "-":
        return "0"
    return sealed


def parse_number(
    text: str, *, decimal: str = ".", thousands: bool = False
) -> float | None:
    """Read a number the way paste does: tolerant of spaces, typographic minus,
    a decimal comma, thousands grouping in either locale, and the HP's `E`
    exponent marker. None if it is not a number.

    `decimal` and `thousands` are the active display locale, so copy/paste
    of what this calculator itself showed round-trips. `100,001` is one
    hundred thousand and one with a thousands comma, and 100.001 with a
    decimal comma; the locale is what distinguishes them. Both marks
    together (``100,000.0001`` / ``100.000,0001``) are unambiguous either way.
    """
    if decimal not in (".", ","):
        raise ValueError(f"unknown decimal separator: {decimal!r}")
    cleaned = text.strip().replace(MINUS_SIGN, "-").replace(" ", "")
    if not cleaned:
        return None
    candidate = _canonical_number_text(
        cleaned, decimal=decimal, thousands=thousands
    )
    try:
        value = float(candidate)
    except ValueError:
        return None
    if math.isfinite(value):
        return value
    return None


def _canonical_number_text(text: str, *, decimal: str, thousands: bool) -> str:
    """Strip grouping and turn a decimal comma into ``.``."""
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            # 100.000,0001 — comma is the decimal, dots are grouping.
            return text.replace(".", "").replace(",", ".")
        # 100,000.0001 — dot is the decimal, commas are grouping.
        return text.replace(",", "")

    if decimal == ",":
        if last_dot >= 0 and thousands and _is_thousands_grouping(text, "."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", ".")

    if last_comma >= 0:
        if thousands and _is_thousands_grouping(text, ","):
            return text.replace(",", "")
        return text.replace(",", ".")
    return text


def _is_thousands_grouping(text: str, separator: str) -> bool:
    """True when `separator` only appears as groups of three digits.

    A single comma in a scientific mantissa (``1,235E4``) is a decimal comma,
    not thousands: SCI/ENG never group the integer part, so that form is how
    a comma-decimal display writes ``1.235E4``. Two or more groups with an
    exponent (``1,000,000E3``) are still thousands.
    """
    mantissa = text[1:] if text[:1] in "+-" else text
    lowered = mantissa.lower()
    exponent_at = lowered.find("e")
    if exponent_at >= 0:
        mantissa = mantissa[:exponent_at]
    parts = mantissa.split(separator)
    min_parts = 3 if exponent_at >= 0 else 2
    if len(parts) < min_parts:
        return False
    if not parts[0].isdigit() or not 1 <= len(parts[0]) <= 3:
        return False
    return all(part.isdigit() and len(part) == 3 for part in parts[1:])
