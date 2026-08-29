"""Property-based validation of the calculation core.

The example-based tests check answers the author thought to ask for. These check
invariants over inputs nobody chose, which is where the awkward cases live.

The most valuable test here is `TestCrossEngine`: the RPN and algebraic engines
are two independent implementations of the same arithmetic, so making them agree
- and agree with Python's own evaluation - checks all three against each other.
"""

from __future__ import annotations

import math
import statistics
from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

import oracle
from rpncalc.alg_engine import AlgEngine
from rpncalc.numeric import ENG, FIX, SCI, STD, NumberFormat, format_number, localize_number, parse_number
from rpncalc.rpn_engine import CalcError, RpnEngine
from rpncalc.stack import RpnStack, StackError

# Magnitudes a calculator actually sees, kept clear of the overflow edge so a
# property failure means a logic error rather than a saturated exponent.
REAL = st.floats(
    min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False
)
SMALL = st.floats(
    min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False
)
NONZERO = REAL.filter(lambda v: abs(v) > 1e-9)

ALL_COMMANDS = [
    "+", "-", "*", "/", "pow", "mod", "percent", "xroot",
    "sqrt", "sq", "inv", "ln", "exp", "log", "alog",
    "sin", "cos", "tan", "asin", "acos", "atan", "abs", "neg", "pi",
    "drop", "swap", "dup", "over", "rot", "unrot", "roll", "rolld",
    "pick", "depth", "undo", "enter", "spc", "backspace", "chs", "eex",
    "clear", "clear_entry", "up", "down", "left", "right",
]


def engine_with(values: list[float]) -> RpnEngine:
    engine = RpnEngine()
    for value in values:
        engine.stack.push(value)
    return engine


class TestStackAlgebra:
    @given(st.lists(REAL, min_size=1, max_size=12))
    def test_push_then_pop_is_identity(self, values):
        stack = RpnStack()
        for value in values:
            stack.push(value)
        for value in reversed(values):
            assert stack.pop() == value
        assert stack.depth == 0

    @given(st.lists(REAL, min_size=2, max_size=12))
    def test_swap_is_its_own_inverse(self, values):
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        stack.swap()
        stack.swap()
        assert stack.to_list() == before

    @given(st.lists(REAL, min_size=3, max_size=12))
    def test_rot_three_times_is_identity(self, values):
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        for _ in range(3):
            stack.rot()
        assert stack.to_list() == before

    @given(st.lists(REAL, min_size=3, max_size=12))
    def test_rot_and_unrot_are_inverses(self, values):
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        stack.rot()
        stack.unrot()
        assert stack.to_list() == before

    @given(st.lists(REAL, min_size=1, max_size=12), st.integers(min_value=1, max_value=12))
    def test_roll_and_rolld_are_inverses(self, values, n):
        assume(n <= len(values))
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        stack.roll(n)
        stack.rolld(n)
        assert stack.to_list() == before

    @given(st.lists(REAL, min_size=1, max_size=12))
    def test_dup_adds_a_copy_of_level_one(self, values):
        stack = RpnStack()
        for value in values:
            stack.push(value)
        stack.dup()
        assert stack.depth == len(values) + 1
        assert stack.peek(1) == stack.peek(2) == values[-1]

    @given(st.lists(REAL, min_size=1, max_size=10), st.integers(min_value=1, max_value=10))
    def test_pick_copies_without_disturbing_anything(self, values, n):
        assume(n <= len(values))
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        stack.pick(n)
        assert stack.to_list()[1:] == before
        assert stack.peek(1) == before[n - 1]

    @given(st.lists(REAL, max_size=6), st.integers(min_value=1, max_value=20))
    def test_underflow_never_mutates(self, values, n):
        assume(n > len(values))
        stack = RpnStack()
        for value in values:
            stack.push(value)
        before = stack.to_list()
        for operation in (
            lambda: stack.peek(n), lambda: stack.dropn(n),
            lambda: stack.roll(n), lambda: stack.rolld(n), lambda: stack.pick(n),
        ):
            with pytest.raises(StackError):
                operation()
            assert stack.to_list() == before


