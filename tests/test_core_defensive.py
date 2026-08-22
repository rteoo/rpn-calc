"""The guard clauses.

Most of these cannot be reached by pressing keys - the entry logic only ever
produces digits, a dot, a minus and an E, so a malformed token is a bug in the
engine rather than something a user can type. They still have to behave, because
the whole point of them is what happens when an assumption stops holding, and
untested error handling is where a crash hides.

Reaching them means calling the internals directly. That is deliberate.
"""

from __future__ import annotations

import math

import pytest

from rpncalc import numeric
from rpncalc.alg_engine import AlgEngine, evaluate_tokens, pretty_expression
from rpncalc.numeric import (
    DIVIDE_SIGN,
    MINUS_SIGN,
    MULTIPLY_SIGN,
    PLUS_SIGN,
    NumberFormat,
)
from rpncalc.rpn_engine import CalcError, RpnEngine, _parse_token
from rpncalc.stack import RpnStack, StackError


class TestNumericGuards:
    def test_decimal_exponent_of_zero(self):
        assert numeric._decimal_exponent(0.0, 3) == 0

    def test_format_rejects_non_finite(self):
        for value in (math.inf, -math.inf, math.nan):
            with pytest.raises(ValueError):
                numeric.format_number(value)

    def test_quantise_rounds_half_away_from_zero(self):
        from decimal import Decimal

        assert numeric._quantise(Decimal("2.5"), 0) == Decimal("3")
        assert numeric._quantise(Decimal("-2.5"), 0) == Decimal("-3")
        assert numeric._quantise(Decimal("2.4"), 0) == Decimal("2")

    def test_number_format_validates(self):
        with pytest.raises(ValueError):
            NumberFormat("BINARY")
        with pytest.raises(ValueError):
            NumberFormat("FIX", -1)
        with pytest.raises(ValueError):
            NumberFormat("FIX", 12)


class TestRpnEngineGuards:
    def test_evaluate_reports_a_value_error_as_bad_input(self):
        def raises_value_error(_x: float) -> float:
            raise ValueError("out of domain")

        with pytest.raises(CalcError, match="Invalid Input"):
            RpnEngine._evaluate(raises_value_error, 1.0)

    def test_evaluate_reports_overflow_as_infinite(self):
        def overflows(_x: float) -> float:
            raise OverflowError

        with pytest.raises(CalcError, match="Infinite Result"):
            RpnEngine._evaluate(overflows, 1.0)

    def test_evaluate_reports_division_by_zero_as_infinite(self):
        def divides_by_zero(_x: float) -> float:
            return 0.0 ** -1

        with pytest.raises(CalcError, match="Infinite Result"):
            RpnEngine._evaluate(divides_by_zero, 1.0)

    def test_evaluate_refuses_a_complex_result(self):
        with pytest.raises(CalcError, match="Invalid Input"):
            RpnEngine._evaluate(lambda _x: complex(1, 1), 1.0)

    def test_parse_token_rejects_a_token_the_keys_cannot_produce(self):
        with pytest.raises(CalcError, match="Invalid Input"):
            _parse_token("not-a-number")

    def test_parse_token_reports_overflow_separately(self):
        with pytest.raises(CalcError, match="Infinite Result"):
            _parse_token("1E999")

    def test_parse_token_tolerates_a_half_typed_entry(self):
        assert _parse_token("5.") == 5.0
        assert _parse_token("-") == 0.0
        assert _parse_token("1E") == 1.0
        assert _parse_token("1E-") == 1.0

    def test_paste_refuses_a_non_finite_value(self):
        engine = RpnEngine()
        with pytest.raises(CalcError, match="Infinite Result"):
            engine.paste_value(math.inf)
        assert engine.depth == 0

    def test_undo_with_nothing_recorded_does_nothing(self):
        engine = RpnEngine()
        engine.press("undo")
        assert engine.depth == 0
        assert engine.error is None

    def test_apply_command_rejects_an_unknown_key(self):
        # _dispatch filters these out, so only a direct call can reach it.
        with pytest.raises(ValueError, match="unknown key id"):
            RpnEngine()._apply_command("nonsense")

    def test_set_angle_mode_validates(self):
        with pytest.raises(ValueError, match="unknown angle mode"):
            RpnEngine().set_angle_mode("GRAD")

    def test_copy_text_of_an_empty_stack(self):
        assert RpnEngine().copy_text() == ""

    def test_knows_normalises_typographic_operators(self):
        engine = RpnEngine()
        for glyph in (MINUS_SIGN, MULTIPLY_SIGN, DIVIDE_SIGN, PLUS_SIGN):
            assert engine.knows(glyph)

    def test_reorder_commands_reject_a_bad_count(self):
        for command in ("roll", "rolld", "pick"):
            engine = RpnEngine()
            engine.stack.push(1.0)
            engine.stack.push(0.0)  # a count of zero is not a level
            engine.press(command)
            assert engine.error == "Too Few Arguments"
            assert engine.stack.to_list() == [0.0, 1.0]

    def test_reorder_commands_reject_a_count_deeper_than_the_stack(self):
        engine = RpnEngine()
        engine.stack.push(1.0)
        engine.stack.push(9.0)
        engine.press("roll")
        assert engine.error == "Too Few Arguments"
        assert engine.stack.to_list() == [9.0, 1.0]


