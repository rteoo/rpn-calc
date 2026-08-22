"""Number formatting and parsing, shared by both calculator engines.

`format_number` is a port of omacalc's `Backend::formatNumber`; the FIX/SCI/ENG
modes extend it with the HP 50g's display formats. Everything here is pure - the
stack always holds full-precision floats, and formatting happens only at the
display boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# omacalc writes operators with typographic glyphs; tokens carry them verbatim.
MINUS_SIGN = "\u2212"
MULTIPLY_SIGN = "\u00d7"
DIVIDE_SIGN = "\u00f7"
PLUS_SIGN = "+"

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
    """Render `value` for the display."""
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


def roundtrip(value: float) -> str:
    """Full-precision text, for carrying an exact value between operations."""
    return f"{value:.{ROUNDTRIP_PRECISION}g}"


def _format_fix(value: float, digits: int) -> str:
    # The 50g falls back to scientific when a number is too wide to show with
    # the requested decimals; 1e12 is where a 12-column display gives out.
    if value != 0 and abs(value) >= 1e12:
        return _format_sci(value, digits)
    text = f"{value:.{digits}f}"
    # A small negative that rounds away to nothing must not display as "-0.00".
    if text.startswith("-") and float(text) == 0:
        return text[1:]
    return text


def _format_sci(value: float, digits: int) -> str:
    mantissa, exponent = _split_exponent(value, digits)
    return f"{mantissa:.{digits}f}E{exponent}"


def _format_eng(value: float, digits: int) -> str:
    if value == 0:
        return f"{0.0:.{digits}f}E0"

    # Round once, at the end. Rounding to `digits` first and then rescaling the
    # mantissa would round twice and lose the last significant digit: 12345 at
    # ENG 3 must read 12.35E3, not 12.34E3.
    _, exponent = _split_exponent(value, digits)
    eng_exponent = 3 * math.floor(exponent / 3)
    decimals = max(digits - (exponent - eng_exponent), 0)
    mantissa = value / 10.0**eng_exponent

    # A mantissa that rounds up out of its decade belongs in the next one.
    if abs(round(mantissa, decimals)) >= 1000:
        eng_exponent += 3
        decimals = max(digits - (exponent - eng_exponent), 0)
        mantissa = value / 10.0**eng_exponent

    return f"{mantissa:.{decimals}f}E{eng_exponent}"


def _split_exponent(value: float, digits: int) -> tuple[float, int]:
    """Mantissa in [1, 10) (or 0) and its base-10 exponent, rounded to `digits`."""
    if value == 0:
        return 0.0, 0
    # Round first, then read the exponent back: rounding 9.99 to 1 decimal
    # gives 10.0, which belongs in the next decade.
    text = f"{value:.{digits}e}"
    mantissa_text, exponent_text = text.split("e")
    return float(mantissa_text), int(exponent_text)


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


def parse_number(text: str) -> float | None:
    """Read a number the way paste does: tolerant of spaces, typographic minus,
    a decimal comma, and the HP's `E` exponent marker. None if it is not a number.
    """
    cleaned = text.strip().replace(MINUS_SIGN, "-").replace(" ", "")
    for candidate in (cleaned, cleaned.replace(",", ".")):
        try:
            value = float(candidate)
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    return None
