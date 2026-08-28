"""Tests for RpnEngine: the command-line-open vs command-line-empty table
that is the entire point of CP3, plus the CP4 scientific function set.
"""

from __future__ import annotations

import math

import pytest

from rpncalc.numeric import FIX, NumberFormat
from rpncalc.numeric import format_number
from rpncalc.rpn_engine import DEFAULT_ANGLE_MODE, RpnEngine


def press(engine: RpnEngine, keys: str) -> None:
    """Space-separated key ids, e.g. press(engine, "3 enter 4 +")."""
    for key in keys.split():
        engine.press(key)


def new_engine() -> RpnEngine:
    return RpnEngine()


# -- canonical sequences from the plan ---------------------------------------


def test_enter_then_add() -> None:
    e = new_engine()
    press(e, "3 enter 4 +")
    assert e.depth == 1
    assert e.stack.peek(1) == 7
    assert e.error is None


def test_spc_separated_entry_pushes_left_to_right() -> None:
    e = new_engine()
    press(e, "3 spc 4 enter")
    assert e.depth == 2
    assert e.stack.peek(1) == 4
    assert e.stack.peek(2) == 3
    assert e.command_line is None


def test_enter_on_empty_command_line_dups_level_1() -> None:
    e = new_engine()
    press(e, "2 enter enter")
    assert e.depth == 2
    assert e.stack.peek(1) == 2
    assert e.stack.peek(2) == 2


def test_backspace_closes_entry_then_drops() -> None:
    e = new_engine()
    press(e, "9 enter")  # something on the stack for DROP to remove
    press(e, "5")
    assert e.command_line == "5"
    press(e, "backspace")
    assert e.command_line is None
    assert e.depth == 1  # the "5" entry never got pushed
    press(e, "backspace")
    assert e.depth == 0  # DROP fired on the empty command line


def test_backspace_deletes_last_character_when_open() -> None:
    e = new_engine()
    press(e, "1 2 3")
    assert e.command_line == "123"
    press(e, "backspace")
    assert e.command_line == "12"


def test_divide_by_zero_is_infinite_result_and_leaves_stack_intact() -> None:
    e = new_engine()
    press(e, "1 enter 0 /")
    assert e.error == "Infinite Result"
    assert e.depth == 2
    assert e.stack.peek(1) == 0
    assert e.stack.peek(2) == 1


def test_zero_divided_by_zero_is_undefined_result() -> None:
    e = new_engine()
    press(e, "0 enter 0 /")
    assert e.error == "Undefined Result"
    assert e.depth == 2


def test_exact_precision_round_trip() -> None:
    e = new_engine()
    press(e, "1 enter 3 / 3 *")
    assert e.depth == 1
    assert e.stack.peek(1) == 1.0  # exact, not merely close


def test_error_clears_on_next_keypress() -> None:
    e = new_engine()
    press(e, "1 enter 0 /")
    assert e.error == "Infinite Result"
    e.press("clear")  # any keypress, not just a fix, clears the message
    assert e.error is None


# -- operator/function implicit ENTER --------------------------------------


def test_operator_implicitly_commits_open_entry() -> None:
    e = new_engine()
    press(e, "3 enter")
    press(e, "4")
    assert e.command_line == "4"
    e.press("+")
    assert e.command_line is None
    assert e.depth == 1
    assert e.stack.peek(1) == 7


def test_function_implicitly_commits_open_entry() -> None:
    e = new_engine()
    press(e, "9")
    e.press("sqrt")
    assert e.command_line is None
    assert e.stack.peek(1) == 3


def test_operator_applies_directly_when_command_line_empty() -> None:
    e = new_engine()
    press(e, "3 enter 4 enter")
    assert e.command_line is None
    e.press("+")
    assert e.stack.peek(1) == 7


# -- CHS ----------------------------------------------------------------


def test_chs_mid_entry_toggles_mantissa_sign() -> None:
    e = new_engine()
    press(e, "5")
    e.press("chs")
    assert e.command_line == "-5"
    e.press("chs")
    assert e.command_line == "5"


def test_chs_on_empty_command_line_negates_level_1() -> None:
    e = new_engine()
    press(e, "5 enter")
    e.press("chs")
    assert e.stack.peek(1) == -5
    assert e.command_line is None


def test_chs_after_eex_toggles_exponent_sign() -> None:
    e = new_engine()
    press(e, "5 eex 3")
    assert e.command_line == "5E3"
    e.press("chs")
    assert e.command_line == "5E-3"
    e.press("chs")
    assert e.command_line == "5E3"


# -- EEX ------------------------------------------------------------------


def test_eex_entry_with_negative_exponent() -> None:
    e = new_engine()
    press(e, "5 eex 3 chs enter")
    assert e.depth == 1
    assert e.stack.peek(1) == 5e-3


def test_eex_opens_command_line_with_default_mantissa() -> None:
    e = new_engine()
    e.press("eex")
    assert e.command_line == "1E"
    press(e, "2 enter")
    assert e.stack.peek(1) == 1e2