class TestStackGuards:
    def test_every_command_underflows_cleanly_on_an_empty_stack(self):
        stack = RpnStack()
        for operation in (
            stack.pop, stack.drop, stack.swap, stack.dup, stack.over,
            stack.rot, stack.unrot,
        ):
            with pytest.raises(StackError, match="Too Few Arguments"):
                operation()
            assert stack.depth == 0

    def test_clear_and_depth_work_on_an_empty_stack(self):
        stack = RpnStack()
        stack.clear()
        stack.depth_command()
        assert stack.to_list() == [0.0]

    def test_dropn_and_dupn_of_zero_are_no_ops(self):
        stack = RpnStack()
        stack.push(1.0)
        stack.dropn(0)
        stack.dupn(0)
        assert stack.to_list() == [1.0]


class TestAlgEngineGuards:
    def test_divide_reproduces_ieee_semantics_without_raising(self):
        from rpncalc.alg_engine import _divide

        assert _divide(1.0, 0.0) == math.inf
        assert _divide(-1.0, 0.0) == -math.inf
        assert math.isnan(_divide(0.0, 0.0))
        assert _divide(1.0, -0.0) == -math.inf
        assert _divide(6.0, 3.0) == 2.0

    @pytest.mark.parametrize(
        "tokens",
        [
            [],                                   # empty
            ["1", PLUS_SIGN],                     # even length
            ["nonsense"],                         # unparseable first operand
            ["1", "?", "2"],                      # not an operator
            ["1", PLUS_SIGN, "nonsense"],         # unparseable operand
            ["1", DIVIDE_SIGN, "0"],              # non-finite result
        ],
    )
    def test_malformed_token_lists_report_failure(self, tokens):
        value, ok = evaluate_tokens(tokens)
        assert ok is False
        assert value == 0.0

    def test_a_well_formed_list_succeeds(self):
        value, ok = evaluate_tokens(["2", PLUS_SIGN, "3", MULTIPLY_SIGN, "4"])
        assert ok is True
        assert value == 14.0

    def test_pretty_expression_formats_operands_for_display(self):
        assert pretty_expression(["42", MULTIPLY_SIGN, "3"]) == f"42 {MULTIPLY_SIGN} 3"
        # Chained results carry round-trip precision; the display re-rounds them.
        assert pretty_expression(["0.30000000000000004"]) == "0.3"

    def test_keys_the_algebraic_engine_does_not_know_are_ignored(self):
        engine = AlgEngine()
        engine.press("7")
        for key in ("enter", "swap", "sqrt", "", "zz"):
            engine.press(key)
        assert engine.display == "7"

    def test_operator_before_any_digit_starts_from_zero(self):
        engine = AlgEngine()
        engine.press(MULTIPLY_SIGN)
        engine.press("5")
        engine.press("=")
        assert engine.display == "0"

    def test_a_second_operator_replaces_the_first(self):
        engine = AlgEngine()
        for key in ("4", PLUS_SIGN, MULTIPLY_SIGN, "2", "="):
            engine.press(key)
        assert engine.display == "8"

    def test_equals_with_nothing_entered_does_nothing(self):
        engine = AlgEngine()
        engine.press("=")
        assert engine.display == "0"
        assert engine.expression == ""

    def test_percent_of_an_unparseable_state_is_ignored(self):
        engine = AlgEngine()
        engine.press("%")
        assert engine.display == "0"

    def test_error_state_absorbs_operators_and_percent(self):
        engine = AlgEngine()
        for key in ("1", DIVIDE_SIGN, "0", "="):
            engine.press(key)
        assert engine.display == "Error"
        for key in (PLUS_SIGN, "%", "sign"):
            engine.press(key)
            assert engine.display == "Error"

    def test_backspace_clears_an_error(self):
        engine = AlgEngine()
        for key in ("1", DIVIDE_SIGN, "0", "="):
            engine.press(key)
        assert engine.display == "Error"
        engine.press("backspace")
        assert engine.display == "0"

    def test_paste_replaces_an_error_state(self):
        engine = AlgEngine()
        for key in ("1", DIVIDE_SIGN, "0", "="):
            engine.press(key)
        engine.paste_value(42.5)
        assert engine.display == "42.5"

    def test_digit_entry_stops_at_fifteen_significant_digits(self):
        engine = AlgEngine()
        for digit in "1234567890123456789":
            engine.press(digit)
        assert len(engine.display.replace("-", "")) == 15

    def test_a_leading_zero_is_replaced_rather_than_appended(self):
        engine = AlgEngine()
        engine.press("0")
        engine.press("5")
        assert engine.display == "5"

    def test_a_leading_negative_zero_is_replaced_too(self):
        engine = AlgEngine()
        engine.press("sign")
        assert engine.display == "-0"
        engine.press("5")
        assert engine.display == "-5"


