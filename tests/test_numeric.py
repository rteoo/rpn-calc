import math

import pytest

from rpncalc.numeric import (
    ENG,
    FIX,
    SCI,
    STD,
    NumberFormat,
    format_number,
    parse_number,
    roundtrip,
    seal_number,
)


class TestFormatNumberStd:
    """Ported from omacalc's `formatsNumbers`."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (133, "133"),
            (0.1 + 0.2, "0.3"),
            (-0.0, "0"),
            (1e15, "1e+15"),
            (99999999999999, "99999999999999"),
            (1 / 3, "0.333333333333333"),
        ],
    )
    def test_matches_qt_g15(self, value, expected):
        assert format_number(value) == expected

    def test_rejects_non_finite(self):
        for value in (math.inf, -math.inf, math.nan):
            with pytest.raises(ValueError):
                format_number(value)


class TestDisplayFormats:
    @pytest.mark.parametrize(
        "mode, digits, value, expected",
        [
            (FIX, 2, 1 / 3, "0.33"),
            (FIX, 0, 2.5, "3"),  # half away from zero, as a calculator rounds
            (FIX, 0, 3.5, "4"),
            (FIX, 1, 0.25, "0.3"),
            (FIX, 3, -0.0001, "0.000"),  # negative zero never survives display
            (FIX, 2, 1e13, "1.00E13"),  # too wide for fixed: falls back to SCI
            (SCI, 3, 12345, "1.235E4"),
            (SCI, 2, 0.000123, "1.23E-4"),
            (ENG, 3, 12345, "12.35E3"),  # exponent snaps to a multiple of 3
            (ENG, 3, 0.000123, "123.0E-6"),
            (ENG, 3, 999999, "1.000E6"),  # rounding up moves to the next decade
            (ENG, 3, 0, "0.000E0"),
            # The ends of the double range: scaling by a power of ten used to
            # divide by zero here and take the display down with it.
            (ENG, 3, 5e-324, "4.941E-324"),
            (SCI, 3, 5e-324, "4.941E-324"),
            (ENG, 3, 1.7976931348623157e308, "179.8E306"),
        ],
    )
    def test_formats(self, mode, digits, value, expected):
        assert format_number(value, NumberFormat(mode, digits)) == expected

    def test_eng_keeps_significant_digits(self):
        # ENG n and SCI n show the same count of significant digits.
        eng = format_number(12345, NumberFormat(ENG, 3)).split("E")[0]
        sci = format_number(12345, NumberFormat(SCI, 3)).split("E")[0]
        assert len(eng.replace(".", "")) == len(sci.replace(".", "")) == 4

    def test_labels(self):
        assert NumberFormat(STD).label() == "STD"
        assert NumberFormat(FIX, 4).label() == "FIX 4"

    def test_rejects_bad_format(self):
        with pytest.raises(ValueError):
            NumberFormat("HEX")
        with pytest.raises(ValueError):
            NumberFormat(FIX, 99)


class TestRoundtrip:
    def test_survives_a_float(self):
        for value in (1 / 3, 1e-300, 123456789.123456789, -2.5):
            assert float(roundtrip(value)) == value


class TestSealNumber:
    @pytest.mark.parametrize(
        "entry, expected",
        [("5.", "5"), ("", "0"), ("-", "0"), ("-0", "-0"), ("42", "42"), ("0.5", "0.5")],
    )
    def test_seals(self, entry, expected):
        assert seal_number(entry) == expected


class TestParseNumber:
    """Ported from omacalc's `pastesNumbers` tolerances."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            (" 42.5 ", 42.5),
            ("1,5", 1.5),
            ("\u22128", -8.0),  # typographic minus
            ("1 000", 1000.0),
            ("1.5E3", 1500.0),
        ],
    )
    def test_parses(self, text, expected):
        assert parse_number(text) == expected

    @pytest.mark.parametrize("text", ["not a number", "", "inf", "nan", "1/2"])
    def test_rejects(self, text):
        assert parse_number(text) is None