class TestEngineNeverBreaks:
    """No sequence of keys may raise, and no non-finite value may reach the
    stack - one infinity there makes every level unformattable, not just its
    own."""

    @given(
        st.lists(st.sampled_from(ALL_COMMANDS), min_size=1, max_size=40),
        st.lists(REAL, max_size=5),
    )
    @settings(max_examples=400, deadline=None)
    def test_random_key_sequences_are_survivable(self, commands, seed):
        engine = engine_with(seed)
        for command in commands:
            try:
                engine.press(command)
            except (StackError, CalcError) as exc:  # pragma: no cover
                pytest.fail(f"{command} raised {exc!r} instead of reporting it")
            for value in engine.stack.to_list():
                assert math.isfinite(value)
            engine.stack_lines()  # formatting must always be possible

    @given(st.lists(st.sampled_from("0123456789.") , min_size=1, max_size=18))
    @settings(max_examples=300, deadline=None)
    def test_arbitrary_typing_always_commits_to_a_number(self, keys):
        engine = RpnEngine()
        for key in keys:
            engine.press(key)
        engine.press("enter")
        assert engine.error is None
        assert engine.depth <= 1
        if engine.depth:
            assert math.isfinite(engine.stack.peek(1))


class TestArithmeticLaws:
    @given(SMALL, SMALL)
    def test_addition_commutes(self, a, b):
        assert engine_apply("+", a, b) == engine_apply("+", b, a)

    @given(SMALL, SMALL)
    def test_multiplication_commutes(self, a, b):
        assert engine_apply("*", a, b) == engine_apply("*", b, a)

    @given(REAL)
    def test_adding_zero_changes_nothing(self, x):
        assert engine_apply("+", x, 0.0) == x

    @given(REAL)
    def test_multiplying_by_one_changes_nothing(self, x):
        assert engine_apply("*", x, 1.0) == x

    @given(REAL)
    def test_negate_is_an_involution(self, x):
        engine = engine_with([x])
        engine.press("neg")
        engine.press("neg")
        assert engine.stack.peek(1) == x

    @given(REAL)
    def test_absolute_value_is_idempotent(self, x):
        once = engine_apply("abs", x)
        assert engine_apply("abs", once) == once
        assert once >= 0

    @given(NONZERO)
    def test_reciprocal_twice_returns_the_value(self, x):
        engine = engine_with([x])
        engine.press("inv")
        engine.press("inv")
        assert engine.stack.peek(1) == pytest.approx(x, rel=1e-12)

    @given(REAL)
    def test_square_root_of_a_square_is_the_magnitude(self, x):
        assume(abs(x) < 1e150)
        engine = engine_with([x])
        engine.press("sq")
        engine.press("sqrt")
        assert engine.stack.peek(1) == pytest.approx(abs(x), rel=1e-12)

    @given(SMALL, SMALL)
    def test_subtraction_is_addition_of_the_negation(self, a, b):
        assert engine_apply("-", a, b) == engine_apply("+", a, -b)


def engine_apply(command: str, *operands: float) -> float:
    engine = engine_with(list(operands))
    engine.press(command)
    assert engine.error is None, f"{command}{operands} -> {engine.error}"
    return engine.stack.peek(1)


class TestFormatting:
    @given(REAL)
    def test_standard_format_round_trips(self, x):
        """STD keeps 15 significant digits, so a value must survive being
        displayed and read back to within that."""
        text = format_number(x)
        back = parse_number(text)
        assert back is not None
        if x == 0:
            assert back == 0
        else:
            assert oracle.relative_error(back, Decimal(x)) <= Decimal("1e-14")

    @given(REAL)
    def test_a_formatted_number_never_shows_negative_zero(self, x):
        for fmt in (NumberFormat(STD), NumberFormat(FIX, 2), NumberFormat(SCI, 3),
                    NumberFormat(ENG, 3)):
            text = format_number(x, fmt)
            assert not text.startswith("-0E")
            assert text not in ("-0", "-0.00", "-0.000")

    @given(REAL, st.integers(min_value=0, max_value=11))
    def test_every_format_produces_something_parseable(self, x, digits):
        for mode in (FIX, SCI, ENG):
            text = format_number(x, NumberFormat(mode, digits))
            assert parse_number(text) is not None, f"{mode} {digits} of {x!r}: {text!r}"

    @given(REAL)
    def test_localized_display_parses_back(self, x):
        text = format_number(x)
        expected = parse_number(text)
        for decimal, thousands in ((".", False), (".", True), (",", False), (",", True)):
            shown = localize_number(text, decimal=decimal, thousands=thousands)
            assert parse_number(shown, decimal=decimal, thousands=thousands) == expected

    @given(REAL, st.integers(min_value=0, max_value=11))
    def test_scientific_and_engineering_agree_on_magnitude(self, x, digits):
        assume(x != 0)
        sci = parse_number(format_number(x, NumberFormat(SCI, digits)))
        eng = parse_number(format_number(x, NumberFormat(ENG, digits)))
        assert sci is not None and eng is not None
        # Both round to the same number of significant digits, so they must
        # describe the same quantity even though the exponents differ.
        assert eng == pytest.approx(sci, rel=10.0 ** -(digits - 1) if digits else 1.0)

    @given(REAL)
    def test_engineering_exponents_are_multiples_of_three(self, x):
        text = format_number(x, NumberFormat(ENG, 3))
        exponent = int(text.split("E")[1])
        assert exponent % 3 == 0