class TestAlgEngineStateTransitions:
    """The paths between the engine's three states - typing, just-evaluated and
    errored - which the example tests exercise less than the arithmetic."""

    def errored(self) -> AlgEngine:
        engine = AlgEngine()
        for key in ("1", DIVIDE_SIGN, "0", "="):
            engine.press(key)
        assert engine.display == "Error"
        return engine

    def evaluated(self) -> AlgEngine:
        engine = AlgEngine()
        for key in ("4", "2", PLUS_SIGN, "1", "="):
            engine.press(key)
        assert engine.display == "43"
        return engine

    def test_a_decimal_point_recovers_from_an_error(self):
        engine = self.errored()
        engine.press(".")
        assert engine.display == "0."

    def test_a_decimal_point_after_equals_starts_a_new_number(self):
        engine = self.evaluated()
        engine.press(".")
        assert engine.display == "0."
        assert engine.expression == ""

    def test_equals_twice_does_not_re_evaluate(self):
        engine = self.evaluated()
        engine.press("=")
        assert engine.display == "43"
        assert engine.expression == f"42 {PLUS_SIGN} 1"

    def test_equals_while_errored_stays_errored(self):
        engine = self.errored()
        engine.press("=")
        assert engine.display == "Error"

    def test_sign_after_equals_edits_the_result(self):
        engine = self.evaluated()
        engine.press("sign")
        assert engine.display == "-43"
        # Editing picks up from the result, with the old expression cleared.
        assert engine.expression == ""

    def test_backspace_after_equals_edits_the_result(self):
        engine = self.evaluated()
        engine.press("backspace")
        assert engine.display == "4"
        assert engine.expression == ""

    def test_backspace_removes_a_lone_minus(self):
        engine = AlgEngine()
        engine.press("sign")
        assert engine.display == "-0"
        engine.press("backspace")
        engine.press("backspace")
        assert engine.display == "0"

    def test_percent_gives_up_on_an_unparseable_current_value(self):
        # current_value() can only fail if the token list has been corrupted,
        # which pressing keys cannot do - so corrupt it deliberately, call the
        # guard, and put it back. `display` assumes valid tokens by contract and
        # is not part of what is under test here.
        engine = AlgEngine()
        engine._tokens = ["not-a-number"]
        engine.press_percent()  # must return quietly rather than raise
        assert engine._entry == ""
        engine._tokens = []
        assert engine.display == "0"


class TestPartialBranches:
    """Two branches that only a specific sequence reaches."""

    def test_percent_falls_back_when_the_running_total_is_unusable(self):
        # "1 / 0 + 10 %": percent-of-the-running-total needs the left side to
        # evaluate, and here it does not, so it falls back to a plain x/100.
        engine = AlgEngine()
        for key in ("1", DIVIDE_SIGN, "0", PLUS_SIGN):
            engine.press(key)
        assert engine._tokens == ["1", DIVIDE_SIGN, "0", PLUS_SIGN]
        engine.press("5")
        engine.press("%")
        assert engine.display == "0.05"  # 5/100, not 5% of an infinite total

    def test_a_second_space_does_not_double_the_separator(self):
        engine = RpnEngine()
        for key in ("5", "spc", "spc", "spc"):
            engine.press(key)
        assert engine.command_line == "5 "
        engine.press("3")
        engine.press("enter")
        assert engine.stack_lines() == ["3", "5"]

    def test_space_on_an_empty_command_line_is_ignored(self):
        engine = RpnEngine()
        engine.press("spc")
        assert engine.command_line is None
        assert engine.depth == 0