# -- stack commands against known stacks -----------------------------------


def test_swap() -> None:
    e = new_engine()
    press(e, "1 enter 2 enter")
    e.press("swap")
    assert e.stack.peek(1) == 1
    assert e.stack.peek(2) == 2


def test_rot() -> None:
    e = new_engine()
    press(e, "1 enter 2 enter 3 enter")  # level1=3 level2=2 level3=1
    e.press("rot")
    assert e.stack.to_list() == [1, 3, 2]


def test_roll_takes_its_count_from_level_1() -> None:
    e = new_engine()
    press(e, "1 enter 2 enter 3 enter 4 enter")  # level1=4 level2=3 level3=2 level4=1
    press(e, "4 enter")  # push the roll count
    e.press("roll")
    assert e.stack.to_list() == [1, 4, 3, 2]


def test_drop_underflow_leaves_error_and_empty_stack() -> None:
    e = new_engine()
    e.press("drop")
    assert e.error == "Too Few Arguments"
    assert e.depth == 0


# -- trig / angle modes -----------------------------------------------------


def test_starts_in_the_declared_default_angle_mode() -> None:
    assert new_engine().angle_mode == DEFAULT_ANGLE_MODE


def test_sin_in_deg_mode() -> None:
    e = new_engine()
    e.set_angle_mode("DEG")
    press(e, "9 0")
    e.press("sin")
    assert e.stack.peek(1) == pytest.approx(1.0)


def test_sin_in_rad_mode() -> None:
    e = new_engine()
    e.set_angle_mode("RAD")
    e.stack.push(math.pi / 2)
    e.press("sin")
    assert e.stack.peek(1) == pytest.approx(1.0)


def test_asin_round_trips_with_sin_in_deg_mode() -> None:
    e = new_engine()
    e.set_angle_mode("DEG")
    press(e, "3 0")
    e.press("sin")
    e.press("asin")
    assert e.stack.peek(1) == pytest.approx(30.0)


# -- domain errors leave the stack untouched --------------------------------


@pytest.mark.parametrize(
    "entry, fn, expected_error",
    [
        ("1", "sqrt", "Invalid Input"),  # sqrt(-1) after CHS below
        ("0", "ln", "Invalid Input"),
        ("1", "ln", "Invalid Input"),  # ln(-1) after CHS below
        ("2", "asin", "Invalid Input"),
        ("2", "acos", "Invalid Input"),
    ],
)
def test_domain_errors_leave_stack_untouched(entry, fn, expected_error) -> None:
    e = new_engine()
    press(e, entry)
    if expected_error == "Invalid Input" and fn in ("sqrt", "ln") and entry == "1":
        e.press("chs")  # make it negative for sqrt(-1) / ln(-1)
    e.press(fn)
    assert e.error == expected_error
    assert e.depth == 1  # the operand is still there, untouched


def test_sqrt_negative_domain_error() -> None:
    e = new_engine()
    press(e, "4")
    e.press("chs")
    e.press("sqrt")
    assert e.error == "Invalid Input"
    assert e.depth == 1
    assert e.stack.peek(1) == -4


# -- CP4 function set --------------------------------------------------------


def test_sq() -> None:
    e = new_engine()
    press(e, "5")
    e.press("sq")
    assert e.stack.peek(1) == 25


def test_inv() -> None:
    e = new_engine()
    press(e, "4")
    e.press("inv")
    assert e.stack.peek(1) == 0.25


def test_ln_exp_round_trip() -> None:
    e = new_engine()
    press(e, "2")
    e.press("ln")
    e.press("exp")
    assert e.stack.peek(1) == pytest.approx(2.0)


def test_log_alog_round_trip() -> None:
    e = new_engine()
    press(e, "3")
    e.press("log")
    e.press("alog")
    assert e.stack.peek(1) == pytest.approx(3.0)


def test_pow() -> None:
    e = new_engine()
    press(e, "2 enter 1 0")  # 2, then 10
    e.press("pow")
    assert e.stack.peek(1) == 1024


def test_mod() -> None:
    e = new_engine()
    press(e, "7 enter 3")
    e.press("mod")
    assert e.stack.peek(1) == 1


def test_percent_consumes_both_operands() -> None:
    # HP's % is an ordinary binary function: level 2 times level 1 percent,
    # both consumed, one result. 200 ENTER 10 % is 20.
    e = new_engine()
    press(e, "2 0 0 enter 1 0 percent")
    assert e.depth == 1
    assert e.stack.peek(1) == 20


def test_xroot_takes_the_nth_root() -> None:
    # y√x reads left to right off the stack: the index is level 2 and the
    # radicand is level 1, so the cube root of 27 is "3 ENTER 27".
    e = new_engine()
    press(e, "3 enter 2 7 xroot")
    assert e.stack.peek(1) == pytest.approx(3.0)

    # Odd roots of a negative are real; a complex result would be a domain error.
    e = new_engine()
    press(e, "3 enter 8 chs xroot")
    assert e.stack.peek(1) == pytest.approx(-2.0)


