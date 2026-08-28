"""HP 12C-style TVM and cash-flow math.

Algorithms follow the HP-12C User's Guide closed forms, cross-checked against
finanx-12c (MIT, Fabio Lima) — see that project's FinanceMemory for the Java
reference this was read against. Period interest `i` is a percent per period;
cash-flow signs are 12C-style (money out negative, money in positive).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class FinanceError(ValueError):
    """An unsolvable or out-of-domain finance problem."""


@dataclass
class CashFlow:
    amount: float
    times: int = 1

    def __post_init__(self) -> None:
        if self.times < 1 or self.times > 99:
            raise FinanceError("Nj must be between 1 and 99")


@dataclass
class FinanceMemory:
    """TVM registers plus the cash-flow list."""

    n: float = 0.0
    i: float = 0.0  # percent per period
    pv: float = 0.0
    pmt: float = 0.0
    fv: float = 0.0
    begin: bool = False  # True = Begin (annuity due), False = End
    pyr: float = 12.0  # periods per year (50g FINANCE screen)
    cash_flows: list[CashFlow] = field(default_factory=list)

    # -- 50g screen helpers -------------------------------------------------

    @property
    def i_yr(self) -> float:
        """Nominal annual rate as shown on the 50g (i × P/YR)."""
        return self.i * self.pyr

    @i_yr.setter
    def i_yr(self, annual: float) -> None:
        self.i = annual / self.pyr if self.pyr else annual

    # -- cash flows ---------------------------------------------------------

    def clear_cash_flows(self) -> None:
        self.cash_flows.clear()

    def set_cfo(self, amount: float) -> None:
        if not self.cash_flows:
            self.cash_flows.append(CashFlow(amount, 1))
        else:
            self.cash_flows[0] = CashFlow(amount, 1)

    def add_cfj(self, amount: float) -> None:
        if not self.cash_flows:
            self.cash_flows.append(CashFlow(0.0, 1))
        self.cash_flows.append(CashFlow(amount, 1))
        self.n = float(len(self.cash_flows) - 1)

    def set_nj(self, times: int) -> None:
        if not self.cash_flows:
            raise FinanceError("No cash flow to set Nj on")
        self.cash_flows[-1] = CashFlow(self.cash_flows[-1].amount, int(times))

    # -- TVM solve ----------------------------------------------------------

    def solve_n(self) -> float:
        self.n = period(self.i, self.pv, self.pmt, self.fv, self.begin)
        return self.n

    def solve_i(self) -> float:
        self.i = rate(self.n, self.pv, self.pmt, self.fv, self.begin)
        return self.i

    def solve_pv(self) -> float:
        self.pv = present_value(self.n, self.i, self.pmt, self.fv, self.begin)
        return self.pv

    def solve_pmt(self) -> float:
        self.pmt = payment(self.n, self.i, self.pv, self.fv, self.begin)
        return self.pmt

    def solve_fv(self) -> float:
        self.fv = future_value(self.n, self.i, self.pv, self.pmt, self.begin)
        return self.fv

    def npv(self) -> float:
        return npv(self.i, self.cash_flows)

    def irr(self) -> float:
        value = irr(self.cash_flows)
        self.i = value
        return value


def _frac(n: float) -> float:
    return n - math.floor(n)


def future_value(n: float, i_pct: float, pv: float, pmt: float, begin: bool) -> float:
    if i_pct <= -100:
        raise FinanceError("Compound Interest Error")
    if n == 0 and pmt == 0:
        return -pv
    i = i_pct / 100.0
    beg = 1.0 if begin else 0.0
    if i == 0:
        return -(pv + pmt * n)
    if _frac(n) == 0:
        factor = (1 - (1 + i) ** (-n)) / i
        return -((pv + (1 + i * beg) * pmt * factor) / ((1 + i) ** (-n)))
    # Odd period: compound the fractional part (12C C flag on).
    odd = (1 + i) ** _frac(n)
    full = math.floor(n)
    factor = (1 - (1 + i) ** (-full)) / i
    return -((pv * odd + (1 + i * beg) * pmt * factor) / ((1 + i) ** (-full)))


def present_value(n: float, i_pct: float, pmt: float, fv: float, begin: bool) -> float:
    if i_pct <= -100:
        raise FinanceError("Compound Interest Error")
    i = i_pct / 100.0
    beg = 1.0 if begin else 0.0
    if i == 0:
        return -(fv + pmt * n)
    if _frac(n) == 0:
        factor = (1 - (1 + i) ** (-n)) / i
        return -(fv * (1 + i) ** (-n) + (1 + i * beg) * pmt * factor)
    odd = (1 + i) ** _frac(n)
    full = math.floor(n)
    factor = (1 - (1 + i) ** (-full)) / i
    return -((fv * (1 + i) ** (-full) + (1 + i * beg) * pmt * factor) / odd)


def payment(n: float, i_pct: float, pv: float, fv: float, begin: bool) -> float:
    if i_pct <= -100:
        raise FinanceError("Compound Interest Error")
    if n == 0:
        raise FinanceError("Compound Interest Error")
    i = i_pct / 100.0
    beg = 1.0 if begin else 0.0
    if i == 0:
        return -(pv + fv) / n
    factor = (1 - (1 + i) ** (-n)) / i
    denom = (1 + i * beg) * factor
    if denom == 0:  # pragma: no cover - guarded by i_pct / n checks above
        raise FinanceError("Compound Interest Error")
    return -(pv + fv * (1 + i) ** (-n)) / denom


def period(i_pct: float, pv: float, pmt: float, fv: float, begin: bool) -> float:
    if i_pct <= -100:
        raise FinanceError("Compound Interest Error")
    if i_pct == 0:
        if pmt == 0:
            raise FinanceError("Compound Interest Error")
        return -(pv + fv) / pmt
    i = i_pct / 100.0
    beg = 1.0 if begin else 0.0
    num = pmt - i * fv + i * pmt * beg
    den = pmt + i * pv + i * pmt * beg
    if num == 0 or den == 0 or num / den <= 0:
        raise FinanceError("Compound Interest Error")
    n = math.log(num / den) / math.log(1 + i)
    # Nearly-integral n collapses to the integer the 12C would show.
    return math.floor(n) if abs(_frac(n)) < 0.005 else math.ceil(n)


def rate(n: float, pv: float, pmt: float, fv: float, begin: bool) -> float:
    """Bisection on i (percent), matching finanx-12c / 12C behaviour."""
    if n == 0:
        raise FinanceError("Compound Interest Error")
    if (pv > 0 and fv > 0) or (pv < 0 and fv < 0):
        raise FinanceError("Compound Interest Error")
    # Normalize signs the way finanx does before searching.
    pv_n = -abs(pv)
    pmt_n = abs(pmt)
    fv_n = abs(fv)
    # The payment has to actually respond to the rate, or there is no rate to
    # find and bisection would "converge" on whichever bound it started from.
    # A single Begin-mode period with no balloon is the case that bites: the
    # annuity-due factor cancels the discount exactly, so the payment is -PV
    # whatever the interest. So is the all-zero problem. A 12C answers Error 5
    # for both rather than inventing a number.
    # Compared with a tolerance, not for equality: the flat case only agrees to
    # about 1e-15 relative, while two rates a hundredfold apart move a solvable
    # payment by a fraction of itself. There is no middle ground to get wrong.
    if math.isclose(
        payment(n, 1.0, pv_n, fv_n, begin),
        payment(n, 100.0, pv_n, fv_n, begin),
        rel_tol=1e-9,
        abs_tol=1e-12,
    ):
        raise FinanceError("Compound Interest Error")
    low, high = -1.0, 99999.0
    for _ in range(10000):
        mid = (low + high) / 2.0
        try:
            guessed = payment(n, mid, pv_n, fv_n, begin)
        except (FinanceError, ZeroDivisionError, ValueError, OverflowError):
            high = mid
            continue
        if abs(pmt_n - guessed) <= 1e-9:
            return mid
        if guessed > pmt_n:
            high = mid
        else:
            low = mid
    raise FinanceError("Compound Interest Error")


def npv(i_pct: float, flows: list[CashFlow]) -> float:
    if not flows:
        return 0.0
    if i_pct <= -100:
        raise FinanceError("Compound Interest Error")
    i = i_pct / 100.0
    total = flows[0].amount
    exponent = 0
    for flow in flows[1:]:
        for _ in range(flow.times):
            exponent += 1
            total += flow.amount / ((1 + i) ** exponent)
    return total


def irr(flows: list[CashFlow]) -> float:
    """Search for the periodic rate (percent) that zeros NPV."""
    if len(flows) < 2:
        raise FinanceError("IRR Error")
    # Bracket a sign change, then bisection.
    low, high = -99.999999, 1000.0
    f_low = npv(low, flows)
    guess = 100.0
    step = 100.0
    found = False
    for _ in range(200):
        try:
            f_guess = npv(guess, flows)
        except (FinanceError, OverflowError, ZeroDivisionError):
            guess -= step
            continue
        if f_low * f_guess <= 0:
            high = guess
            found = True
            break
        guess += step
        step *= 0.5
        if guess > 10000:  # pragma: no cover - defensive cap
            break
    if not found:
        # Fall back to bisection over a wide range.
        high = 1000.0
        if f_low * npv(high, flows) > 0:
            raise FinanceError("IRR Error")
    for _ in range(80):
        mid = (low + high) / 2.0
        f_mid = npv(mid, flows)
        if abs(f_mid) < 1e-10:
            return mid
        if f_low * f_mid <= 0:
            high = mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2.0  # pragma: no cover - 80 iters is enough in practice