# -- cross-engine differential ------------------------------------------------

OPERATORS = ["+", "-", "*", "/"]
PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


def to_postfix(tokens: list[str]) -> list[str]:
    """Shunting-yard, so the same expression can be fed to both engines."""
    output: list[str] = []
    operators: list[str] = []
    for token in tokens:
        if token in PRECEDENCE:
            while operators and PRECEDENCE[operators[-1]] >= PRECEDENCE[token]:
                output.append(operators.pop())
            operators.append(token)
        else:
            output.append(token)
    while operators:
        output.append(operators.pop())
    return output


NUMBER_TEXT = st.from_regex(r"\A(?:[1-9][0-9]{0,3}|0)(?:\.[0-9]{1,3})?\Z", fullmatch=True)


@st.composite
def expressions(draw):
    """An infix expression as alternating number/operator tokens."""
    count = draw(st.integers(min_value=1, max_value=5))
    tokens = [draw(NUMBER_TEXT)]
    for _ in range(count):
        tokens.append(draw(st.sampled_from(OPERATORS)))
        tokens.append(draw(NUMBER_TEXT))
    return tokens


class TestCrossEngine:
    """The two engines share `numeric.py` and nothing else. Agreement between
    them, and with Python's own evaluation, is three independent paths landing
    on the same answer."""

    @given(expressions())
    @settings(max_examples=500, deadline=None)
    def test_rpn_and_algebraic_agree_with_python(self, tokens):
        expression = "".join(tokens)
        try:
            reference = eval(expression)  # noqa: S307 - digits and operators only
        except ZeroDivisionError:
            assume(False)
            return
        assume(math.isfinite(reference))

        algebraic = AlgEngine()
        for token in tokens:
            if token in PRECEDENCE:
                algebraic.press(token)
            else:
                for character in token:
                    algebraic.press(character)
        algebraic.press("=")
        assume(not algebraic._errored)

        rpn = RpnEngine()
        for token in to_postfix(tokens):
            if token in PRECEDENCE:
                rpn.press(token)
            else:
                for character in token:
                    rpn.press(character)
                rpn.press("enter")
        assume(rpn.error is None)

        assert rpn.depth == 1
        assert rpn.stack.peek(1) == pytest.approx(reference, rel=1e-12, abs=1e-12)
        assert float(algebraic.display) == pytest.approx(reference, rel=1e-12, abs=1e-12)

    @given(expressions())
    @settings(max_examples=300, deadline=None)
    def test_operator_precedence_is_not_left_to_right(self, tokens):
        """The algebraic engine must bind * and / tighter than + and -, which is
        the single thing an RPN user does not have to think about."""
        expression = "".join(tokens)
        try:
            reference = eval(expression)  # noqa: S307
        except ZeroDivisionError:
            assume(False)
            return
        assume(math.isfinite(reference))

        algebraic = AlgEngine()
        for token in tokens:
            if token in PRECEDENCE:
                algebraic.press(token)
            else:
                for character in token:
                    algebraic.press(character)
        algebraic.press("=")
        assume(not algebraic._errored)
        assert float(algebraic.display) == pytest.approx(reference, rel=1e-12, abs=1e-12)


class TestEntryRoundTrip:
    @given(NUMBER_TEXT)
    def test_typing_a_number_puts_that_number_on_the_stack(self, text):
        engine = RpnEngine()
        for character in text:
            engine.press(character)
        engine.press("enter")
        assert engine.stack.peek(1) == float(text)

    @given(NUMBER_TEXT)
    def test_change_sign_while_typing_negates(self, text):
        assume(float(text) != 0)
        engine = RpnEngine()
        for character in text:
            engine.press(character)
        engine.press("chs")
        engine.press("enter")
        assert engine.stack.peek(1) == -float(text)

    @given(st.integers(min_value=1, max_value=999), st.integers(min_value=-99, max_value=99))
    def test_exponent_entry_matches_the_literal(self, mantissa, exponent):
        engine = RpnEngine()
        for character in str(mantissa):
            engine.press(character)
        engine.press("eex")
        if exponent < 0:
            for character in str(abs(exponent)):
                engine.press(character)
            engine.press("chs")
        else:
            for character in str(exponent):
                engine.press(character)
        engine.press("enter")
        assert engine.error is None
        assert engine.stack.peek(1) == float(f"{mantissa}e{exponent}")


