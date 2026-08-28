"""Differential validation of the calculation core against `tests/oracle.py`.

Every result the engine produces is checked against the same quantity computed
in 50-digit decimal arithmetic. The engine works in binary floats via `math`;
the oracle works in decimal, and computes the trigonometric functions from
Taylor series rather than calling a library. Agreement between the two is
evidence; agreement between `math` and `math` would not be.

Tolerance is a relative error of 1e-14. A double holds about 15.95 decimal
digits, so a handful of ulp is the floor - anything wider means the engine is
losing precision somewhere it should not.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

import oracle
from rpncalc.rpn_engine import CalcError, RpnEngine, StackError

TOLERANCE = oracle.DOUBLE_TOLERANCE


def apply(command: str, *operands: float, angle: str = "RAD") -> float:
    """Run one engine command over `operands` and return level 1."""
    engine = RpnEngine()
    engine.set_angle_mode(angle)
    for value in operands:
        engine.stack.push(value)
    engine.press(command)
    assert engine.error is None, f"{command}{operands} -> {engine.error}"
    return engine.stack.peek(1)


def check(command: str, expected: Decimal, *operands: float, angle: str = "RAD") -> None:
    actual = apply(command, *operands, angle=angle)
    error = oracle.relative_error(actual, expected)
    assert error <= TOLERANCE, (
        f"{command}{operands}: got {actual!r}, reference {expected}, "
        f"relative error {error:.3e}"
    )


# A spread that exercises the ordinary, the tiny, the huge and the negative.
OPERANDS = [
    0.0, 1.0, -1.0, 2.0, 0.5, -0.5, 3.0, 7.0, 10.0, -10.0,
    0.1, 0.2, 0.3, 1e-8, -1e-8, 1234.5678, -9876.5432,
    1e10, 1e-10, 123456789.123456, 2.718281828459045, 3.141592653589793,
    0.9999999999, 1.0000000001, 1e15, 1e-15,
]

POSITIVE = [v for v in OPERANDS if v > 0]
NONZERO = [v for v in OPERANDS if v != 0]


class TestArithmetic:
    @pytest.mark.parametrize("a", OPERANDS)
    @pytest.mark.parametrize("b", [1.0, -1.0, 0.5, 3.0, 0.1, 1e8, -1234.5678])
    def test_add(self, a, b):
        check("+", oracle.add(a, b), a, b)

    @pytest.mark.parametrize("a", OPERANDS)
    @pytest.mark.parametrize("b", [1.0, -1.0, 0.5, 3.0, 0.1, 1e8, -1234.5678])
    def test_subtract(self, a, b):
        check("-", oracle.sub(a, b), a, b)

    @pytest.mark.parametrize("a", OPERANDS)
    @pytest.mark.parametrize("b", [1.0, -1.0, 0.5, 3.0, 0.1, -1234.5678])
    def test_multiply(self, a, b):
        check("*", oracle.mul(a, b), a, b)

    @pytest.mark.parametrize("a", OPERANDS)
    @pytest.mark.parametrize("b", [1.0, -1.0, 0.5, 3.0, 0.1, -1234.5678])
    def test_divide(self, a, b):
        check("/", oracle.div(a, b), a, b)

    @pytest.mark.parametrize("base", [200.0, 1.0, 0.5, -40.0, 1e6])
    @pytest.mark.parametrize("pct", [10.0, 0.5, 100.0, 250.0, -25.0])
    def test_percent(self, base, pct):
        check("percent", oracle.percent(base, pct), base, pct)

    def test_operand_order_is_level_two_then_level_one(self):
        # 10 ENTER 3 - must be 7, not -7. The classic RPN mistake.
        assert apply("-", 10.0, 3.0) == 7.0
        assert apply("/", 10.0, 4.0) == 2.5
        assert apply("pow", 2.0, 10.0) == 1024.0


class TestRoots:
    @pytest.mark.parametrize("x", POSITIVE + [0.0])
    def test_sqrt(self, x):
        check("sqrt", oracle.sqrt(x), x)

    @pytest.mark.parametrize("x", OPERANDS)
    def test_square(self, x):
        if abs(x) > 1e150:
            pytest.skip("squares out of double range")
        check("sq", oracle.mul(x, x), x)

    @pytest.mark.parametrize("x", NONZERO)
    def test_reciprocal(self, x):
        check("inv", oracle.div(1.0, x), x)

    @pytest.mark.parametrize("x", [8.0, 27.0, 1000.0, 2.0, 0.5])
    @pytest.mark.parametrize("degree", [2.0, 3.0, 5.0])
    def test_xroot(self, x, degree):
        # y√x: the index goes in level 2, the radicand in level 1.
        check("xroot", oracle.power(x, 1.0 / degree), degree, x)

    def test_sqrt_and_square_round_trip(self):
        for x in POSITIVE:
            engine = RpnEngine()
            engine.stack.push(x)
            engine.press("sqrt")
            engine.press("sq")
            assert oracle.relative_error(engine.stack.peek(1), Decimal(repr(x))) <= TOLERANCE


class TestLogarithms:
    @pytest.mark.parametrize("x", POSITIVE)
    def test_ln(self, x):
        check("ln", oracle.ln(x), x)

    @pytest.mark.parametrize("x", POSITIVE)
    def test_log10(self, x):
        check("log", oracle.log10(x), x)

    @pytest.mark.parametrize("x", [0.0, 1.0, -1.0, 2.0, 0.5, -0.5, 10.0, 3.0, -20.0, 100.0])
    def test_exp(self, x):
        check("exp", oracle.exp(x), x)

    @pytest.mark.parametrize("x", [0.0, 1.0, -1.0, 2.0, 0.5, -0.5, 5.0, -8.0, 100.0])
    def test_alog(self, x):
        check("alog", oracle.alog(x), x)

    @pytest.mark.parametrize("x", POSITIVE)
    def test_ln_and_exp_round_trip(self, x):
        engine = RpnEngine()
        engine.stack.push(x)
        engine.press("ln")
        engine.press("exp")
        assert oracle.relative_error(engine.stack.peek(1), Decimal(repr(x))) <= Decimal("1e-13")

    @pytest.mark.parametrize("x", [1.0, 2.0, 10.0, 0.5, 1234.5678])
    def test_log_and_alog_round_trip(self, x):
        engine = RpnEngine()
        engine.stack.push(x)
        engine.press("log")
        engine.press("alog")
        assert oracle.relative_error(engine.stack.peek(1), Decimal(repr(x))) <= Decimal("1e-13")


class TestPower:
    @pytest.mark.parametrize(
        "base, exponent",
        [
            (2.0, 10.0), (2.0, 0.5), (10.0, 3.0), (1.5, 2.5), (0.5, -2.0),
            (7.0, 0.0), (1.0, 12345.0), (-2.0, 3.0), (-2.0, 4.0), (-8.0, 2.0),
            (123.456, 1.5), (0.1, 3.0), (1e5, 2.0),
        ],
    )
    def test_pow(self, base, exponent):
        check("pow", oracle.power(base, exponent), base, exponent)

    def test_negative_base_with_integer_exponent_keeps_its_sign(self):
        assert apply("pow", -2.0, 3.0) == -8.0
        assert apply("pow", -2.0, 2.0) == 4.0

    def test_anything_to_the_zero_is_one(self):
        for base in NONZERO:
            assert apply("pow", base, 0.0) == 1.0


class TestTrigonometryRadians:
    ANGLES = [
        0.0, 0.1, 0.5, 1.0, -1.0, 1.5, 2.0, 3.0, -3.0, 6.0, 10.0, -10.0,
        100.0, 1000.0, 0.7853981633974483, 1.5707963267948966,
        3.141592653589793, 6.283185307179586,
    ]

    @pytest.mark.parametrize("x", ANGLES)
    def test_sin(self, x):
        actual = apply("sin", x)
        expected = oracle.sin(x)
        # Near a zero of the function, relative error is meaningless: compare
        # absolutely instead, which is the honest measure there.
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(repr(actual)) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize("x", ANGLES)
    def test_cos(self, x):
        actual = apply("cos", x)
        expected = oracle.cos(x)
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(repr(actual)) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize("x", [0.0, 0.1, 0.5, 1.0, -1.0, 2.0, 3.0, 10.0, 0.7853981633974483])
    def test_tan(self, x):
        actual = apply("tan", x)
        expected = oracle.tan(x)
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(repr(actual)) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    def test_pythagorean_identity(self):
        for x in self.ANGLES:
            s = apply("sin", x)
            c = apply("cos", x)
            assert abs(s * s + c * c - 1.0) < 1e-14


class TestTrigonometryDegrees:
    ANGLES = [0.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 270.0, 360.0,
              -45.0, -90.0, 720.0, 1234.5]

    @pytest.mark.parametrize("x", ANGLES)
    def test_sin_in_degrees(self, x):
        actual = apply("sin", x, angle="DEG")
        expected = oracle._sin_series(oracle._reduce(oracle.radians(x)))
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(repr(actual)) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize("x", ANGLES)
    def test_cos_in_degrees(self, x):
        actual = apply("cos", x, angle="DEG")
        expected = oracle._cos_series(oracle._reduce(oracle.radians(x)))
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(repr(actual)) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize(
        "degrees, expected",
        [(0.0, 0.0), (30.0, 0.5), (90.0, 1.0), (150.0, 0.5), (270.0, -1.0)],
    )
    def test_landmark_sines(self, degrees, expected):
        assert apply("sin", degrees, angle="DEG") == pytest.approx(expected, abs=1e-15)

    def test_tan_of_forty_five_degrees_is_one(self):
        assert apply("tan", 45.0, angle="DEG") == pytest.approx(1.0, abs=1e-15)

    def test_angle_mode_only_applies_at_the_boundary(self):
        # The same number means different things in the two modes, and nothing
        # else about the stack changes.
        assert apply("sin", 90.0, angle="DEG") == pytest.approx(1.0, abs=1e-15)
        assert apply("sin", 90.0, angle="RAD") == pytest.approx(math.sin(90.0), abs=1e-15)


class TestInverseTrigonometry:
    """Checked against the oracle's own atan/asin/acos, which are built from a
    reduced Taylor series and exact identities - not from `math`."""

    VALUES = [0.0, 0.1, 0.5, -0.5, 0.9, 0.99, 1.0, -1.0, 0.7071067811865476,
              1e-8, -1e-8, 0.30901699437494745]

    @pytest.mark.parametrize("x", VALUES)
    def test_asin(self, x):
        actual = apply("asin", x)
        expected = oracle.asin(x)
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(actual) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize("x", VALUES)
    def test_acos(self, x):
        actual = apply("acos", x)
        expected = oracle.acos(x)
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(actual) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize(
        "x",
        [0.0, 0.05, 0.5, -0.5, 0.9, 1.0, -1.0, 2.0, 10.0, -10.0,
         1e6, -1e6, 1e-6, 1e12, 1e-12],
    )
    def test_atan(self, x):
        actual = apply("atan", x)
        expected = oracle.atan(x)
        if abs(expected) < Decimal("1e-8"):
            assert abs(Decimal(actual) - expected) <= Decimal("1e-15")
        else:
            assert oracle.relative_error(actual, expected) <= TOLERANCE

    @pytest.mark.parametrize("x", [0.0, 0.1, 0.5, -0.5, 0.9, 1.0, -1.0])
    def test_asin_round_trips_through_sin(self, x):
        assert abs(apply("sin", apply("asin", x)) - x) < 1e-14

    @pytest.mark.parametrize("x", [0.0, 0.5, 1.0, -1.0, 10.0, 0.001])
    def test_atan_round_trips_through_tan(self, x):
        # Only where tan is well conditioned. Beyond about |x| = 100 the angle
        # is so close to pi/2 that tan amplifies the last bits enormously, and a
        # round-trip there measures the conditioning of tan, not the engine.
        assert abs(apply("tan", apply("atan", x)) - x) <= abs(x) * 1e-13 + 1e-14

    def test_asin_and_acos_are_complementary(self):
        for x in self.VALUES:
            total = apply("asin", x) + apply("acos", x)
            assert abs(total - float(oracle.PI / 2)) < 1e-14

    def test_landmarks(self):
        assert apply("asin", 1.0) == pytest.approx(float(oracle.PI / 2), abs=1e-15)
        assert apply("acos", 0.0) == pytest.approx(float(oracle.PI / 2), abs=1e-15)
        assert apply("atan", 1.0) == pytest.approx(float(oracle.PI / 4), abs=1e-15)
        assert apply("asin", 0.0) == 0.0
        assert apply("acos", 1.0) == 0.0

    def test_landmarks_in_degrees(self):
        assert apply("asin", 1.0, angle="DEG") == pytest.approx(90.0, abs=1e-13)
        assert apply("acos", 0.0, angle="DEG") == pytest.approx(90.0, abs=1e-13)
        assert apply("atan", 1.0, angle="DEG") == pytest.approx(45.0, abs=1e-13)


class TestChainedPrecision:
    """Results move between operations as full doubles, so a chain must not
    accumulate error beyond what the arithmetic itself costs."""

    def test_divide_then_multiply_returns_exactly(self):
        for divisor in (3.0, 7.0, 11.0, 13.0, 97.0):
            engine = RpnEngine()
            engine.stack.push(1.0)
            engine.stack.push(divisor)
            engine.press("/")
            engine.stack.push(divisor)
            engine.press("*")
            assert engine.stack.peek(1) == 1.0

    def test_a_long_chain_tracks_the_reference(self):
        # ((((2 + 3) * 7 - 4) / 6) ^ 2) then sqrt, against the same in decimal.
        engine = RpnEngine()
        for value, command in [(2.0, None), (3.0, "+"), (7.0, "*"), (4.0, "-"),
                               (6.0, "/"), (2.0, "pow")]:
            engine.stack.push(value)
            if command:
                engine.press(command)
        engine.press("sqrt")
        expected = ((Decimal(2) + 3) * 7 - 4) / 6
        assert oracle.relative_error(engine.stack.peek(1), expected) <= TOLERANCE

    def test_repeated_addition_drifts_only_as_float_addition_does(self):
        engine = RpnEngine()
        engine.stack.push(0.0)
        for _ in range(100):
            engine.stack.push(0.01)
            engine.press("+")

        # Not `sum()`: since 3.12 it compensates for rounding and is *more*
        # accurate than adding left to right, so it is the wrong reference for
        # a calculator that adds one operand at a time.
        naive = 0.0
        for _ in range(100):
            naive += 0.01
        assert engine.stack.peek(1) == naive

        # 0.01 has no exact binary form, so a hundred of them do not make one.
        assert engine.stack.peek(1) != 1.0
        assert abs(engine.stack.peek(1) - 1.0) < 1e-14


class TestDomainsAndErrors:
    @pytest.mark.parametrize(
        "command, operands, message",
        [
            ("sqrt", (-1.0,), "Invalid Input"),
            ("sqrt", (-1e-300,), "Invalid Input"),
            ("ln", (0.0,), "Invalid Input"),
            ("ln", (-1.0,), "Invalid Input"),
            ("log", (0.0,), "Invalid Input"),
            ("log", (-5.0,), "Invalid Input"),
            ("asin", (1.0000001,), "Invalid Input"),
            ("asin", (-2.0,), "Invalid Input"),
            ("acos", (2.0,), "Invalid Input"),
            ("inv", (0.0,), "Infinite Result"),
            ("/", (1.0, 0.0), "Infinite Result"),
            ("/", (0.0, 0.0), "Undefined Result"),
            ("mod", (5.0, 0.0), "Infinite Result"),
            ("pow", (-2.0, 0.5), "Invalid Input"),
            ("xroot", (0.0, 4.0), "Infinite Result"),   # a zeroth root
            ("xroot", (2.0, -4.0), "Invalid Input"),    # even root of < 0
        ],
    )
    def test_error_leaves_the_stack_exactly_as_it_was(self, command, operands, message):
        engine = RpnEngine()
        for value in operands:
            engine.stack.push(value)
        before = engine.stack.to_list()
        engine.press(command)
        assert engine.error == message
        assert engine.stack.to_list() == before

    @pytest.mark.parametrize(
        "command",
        ["+", "-", "*", "/", "pow", "mod", "percent", "xroot",
         "sqrt", "sq", "inv", "ln", "exp", "log", "alog",
         "sin", "cos", "tan", "asin", "acos", "atan", "abs", "neg"],
    )
    def test_every_function_reports_underflow_rather_than_raising(self, command):
        engine = RpnEngine()
        engine.press(command)
        assert engine.error == "Too Few Arguments"
        assert engine.depth == 0

    @pytest.mark.parametrize(
        "command", ["+", "-", "*", "/", "pow", "mod", "percent", "xroot"]
    )
    def test_binary_functions_need_two_operands(self, command):
        engine = RpnEngine()
        engine.stack.push(1.0)
        engine.press(command)
        assert engine.error == "Too Few Arguments"
        assert engine.stack.to_list() == [1.0]

    def test_no_function_can_put_a_non_finite_value_on_the_stack(self):
        """The display cannot format infinity, so one reaching the stack would
        break every level at once, not just its own."""
        engine = RpnEngine()
        extremes = [0.0, 1e308, -1e308, 1e-308, 5e-324, 1.7976931348623157e308]
        for command in ["+", "-", "*", "/", "pow", "sq", "exp", "alog", "inv"]:
            for a in extremes:
                for b in extremes:
                    engine.stack.clear()
                    engine.stack.push(a)
                    engine.stack.push(b)
                    try:
                        engine.press(command)
                    except (StackError, CalcError):  # pragma: no cover
                        pytest.fail(f"{command} raised instead of reporting")
                    for value in engine.stack.to_list():
                        assert math.isfinite(value), f"{command}({a}, {b}) -> {value}"
                    engine.stack_lines()  # must never raise


class TestSignsAndZero:
    def test_negate_is_exact(self):
        for x in OPERANDS:
            assert apply("neg", x) == -x if x != 0 else apply("neg", x) == 0.0

    def test_absolute_value_is_exact(self):
        for x in OPERANDS:
            assert apply("abs", x) == abs(x)

    def test_negative_zero_never_reaches_the_display(self):
        engine = RpnEngine()
        engine.stack.push(0.0)
        engine.press("neg")
        assert engine.stack_lines() == ["0"]

    def test_mod_follows_the_sign_of_the_dividend(self):
        # math.fmod semantics, which is what the engine documents using.
        assert apply("mod", 7.0, 3.0) == 1.0
        assert apply("mod", -7.0, 3.0) == -1.0
        assert apply("mod", 7.0, -3.0) == 1.0
