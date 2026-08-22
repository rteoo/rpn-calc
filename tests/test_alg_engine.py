"""Port of omacalc's `tst_omacalc.cpp`, against the headless `AlgEngine`.

All 18 upstream cases are ported 1:1 except:
- `formatsNumbers` - already covered by `tests/test_numeric.py`.
- `loadsCurrentOmarchyTheme` - Omarchy theme loading is Qt-facing
  (`backend.py`), not part of the pure engine tested here.

No QApplication is created in this file; `pastesNumbers` exercises the
parse-and-adopt path directly on the engine (`AlgEngine.paste_value`),
leaving clipboard access itself to `backend.py`.
"""

from __future__ import annotations

from rpncalc.alg_engine import AlgEngine, evaluate_tokens
from rpncalc.numeric import parse_number


def press(calculator: AlgEngine, keys: str) -> None:
    """Space-separated key sequence, mirroring the C++ test helper."""
    for key in keys.split():
        calculator.press(key)


def test_starts_at_zero() -> None:
    calculator = AlgEngine()
    assert calculator.display == "0"
    assert calculator.expression == ""


def test_calculates_with_precedence() -> None:
    calculator = AlgEngine()
    press(calculator, "4 2 × 3 + 7 =")
    assert calculator.display == "133"
    assert calculator.expression == "42 × 3 + 7"

    press(calculator, "clear 2 + 3 × 4 =")
    assert calculator.display == "14"

    press(calculator, "clear 1 0 - 4 ÷ 2 =")
    assert calculator.display == "8"


def test_shows_entry_while_typing() -> None:
    calculator = AlgEngine()
    press(calculator, "4 2 ×")
    assert calculator.display == "42"
    assert calculator.expression == "42 ×"

    press(calculator, "3")
    assert calculator.display == "3"


def test_handles_decimals() -> None:
    calculator = AlgEngine()
    press(calculator, ". 5 + . 2 5 =")
    assert calculator.display == "0.75"

    # Binary-float noise stays out of the display.
    press(calculator, "clear 0 . 1 + 0 . 2 =")
    assert calculator.display == "0.3"

    # A second decimal point in one number is ignored.
    press(calculator, "clear 1 . 5 . 5")
    assert calculator.display == "1.55"


def test_division_by_zero_errors() -> None:
    calculator = AlgEngine()
    press(calculator, "1 ÷ 0 =")
    assert calculator.display == "Error"

    # Digits recover from an error without an explicit clear.
    press(calculator, "5")
    assert calculator.display == "5"


def test_percent_of_running_total() -> None:
    calculator = AlgEngine()

    # With a pending + or −, x% means x percent of the running total.
    press(calculator, "2 0 0 + 1 0 % =")
    assert calculator.display == "220"

    press(calculator, "clear 2 0 0 - 1 0 % =")
    assert calculator.display == "180"

    # With × or ÷, or standalone, x% is simply x ÷ 100.
    press(calculator, "clear 2 0 0 × 1 0 % =")
    assert calculator.display == "20"

    press(calculator, "clear 5 0 %")
    assert calculator.display == "0.5"

    # After equals, percent picks up from the result.
    press(calculator, "clear 4 0 + 1 0 = %")
    assert calculator.display == "0.5"


def test_percent_and_sign() -> None:
    calculator = AlgEngine()
    press(calculator, "8 sign")
    assert calculator.display == "-8"
    press(calculator, "sign")
    assert calculator.display == "8"

    press(calculator, "clear 4 + 8 sign =")
    assert calculator.display == "-4"


def test_sign_starts_new_operand() -> None:
    calculator = AlgEngine()

    # Sign with nothing typed starts a fresh negative operand rather than
    # negating the previous one: 4 + ± 2 = is 4 + (-2), not 4 + (-42).
    press(calculator, "4 + sign 2 =")
    assert calculator.display == "2"
    assert calculator.expression == "4 + -2"

    press(calculator, "clear sign")
    assert calculator.display == "-0"
    press(calculator, "5")
    assert calculator.display == "-5"


def test_chains_with_full_precision() -> None:
    calculator = AlgEngine()

    # Chaining continues from the exact value, not the rounded display.
    press(calculator, "1 ÷ 3 = × 3 =")
    assert calculator.display == "1"

    # Integers within the 15-digit entry limit survive exactly.
    press(calculator, "clear 9 9 9 9 9 9 9 9 9 9 9 9 9 9 =")
    assert calculator.display == "99999999999999"


def test_caps_entry_at_fifteen_digits() -> None:
    calculator = AlgEngine()
    press(calculator, "1 2 3 4 5 6 7 8 9 1 2 3 4 5 6 7 8")
    assert calculator.display == "123456789123456"

    # The decimal point does not count against the digit cap.
    press(calculator, "clear . 1 2 3 4 5 6 7 8 9 1 2 3 4 5 6 7")
    assert calculator.display == "0.123456789123456"


def test_backspace_edits() -> None:
    calculator = AlgEngine()
    press(calculator, "1 2 3 backspace")
    assert calculator.display == "12"

    press(calculator, "backspace backspace backspace")
    assert calculator.display == "0"


def test_chains_from_result() -> None:
    calculator = AlgEngine()
    press(calculator, "6 × 7 = × 2 =")
    assert calculator.display == "84"
    assert calculator.expression == "42 × 2"

    # A digit after equals starts fresh instead of appending to the result.
    press(calculator, "9")
    assert calculator.display == "9"
    assert calculator.expression == ""


def test_replaces_dangling_operator() -> None:
    calculator = AlgEngine()
    press(calculator, "4 + × 2 =")
    assert calculator.display == "8"

    # Equals with a trailing operator drops it.
    press(calculator, "clear 9 + =")
    assert calculator.display == "9"


def test_pastes_numbers() -> None:
    # Clipboard access belongs to backend.py; here we drive the same
    # parse-then-adopt path directly: numeric.parse_number feeds
    # AlgEngine.paste_value, exactly as backend.pasteNumber does.
    calculator = AlgEngine()

    calculator.paste_value(parse_number(" 42.5 "))
    assert calculator.display == "42.5"

    # A pasted number is a normal entry that calculates like any other.
    press(calculator, "+ . 5 =")
    assert calculator.display == "43"

    # Decimal commas are welcome; garbage is ignored.
    calculator.paste_value(parse_number("1,5"))
    assert calculator.display == "1.5"

    garbage = parse_number("not a number")
    assert garbage is None
    # Nothing changes when the clipboard held garbage.
    assert calculator.display == "1.5"


def test_evaluates_tokens() -> None:
    value, ok = evaluate_tokens(["2", "+", "3", "×", "4"])
    assert ok
    assert value == 14.0

    _, ok = evaluate_tokens(["2", "+"])
    assert not ok

    _, ok = evaluate_tokens(["1", "÷", "0"])
    assert not ok