class TestStatisticsAgainstTheStandardLibrary:
    """The Σ readbacks against `statistics`, an independent implementation.

    Same idea as `TestCrossEngine`: checking our mean against our own sum
    would only prove the code calls the function it says it calls. `statistics`
    shares no code with the engine, so agreement is two paths landing together.
    """

    @staticmethod
    def accumulate(values):
        engine = RpnEngine()
        for value in values:
            engine.stack.clear()
            engine.stack.push(float(value))
            engine.press("sum_plus")
        engine.stack.clear()
        return engine

    @given(st.lists(REAL, min_size=1, max_size=30))
    @settings(max_examples=150)
    def test_median_matches_exactly(self, values):
        engine = self.accumulate(values)
        engine.press("median")
        assert engine.stack.peek(1) == statistics.median(values)

    @given(st.lists(REAL, min_size=1, max_size=30))
    @settings(max_examples=150)
    def test_mean_and_sum_agree_with_the_library(self, values):
        engine = self.accumulate(values)
        engine.press("sigma_sum")
        assert engine.stack.peek(1) == pytest.approx(math.fsum(values), rel=1e-12)
        engine.stack.clear()
        engine.press("mean")
        assert engine.stack.peek(1) == pytest.approx(
            statistics.fmean(values), rel=1e-12, abs=1e-9
        )

    @given(st.lists(REAL, min_size=2, max_size=30))
    @settings(max_examples=300)
    def test_stddev_matches_the_sample_form(self, values):
        """`statistics.stdev` works in exact rationals, so this is a real
        oracle rather than the same float arithmetic written twice."""
        expected = statistics.stdev(values)
        engine = self.accumulate(values)
        engine.press("stddev")
        assert engine.stack.peek(1) == pytest.approx(expected, rel=1e-12, abs=1e-12)

    def test_stddev_holds_up_on_a_tight_cluster_far_from_zero(self):
        """Deterministic pin for the case a property run found once.

        The mean of these is not representable, and plain two-pass carries the
        leftover bias into the ninth digit. Kept as an example test because a
        branch - or a bug - reached only by chance is not covered.
        """
        values = [733007751635.0, 733007751635.0, 733007751634.0]
        engine = self.accumulate(values)
        engine.press("stddev")
        assert engine.stack.peek(1) == statistics.stdev(values)

    @pytest.mark.parametrize("value", [1e308, 1.5e308])
    def test_huge_repeated_values_keep_mean_and_stddev_finite(self, value):
        """Scaling avoids overflowing the sum of an otherwise finite mean."""
        mean = self.accumulate([value, value])
        mean.press("mean")
        assert mean.error is None
        assert mean.stack.peek(1) == value

        stddev = self.accumulate([value, value])
        stddev.press("stddev")
        assert stddev.error is None
        assert stddev.stack.peek(1) == 0.0

    @given(st.lists(REAL, min_size=2, max_size=20))
    @settings(max_examples=100)
    def test_a_shifted_sample_moves_its_centre_but_not_its_spread(self, values):
        """Spread is translation-invariant; the naive Σx² form is not."""
        offset = 1e6
        plain = self.accumulate(values)
        plain.press("stddev")
        shifted = self.accumulate([v + offset for v in values])
        shifted.press("stddev")
        assert shifted.stack.peek(1) == pytest.approx(
            plain.stack.peek(1), rel=1e-6, abs=1e-6
        )

    def test_the_two_pass_form_survives_what_the_shortcut_cannot(self):
        """Deterministic, because this is the reason the design is what it is.

        `Σx² - n·x̄²` subtracts two enormous nearly-equal numbers here; in
        float64 it returns exactly 0.0 for a sample whose spread is exactly 1.
        """
        values = [1e9, 1e9 + 1, 1e9 + 2]
        total = sum(values)
        squares = sum(value * value for value in values)
        shortcut = ((squares - total * total / 3) / 2) ** 0.5
        assert shortcut == 0.0  # the form we deliberately do not use

        engine = self.accumulate(values)
        engine.press("stddev")
        assert engine.stack.peek(1) == pytest.approx(1.0, rel=1e-12)
