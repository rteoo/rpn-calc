import math

import pytest

from rpncalc.numeric import (
    ENG,
    FIX,
    SCI,
    STD,
    NumberFormat,
    format_number,
    localize_number,
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
            # The mathematically rounded value is above the float ceiling;
            # formatting backs off one display digit to remain parseable.
            (ENG, 3, 1.7976931348623157e308, "179.7E306"),
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
            ("100,000.0001", 100000.0001),  # US grouping, both marks
            ("100.000,0001", 100000.0001),  # EU grouping, both marks
            ("1,000E3", 1000.0),  # SCI comma decimal
            ("1,235E4", 12350.0),
            (",000", 0.0),
        ],
    )
    def test_parses(self, text, expected):
        assert parse_number(text) == expected

    @pytest.mark.parametrize(
        "text",
        ["not a number", "", "inf", "nan", "1/2", "1E3,", "1,000,00", "1,000,00E3"],
    )
    def test_rejects(self, text):
        assert parse_number(text) is None

    def test_a_four_digit_leading_group_is_a_decimal_comma(self):
        # Thousands groups are 1–3 digits, then threes. 1234,567 is 1234.567.
        assert parse_number("1234,567") == 1234.567

    def test_a_short_trailing_group_is_a_decimal_comma(self):
        assert parse_number("1,00") == 1.00
        assert parse_number("1,5") == 1.5

    def test_omacalc_treats_a_lone_comma_as_decimal(self):
        # Without the thousands setting, "1,000" is 1.0 just as "1,5" is 1.5.
        assert parse_number("1,000") == 1.0


class TestParseNumberLocale:
    """`100,001` is thousands or a decimal comma; the locale decides."""

    def test_thousands_comma_reads_grouping(self):
        assert parse_number("1,000", thousands=True) == 1000.0
        assert parse_number("+1,000", thousands=True) == 1000.0
        assert parse_number("-1,000,000", thousands=True) == -1_000_000.0
        assert parse_number("100,001", thousands=True) == 100001.0
        assert parse_number("1,000,000E3", thousands=True) == 1_000_000e3
        assert parse_number("+1,000,000E3", thousands=True) == 1_000_000e3

    def test_thousands_comma_still_accepts_a_decimal_comma(self):
        assert parse_number("1,5", thousands=True) == 1.5
        assert parse_number("1,00", thousands=True) == 1.0
        assert parse_number("1,235E4", thousands=True) == 12350.0
        assert parse_number("1,000E3", thousands=True) == 1000.0
        assert parse_number("1234,567", thousands=True) == 1234.567
        assert parse_number("1E3,", thousands=True) is None

    def test_decimal_comma_reads_a_lone_comma_as_decimal(self):
        assert parse_number("100,001", decimal=",") == 100.001
        assert parse_number("1,5", decimal=",") == 1.5
        assert parse_number("1,235E4", decimal=",") == 12350.0

    def test_decimal_comma_with_thousands_reads_dot_groups(self):
        assert parse_number("1.000", decimal=",", thousands=True) == 1000.0
        assert parse_number("100.001", decimal=",", thousands=True) == 100001.0
        assert parse_number("100.000,0001", decimal=",", thousands=True) == 100000.0001
        assert parse_number("1.5", decimal=",", thousands=True) == 1.5
        assert parse_number("1.000.000E3", decimal=",", thousands=True) == 1_000_000e3

    def test_rejects_an_unknown_decimal(self):
        with pytest.raises(ValueError, match="unknown decimal separator"):
            parse_number("1.5", decimal=";")


class TestLocalizeNumber:
    def test_identity_keeps_canonical_text(self):
        assert localize_number("100000.0001") == "100000.0001"
        assert localize_number("1.235E4") == "1.235E4"
        assert localize_number("1e+15") == "1e+15"

    def test_comma_decimal_swaps_the_point(self):
        assert localize_number("100.001", decimal=",") == "100,001"
        assert localize_number("1.235E4", decimal=",") == "1,235E4"
        assert localize_number("1e+15", decimal=",") == "1e+15"

    def test_thousands_uses_the_other_mark(self):
        assert localize_number("100000", thousands=True) == "100,000"
        assert localize_number("100000.0001", thousands=True) == "100,000.0001"
        assert localize_number("100000", decimal=",", thousands=True) == "100.000"
        assert localize_number("100000.0001", decimal=",", thousands=True) == (
            "100.000,0001"
        )

    def test_screenshot_values(self):
        assert localize_number("100", thousands=True) == "100"
        assert localize_number("100.001", thousands=True) == "100.001"
        assert localize_number("100000", thousands=True) == "100,000"
        assert localize_number("100000.0001", thousands=True) == "100,000.0001"

    def test_negative_keeps_the_sign_outside_the_groups(self):
        assert localize_number("-100000", thousands=True) == "-100,000"
        assert localize_number("-1000.5", decimal=",", thousands=True) == "-1.000,5"

    def test_small_integers_are_not_grouped(self):
        assert localize_number("100", thousands=True) == "100"
        assert localize_number("12", thousands=True) == "12"
        assert localize_number("1000", thousands=True) == "1,000"

    def test_seven_digits_make_two_separators(self):
        assert localize_number("1000000", thousands=True) == "1,000,000"

    def test_rejects_an_unknown_decimal(self):
        with pytest.raises(ValueError, match="unknown decimal separator"):
            localize_number("1.5", decimal=";")

    def test_localized_display_parses_back(self):
        samples = (
            0.0,
            100.0,
            100.001,
            100000.0,
            100000.0001,
            -1234.5,
            1 / 3,
            1e15,
            5e-4,
            12345.0,
        )
        locales = (
            (".", False),
            (".", True),
            (",", False),
            (",", True),
        )
        formats = (
            NumberFormat(STD),
            NumberFormat(FIX, 2),
            NumberFormat(SCI, 3),
            NumberFormat(ENG, 3),
        )
        for value in samples:
            for fmt in formats:
                canonical = format_number(value, fmt)
                expected = parse_number(canonical)
                for decimal, thousands in locales:
                    shown = localize_number(
                        canonical, decimal=decimal, thousands=thousands
                    )
                    assert parse_number(
                        shown, decimal=decimal, thousands=thousands
                    ) == expected, (
                        f"{fmt.mode} {value!r} → {canonical!r} → {shown!r}"
                    )