def test_xroot_reads_the_stack_the_way_its_legend_reads() -> None:
    """The operand order is the whole point of the `y√x` relabel.

    Under the old `ⁿ√y` the operands were the other way round, so a silent
    swap here would still look plausible: both orders give 3 for the cube
    root of 27 only because 27 and 3 are not interchangeable anywhere else.
    These two pin the direction.
    """
    e = new_engine()
    press(e, "2 enter 6 4 xroot")      # index 2, radicand 64
    assert e.stack.peek(1) == pytest.approx(8.0)

    e = new_engine()
    press(e, "6 4 enter 2 xroot")      # index 64, radicand 2 - the other way
    assert e.stack.peek(1) == pytest.approx(2.0 ** (1.0 / 64.0))


def test_clear_entry_spares_the_stack() -> None:
    e = new_engine()
    press(e, "8 enter 1 2 3 clear_entry")
    assert e.depth == 1
    assert e.stack.peek(1) == 8
    assert e.command_line is None


def test_clear_empties_the_stack() -> None:
    e = new_engine()
    press(e, "8 enter 9 clear")
    assert e.depth == 0

def test_pi_pushes_constant() -> None:
    e = new_engine()
    e.press("pi")
    assert e.stack.peek(1) == pytest.approx(math.pi)


def test_abs_and_neg() -> None:
    e = new_engine()
    press(e, "5")
    e.press("chs")
    e.press("abs")
    assert e.stack.peek(1) == 5
    e.press("neg")
    assert e.stack.peek(1) == -5


# -- display formatting -------------------------------------------------


def test_stack_lines_honor_number_format() -> None:
    e = new_engine()
    e.set_number_format(NumberFormat(FIX, 2))
    press(e, "1 enter 3")
    e.press("/")
    assert e.stack_lines() == ["0.33"]
    # full precision still lives on the stack underneath the display format.
    assert e.stack.peek(1) == pytest.approx(1 / 3)


# -- undo -----------------------------------------------------------------


def test_undo_restores_stack_after_a_command() -> None:
    e = new_engine()
    press(e, "3 enter 4 +")
    assert e.stack.to_list() == [7]
    e.press("undo")
    # UNDO reverts the whole last command -- here, "commit the pending '4'
    # entry, then add" -- back to the stack as it stood before that command,
    # not to some intermediate state where 4 had already been pushed.
    assert e.stack.to_list() == [3]


# -- overflow and malformed input never escape the engine --------------------


@pytest.mark.parametrize(
    "sequence, command",
    [
        ("1 0 0 0 enter", "exp"),      # math.exp raises OverflowError
        ("1 eex 2 0 0 enter", "sq"),   # returns inf rather than raising
        ("4 0 0 enter", "alog"),
        ("1 eex 3 0 0 enter 1 eex 3 0 0 enter", "*"),
        ("1 0 enter 4 0 0 enter", "pow"),
    ],
)
def test_overflow_becomes_an_error_not_a_crash(sequence, command) -> None:
    e = new_engine()
    press(e, sequence)
    before = e.stack.to_list()
    e.press(command)
    assert e.error == "Infinite Result"
    assert e.stack.to_list() == before
    # The display must still render: an infinite level would break formatting
    # for every level, not just its own.
    assert e.stack_lines() == [format_number(v) for v in before]


def test_an_entry_that_overflows_is_rejected_whole() -> None:
    e = new_engine()
    press(e, "7 enter")
    press(e, "1 eex 9 9 9")
    e.press("enter")
    assert e.error == "Infinite Result"
    assert e.stack.to_list() == [7.0]  # nothing half-pushed
    assert e.stack_lines() == ["7"]


def test_a_negative_base_with_a_fractional_power_is_a_domain_error() -> None:
    e = new_engine()
    press(e, "8 chs enter 0 . 5 pow")
    assert e.error == "Invalid Input"
    assert e.stack.to_list() == [0.5, -8.0]


def test_decimal_point_is_ignored_inside_an_exponent() -> None:
    e = new_engine()
    press(e, "1 eex 3 .")
    assert e.command_line == "1E3"  # the key does nothing, as on the 50g
    e.press("enter")
    assert e.stack_lines() == ["1000"]


def test_an_unbound_command_is_a_no_op() -> None:
    e = new_engine()
    press(e, "4 enter")
    e.press("bogus")  # must not raise
    assert e.stack.to_list() == [4.0]
    assert e.error is None


def test_undo_takes_back_the_entry_an_erroring_command_committed() -> None:
    e = new_engine()
    press(e, "5 +")  # commits 5, then + fails: nothing to add it to
    assert e.error == "Too Few Arguments"
    assert e.stack.to_list() == [5.0]  # the commit stands
    e.press("undo")
    assert e.stack.to_list() == []  # and UNDO takes it back
