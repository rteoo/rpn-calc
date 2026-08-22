"""An independent reference implementation, for checking the engine's answers.

The engine computes with `math` on binary floats. Checking it against `math`
would only prove it calls the function it says it calls. Everything here is
computed with `decimal` at 50 significant digits instead - a different number
representation and, for the trigonometric functions, a different algorithm - so
agreeing with it is real evidence rather than a tautology.

Inputs convert with `Decimal(value)`, which takes the float's *exact* binary
value, not `Decimal(repr(value))`, which takes its shortest printable form.
The difference matters: 0.9999999999 is not exactly that decimal, and asking
what the engine should have returned for a number it never held produces
failures that are the test's fault rather than the engine's.

Not a general-purpose library: it exists to answer "what should this have been?"
inside the test suite.
"""

from __future__ import annotations

from decimal import Decimal, getcontext, localcontext

PRECISION = 50
getcontext().prec = PRECISION

# pi to 60 digits, typed from a published value rather than computed with
# anything the engine also uses.
PI = Decimal(
    "3.14159265358979323846264338327950288419716939937510582097494"
)


def _sin_series(x: Decimal) -> Decimal:
    """sin by Taylor series - the recipe from the decimal documentation."""
    with localcontext() as ctx:
        ctx.prec += 10
        i, lasts, s, fact, num, sign = 1, 0, x, 1, x, 1
        while s != lasts:
            lasts = s
            i += 2
            fact *= i * (i - 1)
            num *= x * x
            sign *= -1
            s += num / fact * sign
    return +s


def _cos_series(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += 10
        i, lasts, s, fact, num, sign = 0, 0, Decimal(1), 1, Decimal(1), 1
        while s != lasts:
            lasts = s
            i += 2
            fact *= i * (i - 1)
            num *= x * x
            sign *= -1
            s += num / fact * sign
    return +s


def _reduce(x: Decimal) -> Decimal:
    """Fold an angle into [-pi, pi] so the series converges quickly."""
    two_pi = 2 * PI
    with localcontext() as ctx:
        ctx.prec += 10
        turns = (x / two_pi).to_integral_value(rounding="ROUND_HALF_EVEN")
        return +(x - turns * two_pi)


def sin(x: float) -> Decimal:
    return _sin_series(_reduce(Decimal(x)))


def cos(x: float) -> Decimal:
    return _cos_series(_reduce(Decimal(x)))


def tan(x: float) -> Decimal:
    reduced = _reduce(Decimal(x))
    return _sin_series(reduced) / _cos_series(reduced)


def radians(degrees: float) -> Decimal:
    return Decimal(degrees) * PI / 180


def degrees(radians_value: Decimal) -> Decimal:
    return radians_value * 180 / PI


def sqrt(x: float) -> Decimal:
    return Decimal(x).sqrt()


def ln(x: float) -> Decimal:
    return Decimal(x).ln()


def log10(x: float) -> Decimal:
    return Decimal(x).log10()


def exp(x: float) -> Decimal:
    return Decimal(x).exp()


def alog(x: float) -> Decimal:
    """10 raised to x."""
    return (Decimal(x) * Decimal(10).ln()).exp()


def power(base: float, exponent: float) -> Decimal:
    b = Decimal(base)
    e = Decimal(exponent)
    if b == 0:
        return Decimal(0) if e > 0 else Decimal("NaN")
    if b < 0:
        if e != e.to_integral_value():
            return Decimal("NaN")
        magnitude = (e * (-b).ln()).exp()
        return -magnitude if int(e) % 2 else magnitude
    return (e * b.ln()).exp()


def add(a: float, b: float) -> Decimal:
    return Decimal(a) + Decimal(b)


def sub(a: float, b: float) -> Decimal:
    return Decimal(a) - Decimal(b)


def mul(a: float, b: float) -> Decimal:
    return Decimal(a) * Decimal(b)


def div(a: float, b: float) -> Decimal:
    return Decimal(a) / Decimal(b)


def percent(base: float, pct: float) -> Decimal:
    return Decimal(base) * Decimal(pct) / 100


def relative_error(actual: float, expected: Decimal) -> Decimal:
    """How far `actual` is from the reference, as a fraction of the reference."""
    got = Decimal(actual)
    if expected == 0:
        return abs(got)
    return abs((got - expected) / expected)


# A double carries about 15.95 decimal digits. Anything within a few ulp of the
# reference is as close as binary floating point can get; wider than that means
# the engine, not the representation, is losing precision.
DOUBLE_TOLERANCE = Decimal("1e-14")


def _atan_series(z: Decimal) -> Decimal:
    """atan by Taylor series. Only used for small |z|, where it converges fast."""
    with localcontext() as ctx:
        ctx.prec += 10
        total = Decimal(0)
        term = z
        n = 0
        while True:
            contribution = term / (2 * n + 1)
            if contribution == 0:
                break
            total += contribution if n % 2 == 0 else -contribution
            term *= z * z
            n += 1
    return +total


def _atan_small(z: Decimal) -> Decimal:
    """atan for 0 <= z <= 1, reduced until the series converges quickly.

    atan(z) = 2 * atan(z / (1 + sqrt(1 + z^2))) halves the argument each time.
    Without this the series crawls as z approaches 1, and at z = 1 it does not
    converge at all.
    """
    with localcontext() as ctx:
        ctx.prec += 10
        halvings = 0
        while z > Decimal("0.05"):
            z = z / (1 + (1 + z * z).sqrt())
            halvings += 1
        result = _atan_series(z) * (2 ** halvings)
    return +result


def _atan_decimal(z: Decimal) -> Decimal:
    negative = z < 0
    z = abs(z)
    # Above 1 the series has no useful convergence, so reflect through pi/2.
    result = (PI / 2 - _atan_small(1 / z)) if z > 1 else _atan_small(z)
    return -result if negative else result


def atan(x: float) -> Decimal:
    return _atan_decimal(Decimal(x))


def asin(x: float) -> Decimal:
    """asin via atan, an exact identity rather than a second series."""
    value = Decimal(x)
    if abs(value) == 1:
        return (PI / 2) if value > 0 else -(PI / 2)
    with localcontext() as ctx:
        ctx.prec += 10
        ratio = value / (1 - value * value).sqrt()
    return _atan_decimal(ratio)


def acos(x: float) -> Decimal:
    return PI / 2 - asin(x)
