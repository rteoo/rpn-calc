"""TVM / cash-flow math and 12C-style face keys.

Closed-form vectors are the usual HP-12C textbook cases; tolerance is loose
enough for bisection on i / IRR without hiding a wrong formula.
"""

import math

import pytest

from rpncalc.finance import (
    CashFlow,
    FinanceError,
    FinanceMemory,
    future_value,
    irr,
    npv,
    payment,
    period,
    present_value,
    rate,
)
from rpncalc.rpn_engine import RpnEngine
from rpncalc.stack import StackError


def accumulate(engine, values):
    """Feed one-variable samples in through the real Σ+ keypath."""
    for value in values:
        engine.press("clear")
        for char in str(value):
            engine.press(char)
        engine.press("sum_plus")
    return engine


class TestTvmClosedForm:
    def test_payment_on_a_loan(self):
        pmt = payment(36, 1.0, 10000.0, 0.0, begin=False)
        assert pmt == pytest.approx(-332.143, abs=0.01)

    def test_present_value_of_an_annuity(self):
        pv = present_value(20, 5.0, -1000.0, 0.0, begin=False)
        assert pv == pytest.approx(12462.21, abs=0.05)

    def test_future_value_of_savings(self):
        fv = future_value(12, 1.0, 0.0, -100.0, begin=False)
        assert fv == pytest.approx(1268.25, abs=0.05)

    def test_period_rounds_like_the_12c(self):
        n = period(1.0, 10000.0, -332.14, 0.0, begin=False)
        assert n == pytest.approx(36, abs=1)

    def test_rate_recovers_the_loan_interest(self):
        i = rate(36, 10000.0, -332.14, 0.0, begin=False)
        assert i == pytest.approx(1.0, abs=0.01)

    def test_rate_recovers_a_high_rate_with_same_signed_pv_and_fv(self):
        pmt = payment(1, 800.0, 1000.0, 1000.0, False)
        assert pmt == pytest.approx(-10000.0)
        assert rate(1, 1000.0, pmt, 1000.0, False) == pytest.approx(800.0)

    def test_rate_recovers_a_negative_rate(self):
        assert rate(1, -100.0, 0.0, 50.0, False) == pytest.approx(-50.0)

    def test_rate_rejects_same_signed_cash_flows(self):
        with pytest.raises(FinanceError, match="Compound Interest Error"):
            rate(1, -100.0, -110.0, 0.0, False)

    def test_begin_mode_changes_payment(self):
        end = payment(12, 1.0, 1000.0, 0.0, begin=False)
        beg = payment(12, 1.0, 1000.0, 0.0, begin=True)
        assert beg != pytest.approx(end)
        assert abs(beg) < abs(end)

    def test_zero_interest_paths(self):
        assert payment(10, 0.0, 1000.0, 0.0, False) == pytest.approx(-100.0)
        assert present_value(10, 0.0, -100.0, 0.0, False) == pytest.approx(1000.0)
        assert future_value(10, 0.0, 1000.0, -100.0, False) == pytest.approx(0.0)
        assert period(0.0, 1000.0, -100.0, 0.0, False) == pytest.approx(10.0)

    def test_n_zero_future_value(self):
        assert future_value(0, 5.0, 100.0, 0.0, False) == pytest.approx(-100.0)

    def test_odd_period_compounds_the_fraction(self):
        # Fractional n takes the 12C C-flag path.
        fv = future_value(12.5, 1.0, 0.0, -100.0, False)
        assert math.isfinite(fv)
        pv = present_value(12.5, 1.0, -100.0, 0.0, False)
        assert math.isfinite(pv)

    def test_domain_errors(self):
        with pytest.raises(FinanceError):
            payment(0, 1.0, 1000.0, 0.0, False)
        with pytest.raises(FinanceError):
            payment(10, -100.0, 1000.0, 0.0, False)
        with pytest.raises(FinanceError):
            present_value(10, -100.0, -100.0, 0.0, False)
        with pytest.raises(FinanceError):
            future_value(10, -100.0, 1000.0, -100.0, False)
        with pytest.raises(FinanceError):
            period(-100.0, 1000.0, -100.0, 0.0, False)
        with pytest.raises(FinanceError):
            period(0.0, 1000.0, 0.0, 0.0, False)
        with pytest.raises(FinanceError):
            period(5.0, 0.0, 0.0, 0.0, False)
        with pytest.raises(FinanceError):
            rate(0, 1000.0, -100.0, 0.0, False)
        with pytest.raises(FinanceError):
            rate(10, 1000.0, -100.0, 1000.0, False)


class TestCashFlows:
    def test_npv_simple_project(self):
        flows = [CashFlow(-1000), CashFlow(600), CashFlow(600)]
        assert npv(10.0, flows) == pytest.approx(41.32, abs=0.05)

    def test_irr_simple_project(self):
        flows = [CashFlow(-1000), CashFlow(600), CashFlow(600)]
        rate_pct = irr(flows)
        assert rate_pct == pytest.approx(13.066, abs=0.05)
        assert npv(rate_pct, flows) == pytest.approx(0.0, abs=1e-6)

    def test_npv_empty_and_bad_rate(self):
        assert npv(10.0, []) == 0.0
        with pytest.raises(FinanceError):
            npv(-100.0, [CashFlow(-1), CashFlow(1)])

    def test_irr_needs_two_flows(self):
        with pytest.raises(FinanceError):
            irr([CashFlow(-1000)])

    def test_irr_all_same_sign_fails(self):
        with pytest.raises(FinanceError):
            irr([CashFlow(100), CashFlow(100), CashFlow(100)])

    def test_cash_flow_times_bounds(self):
        with pytest.raises(FinanceError):
            CashFlow(1.0, 0)
        with pytest.raises(FinanceError):
            CashFlow(1.0, 100)

    def test_memory_helpers(self):
        mem = FinanceMemory()
        mem.clear_cash_flows()
        mem.set_cfo(-5000)
        mem.set_cfo(-4000)  # replace
        assert mem.cash_flows[0].amount == -4000
        mem.add_cfj(1000)
        mem.set_nj(6)
        assert mem.cash_flows[-1].times == 6
        mem.i = 10.0
        assert mem.npv() == pytest.approx(npv(10.0, mem.cash_flows))
        mem2 = FinanceMemory()
        mem2.add_cfj(50)  # creates a zero CF0 first
        assert mem2.cash_flows[0].amount == 0.0
        with pytest.raises(FinanceError):
            FinanceMemory().set_nj(2)

    def test_i_yr_and_solvers(self):
        mem = FinanceMemory(n=36, i=1.0, pv=10000.0, fv=0.0, begin=False)
        assert mem.i_yr == pytest.approx(12.0)
        mem.i_yr = 12.0
        assert mem.i == pytest.approx(1.0)
        mem.pyr = 0.0
        mem.i_yr = 5.0  # pyr==0 keeps the annual as period rate
        assert mem.i == 5.0
        mem.pyr = 12.0
        mem.i = 1.0
        assert mem.solve_pmt() == pytest.approx(-332.14, abs=0.05)
        mem.pmt = mem.pmt
        assert mem.solve_n() == pytest.approx(36, abs=1)
        assert mem.solve_i() == pytest.approx(1.0, abs=0.05)
        assert mem.solve_pv() == pytest.approx(10000.0, abs=1)
        mem.pv = 0.0
        mem.pmt = -100.0
        mem.n = 12
        mem.i = 1.0
        assert mem.solve_fv() == pytest.approx(1268.25, abs=0.05)
        mem.set_cfo(-1000)
        mem.add_cfj(600)
        mem.add_cfj(600)
        assert mem.irr() == pytest.approx(13.066, abs=0.05)


class TestFaceKeys:
    def test_store_then_solve_loan_payment(self):
        e = RpnEngine()
        for keys in (
            "3 6 fin_n",
            "1 fin_i",
            "1 0 0 0 0 fin_pv",
            "0 fin_fv",
        ):
            for k in keys.split():
                e.press(k)
        e.press("fin_pmt")  # no fresh entry → solve
        assert e.stack.peek(1) == pytest.approx(-332.14, abs=0.05)
        assert e.finance.pmt == pytest.approx(-332.14, abs=0.05)

    def test_finance_screen_solve_for_pv(self):
        e = RpnEngine()
        e.finance.n = 20
        e.finance.i = 5
        e.finance.pmt = -1000
        e.finance.fv = 0
        e.finance_cursor = 2  # pv
        e.finance_menu(2)  # SOLVE
        assert e.error is None
        assert e.finance.pv == pytest.approx(12462.21, abs=0.05)

    def test_finance_screen_edit_and_begin_toggle(self):
        e = RpnEngine()
        e.stack.push(48.0)
        e.finance_cursor = 0  # n
        e.finance_menu(0)  # EDIT
        assert e.finance.n == 48.0
        e.stack.push(6.0)
        e.finance_cursor = 1  # i_yr
        e.finance_menu(0)
        assert e.finance.i_yr == pytest.approx(6.0)
        e.stack.push(1.0)
        e.finance_cursor = 2
        e.finance_menu(0)
        e.stack.push(-10.0)
        e.finance_cursor = 3
        e.finance_menu(0)
        e.stack.push(0.0)
        e.finance_cursor = 4
        e.finance_menu(0)
        e.stack.push(4.0)
        e.finance_cursor = 5  # pyr
        e.finance_menu(0)
        assert e.finance.pyr == 4.0
        e.finance_cursor = 6  # begin
        assert e.finance.begin is False
        e.finance_menu(0)
        assert e.finance.begin is True
        e.finance_menu(2)  # SOLVE on begin toggles back
        assert e.finance.begin is False

    def test_finance_screen_solve_other_fields(self):
        e = RpnEngine()
        e.finance.n = 36
        e.finance.i = 1
        e.finance.pv = 10000
        e.finance.fv = 0
        e.finance_cursor = 3  # pmt
        e.finance_menu(2)
        assert e.stack.peek(1) == pytest.approx(-332.14, abs=0.05)
        e.finance_cursor = 0
        e.finance_menu(2)  # solve n
        e.finance_cursor = 1
        e.finance_menu(2)  # solve i_yr
        e.finance_cursor = 4
        e.finance.pmt = e.finance.pmt
        e.finance.pv = 0
        e.finance.n = 12
        e.finance.i = 1
        e.finance.pmt = -100
        e.finance_menu(2)  # fv
        e.finance_cursor = 5
        e.finance_menu(2)  # pyr is a no-op
        e.finance_menu(1)  # AMOR inert

    def test_finance_menu_errors(self):
        e = RpnEngine()
        e.finance_cursor = 0
        e.finance_menu(0)  # EDIT with empty stack
        assert e.error == "Too Few Arguments"
        e.stack.push(0.0)
        e.finance_cursor = 5
        e.finance_menu(0)  # pyr = 0
        assert e.error == "Compound Interest Error"

    def test_finance_move_wraps(self):
        e = RpnEngine()
        e.finance_cursor = 0
        e.finance_move("up")
        assert e.finance_cursor == len(e._FINANCE_FIELDS) - 1
        e.finance_move("down")
        assert e.finance_cursor == 0

    def test_cash_flow_face_keys(self):
        e = RpnEngine()
        for k in ("1", "0", "0", "0", "chs", "fin_cfo"):
            e.press(k)
        for k in ("6", "0", "0", "fin_cfj"):
            e.press(k)
        for k in ("6", "0", "0", "fin_cfj"):
            e.press(k)
        for k in ("1", "0", "fin_i"):
            e.press(k)
        e.press("fin_npv")
        assert e.stack.peek(1) == pytest.approx(41.32, abs=0.05)
        e.press("fin_irr")
        assert e.stack.peek(1) == pytest.approx(13.066, abs=0.05)
        for k in ("3", "fin_nj"):
            e.press(k)
        assert e.finance.cash_flows[-1].times == 3

    def test_finance_store_without_stack_errors(self):
        e = RpnEngine()
        e._finance_store_pending = True
        e.press("fin_n")
        assert e.error == "Too Few Arguments"

    def test_cf_keys_need_arguments(self):
        e = RpnEngine()
        e.press("fin_cfo")
        assert e.error == "Too Few Arguments"
        e.press("fin_cfj")
        assert e.error == "Too Few Arguments"
        e.press("fin_nj")
        assert e.error == "Too Few Arguments"

    def test_delta_percent_and_fact(self):
        e = RpnEngine()
        for k in ("1", "0", "0", "enter", "1", "2", "0", "delta_percent"):
            e.press(k)
        assert e.stack.peek(1) == pytest.approx(20.0)
        for k in ("5", "fact"):
            e.press(k)
        assert e.stack.peek(1) == 120.0

    def test_fact_and_delta_errors(self):
        e = RpnEngine()
        e.press("1")
        e.press("chs")
        e.press("fact")
        assert e.error == "Invalid Input"
        for k in ("0", "enter", "1", "delta_percent"):
            e.press(k)
        assert e.error == "Infinite Result"

    def test_sum_plus_and_e(self):
        e = RpnEngine()
        e.press("e")
        assert e.stack.peek(1) == pytest.approx(math.e)
        e.press("drop")
        for k in ("2", "enter", "3", "sum_plus"):
            e.press(k)
        # n replaces level 1; the y value is read, not eaten.
        assert e.stack.to_list() == [1.0, 2.0]
        e.press("4")
        e.press("sum_plus")
        assert e.stack.to_list() == [2.0, 1.0, 2.0]
        e.press("clear")
        e.press("sum_plus")
        assert e.error == "Too Few Arguments"

    def test_defensive_unknown_finance_helpers(self):
        e = RpnEngine()
        with pytest.raises(ValueError):
            e._apply_finance("fin_nope", store=False)
        with pytest.raises(FinanceError):
            e._solve_finance_field("begin")
        e.finance_move("sideways")  # neither up nor down
        e._store_finance_field("begin", 1.0)  # no-op field

    def test_sum_plus_single_level(self):
        e = RpnEngine()
        e.stack.push(5.0)
        e.press("sum_plus")
        assert e.stack.peek(1) == 1.0


class TestHardBranches:
    def test_period_floors_near_integers(self):
        pmt = payment(36, 1.0, 10000.0, 0.0, False)
        assert period(1.0, 10000.0, pmt, 0.0, False) == 36.0

    def test_rate_bisection_skips_bad_mids(self, monkeypatch):
        real = payment

        def flaky(n, i_pct, pv, fv, begin):
            # Make the far end of the search range unevaluable, so the
            # bisection has to walk `high` down past it. Keyed on the rate
            # rather than a call count: `rate` probes for a flat payment
            # before it starts, and a counting stub would swallow the probe
            # instead of the mids this test is about.
            if i_pct > 1000.0:
                raise FinanceError("Compound Interest Error")
            return real(n, i_pct, pv, fv, begin)

        monkeypatch.setattr("rpncalc.finance.payment", flaky)
        assert rate(36, 10000.0, -332.14, 0.0, False) == pytest.approx(1.0, abs=0.05)

    def test_rate_gives_up(self, monkeypatch):
        # Varies with the rate, so it clears the flatness probe, but never
        # comes near the payment asked for: the bisection has to exhaust its
        # iteration budget and give up.
        monkeypatch.setattr(
            "rpncalc.finance.payment",
            lambda n, i_pct, *a, **k: 999999.0 + i_pct,
        )
        with pytest.raises(FinanceError):
            rate(10, 1000.0, -100.0, 0.0, False)

    def test_irr_overflow_and_fallback(self, monkeypatch):
        flows = [CashFlow(-100), CashFlow(10), CashFlow(10)]
        real = npv
        state = {"n": 0}

        def boom(i_pct, fs):
            state["n"] += 1
            if state["n"] == 2:
                raise OverflowError
            return real(i_pct, fs)

        monkeypatch.setattr("rpncalc.finance.npv", boom)
        # May still find a root or raise; either path exercises the handler.
        try:
            irr(flows)
        except FinanceError:
            pass

    def test_irr_returns_midpoint_when_flat(self, monkeypatch):
        flows = [CashFlow(-100), CashFlow(50), CashFlow(50)]
        # Never quite zero → fall off the end of the bisection loop.
        monkeypatch.setattr(
            "rpncalc.finance.npv",
            lambda i, fs: 1.0 if i < 0 else -1.0,
        )
        assert isinstance(irr(flows), float)

    def test_irr_hits_exact_zero(self, monkeypatch):
        flows = [CashFlow(-100), CashFlow(110)]
        monkeypatch.setattr(
            "rpncalc.finance.npv",
            lambda i, fs: 0.0 if abs(i - 10.0) < 50 else (1.0 if i < 10 else -1.0),
        )
        assert irr(flows) == pytest.approx(10.0, abs=50)

    def test_irr_search_exhausts_then_bisects(self, monkeypatch):
        flows = [CashFlow(-100), CashFlow(50), CashFlow(60)]

        def controlled(i, fs):
            if i < 0:
                return -1.0
            if i >= 1000:
                return 1.0
            return -1.0

        monkeypatch.setattr("rpncalc.finance.npv", controlled)
        assert isinstance(irr(flows), float)


class TestRateSolvesForTheRateItFound:
    """Regressions for two `rate()` bugs that 100% branch coverage missed.

    Both produced a number rather than an error, which on a calculator is the
    expensive kind of wrong: `1 n · 1000 PV · 1000 CHS PMT · BEGIN · [i]` used
    to answer 99999% per period with no error showing. Coverage never caught
    it because `rate` was only ever exercised in End mode.
    """

    def test_returns_the_mid_it_converged_on_not_a_bound(self):
        # `rate` bisects low=-1, high=99999, so its first mid is 49999. Feed it
        # the payment that mid produces: it matches on iteration one, and the
        # early exit used to hand back `high` - double the right answer.
        first_mid = (-1.0 + 99999.0) / 2.0
        pmt_at_first_mid = payment(5.0, first_mid, -1000.0, 0.0, False)
        found = rate(5.0, 1000.0, -abs(pmt_at_first_mid), 0.0, False)
        assert found == pytest.approx(first_mid, rel=1e-9)

    @pytest.mark.parametrize("begin", [False, True])
    @pytest.mark.parametrize("n", [2, 5, 12, 60, 360])
    @pytest.mark.parametrize("i", [0.01, 0.5, 0.75, 5.0, 25.0, 100.0])
    def test_recovers_the_rate_that_built_the_payment(self, n, i, begin):
        """The round trip that would have caught both bugs on its own."""
        pmt = payment(n, i, -1000.0, 0.0, begin)
        assert rate(n, -1000.0, pmt, 0.0, begin) == pytest.approx(i, rel=1e-6)

    @pytest.mark.parametrize("i", [0.5, 5.0, 12.0, 500.0])
    def test_one_begin_period_pays_back_the_principal_whatever_the_rate(self, i):
        """Why the case below is unsolvable, stated as an assertion."""
        assert payment(1, i, -1000.0, 0.0, True) == pytest.approx(1000.0)

    @pytest.mark.parametrize("i", [0.5, 5.0, 12.0])
    def test_refuses_a_single_begin_period_with_no_balloon(self, i):
        pmt = payment(1, i, -1000.0, 0.0, True)
        with pytest.raises(FinanceError):
            rate(1, -1000.0, pmt, 0.0, True)

    def test_refuses_the_all_zero_problem(self):
        # Every rate satisfies 0 = 0; there is nothing to report.
        with pytest.raises(FinanceError):
            rate(10, 0.0, 0.0, 0.0, False)

    def test_a_begin_period_with_a_balloon_is_still_solvable(self):
        """The guard must refuse only the flat case, not Begin mode at large."""
        pmt = payment(1, 7.5, -1000.0, 250.0, True)
        assert rate(1, -1000.0, pmt, 250.0, True) == pytest.approx(7.5, rel=1e-6)

    def test_the_engine_reports_the_error_instead_of_a_rate(self):
        """Through real keystrokes: the bug as a user would have met it."""
        e = RpnEngine()
        e.finance.begin = True
        for k in ("1", "fin_n"):
            e.press(k)
        for k in ("1", "0", "0", "0", "fin_pv"):
            e.press(k)
        for k in ("1", "0", "0", "0", "chs", "fin_pmt"):
            e.press(k)
        depth_before = e.stack.depth
        e.press("fin_i")
        assert e.error == "Compound Interest Error"
        assert e.stack.depth == depth_before  # errors never mutate the stack


class TestStatisticsRegisters:
    """Σ+ accumulates into registers MEAN reads back and CLΣ resets.

    Σ+ shipped with `_stats_sx` / `_stats_sy` written and never read, and it
    ate level 2 on the way. 12C semantics: x from level 1, y read from level 2
    but *not* consumed, n replacing level 1.
    """

    def test_sum_plus_replaces_level_one_and_keeps_level_two(self):
        e = RpnEngine()
        for k in ("7", "enter", "2", "enter", "3", "sum_plus"):
            e.press(k)
        assert e.stack.to_list() == [1.0, 2.0, 7.0]

    def test_mean_returns_both_means(self):
        e = RpnEngine()
        # Pairs (y, x): (10, 1), (20, 2), (30, 3).
        for y, x in ((10, 1), (20, 2), (30, 3)):
            e.stack.clear()
            e.stack.push(float(y))
            e.stack.push(float(x))
            e.press("sum_plus")
        e.stack.clear()
        e.press("mean")
        assert e.stack.peek(1) == pytest.approx(2.0)   # x̄ into level 1
        assert e.stack.peek(2) == pytest.approx(20.0)  # ȳ into level 2

    def test_a_one_variable_sample_means_over_x_alone(self):
        e = RpnEngine()
        for value in ("4", "6", "1", "1"):
            e.press(value)
            e.press("sum_plus")
            e.press("drop")
        e.press("mean")
        assert e.stack.peek(1) == pytest.approx((4 + 6 + 1 + 1) / 4)

    def test_sigma_returns_the_running_totals(self):
        """The whole point of the accumulator: read the sum back out."""
        e = RpnEngine()
        for value in ("12", "30", "5", "3"):
            e.press("clear")
            for char in value:
                e.press(char)
            e.press("sum_plus")
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(50.0)   # Σx into level 1
        assert e.stack.peek(2) == pytest.approx(0.0)    # Σy, untouched here

    def test_sigma_returns_both_totals_for_paired_data(self):
        e = RpnEngine()
        for y, x in ((10, 1), (20, 2), (30, 3)):
            e.stack.clear()
            e.stack.push(float(y))
            e.stack.push(float(x))
            e.press("sum_plus")
        e.stack.clear()
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(6.0)    # Σx
        assert e.stack.peek(2) == pytest.approx(60.0)   # Σy

    def test_mean_is_sigma_over_n(self):
        """The two readbacks have to agree, or one of them is lying."""
        e = RpnEngine()
        for value in (3.5, -2.0, 11.25, 0.75):
            e.stack.clear()
            e.stack.push(value)
            e.press("sum_plus")
        e.stack.clear()
        e.press("sigma_sum")
        total = e.stack.peek(1)
        e.stack.clear()
        e.press("mean")
        assert e.stack.peek(1) == pytest.approx(total / 4)

    def test_sigma_without_any_data_errors(self):
        e = RpnEngine()
        e.press("sigma_sum")
        assert e.error == "Statistics Error"
        assert e.stack.depth == 0

    def test_clear_sigma_forgets_the_totals_too(self):
        e = RpnEngine()
        for k in ("4", "sum_plus"):
            e.press(k)
        e.press("clear_sigma")
        e.press("sigma_sum")
        assert e.error == "Statistics Error"

    def test_undo_rolls_the_totals_back_with_the_pair(self):
        e = RpnEngine()
        for k in ("4", "0", "sum_plus"):
            e.press(k)
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(40.0)
        e.press("clear")
        for k in ("2", "sum_plus"):
            e.press(k)
        e.press("undo")
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(40.0)  # the 2 went back

    def test_median_of_an_odd_sample_is_the_middle_value(self):
        e = accumulate(RpnEngine(), [7, 1, 5, 3, 9])
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(5.0)

    def test_median_of_an_even_sample_averages_the_two_middles(self):
        e = accumulate(RpnEngine(), [7, 1, 5, 3])
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(4.0)  # (3 + 5) / 2

    def test_median_does_not_care_what_order_they_arrived_in(self):
        first = accumulate(RpnEngine(), [10, 2, 8, 4, 6])
        second = accumulate(RpnEngine(), [6, 8, 2, 10, 4])
        for engine in (first, second):
            engine.stack.clear()
            engine.press("median")
        assert first.stack.peek(1) == second.stack.peek(1) == pytest.approx(6.0)

    def test_median_is_not_the_mean(self):
        """A skewed sample, where confusing the two would go unnoticed."""
        e = accumulate(RpnEngine(), [1, 2, 3, 4, 1000])
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(3.0)
        e.stack.clear()
        e.press("mean")
        assert e.stack.peek(1) == pytest.approx(202.0)

    def test_stddev_is_the_sample_form_dividing_by_n_minus_one(self):
        e = accumulate(RpnEngine(), [2, 4, 4, 4, 5, 5, 7, 9])
        e.stack.clear()
        e.press("stddev")
        # Population σ here is exactly 2; the sample s is larger.
        assert e.stack.peek(1) == pytest.approx(2.13809, abs=1e-5)

    def test_stddev_of_identical_values_is_zero(self):
        e = accumulate(RpnEngine(), [3, 3, 3, 3])
        e.stack.clear()
        e.press("stddev")
        assert e.stack.peek(1) == pytest.approx(0.0)

    def test_stddev_survives_data_far_from_zero(self):
        """Why STD works off the points and not off Σx².

        `Σx² - n·x̄²` subtracts two enormous nearly-equal numbers here and
        keeps almost none of the answer. The spacing is 1, so s is exactly 1.
        """
        e = accumulate(RpnEngine(), [1e9, 1e9 + 1, 1e9 + 2])
        e.stack.clear()
        e.press("stddev")
        assert e.stack.peek(1) == pytest.approx(1.0, rel=1e-12)

    def test_stddev_needs_two_points(self):
        e = accumulate(RpnEngine(), [5])
        e.stack.clear()
        e.press("stddev")
        assert e.error == "Statistics Error"
        assert e.stack.depth == 0
        # MEAN and MEDIAN are answerable for one point; only spread is not.
        e.press("mean")
        assert e.error is None

    def test_median_and_stddev_report_both_columns(self):
        e = RpnEngine()
        for y, x in ((10, 1), (50, 5), (30, 3)):
            e.stack.clear()
            e.stack.push(float(y))
            e.stack.push(float(x))
            e.press("sum_plus")
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(3.0)   # median x
        assert e.stack.peek(2) == pytest.approx(30.0)  # median y
        e.stack.clear()
        e.press("stddev")
        assert e.stack.peek(1) == pytest.approx(2.0)   # s of 1, 3, 5
        assert e.stack.peek(2) == pytest.approx(20.0)  # s of 10, 30, 50

    def test_a_sample_at_the_float_ceiling_reports_rather_than_crashes(self):
        """Summarising near the ceiling overflows inside the statistics.

        `press` catches StackError, CalcError and FinanceError - an
        OverflowError escaping a readback would take the window down instead
        of showing a message, so they go through `_evaluate` like every other
        function in the engine.
        """
        import struct

        def next_float(value):
            bits = struct.unpack("q", struct.pack("d", value))[0]
            return struct.unpack("d", struct.pack("q", bits + 1))[0]

        e = RpnEngine()
        for value in (1e300, next_float(1e300)):
            e.stack.clear()
            e.stack.push(value)
            e.press("sum_plus")
        e.stack.clear()
        e.press("stddev")
        assert e.error == "Infinite Result"
        assert e.stack.depth == 0

    def test_a_huge_but_summable_sample_still_answers(self):
        """The guard must refuse only what actually overflows."""
        e = RpnEngine()
        for value in (1e300, 2e300, 3e300):
            e.stack.clear()
            e.stack.push(value)
            e.press("sum_plus")
        e.stack.clear()
        e.press("sigma_sum")
        assert e.error is None
        assert e.stack.peek(1) == pytest.approx(6e300)   # still finite
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(2e300)

    def test_a_sum_past_the_ceiling_reports_infinite(self):
        e = RpnEngine()
        for value in (1.5e308, 1.5e308):
            e.stack.clear()
            e.stack.push(value)
            e.press("sum_plus")
        e.stack.clear()
        e.press("sigma_sum")
        assert e.error == "Infinite Result"
        assert e.stack.depth == 0
        # The median of the same sample is one of its own points, so it
        # stands - _median falls back to halving each middle when their sum
        # would overflow.
        e.press("median")
        assert e.stack.peek(1) == pytest.approx(1.5e308)
        assert e.error is None

    def test_the_median_of_two_smallest_denormals_does_not_vanish(self):
        """The other end of the range, and why the fallback is conditional.

        `a/2 + b/2` underflows to 0.0 here; the answer is the number itself.
        """
        e = RpnEngine()
        for _ in range(2):
            e.stack.clear()
            e.stack.push(5e-324)
            e.press("sum_plus")
        e.stack.clear()
        e.press("median")
        assert e.stack.peek(1) == 5e-324

    def test_median_and_stddev_without_data_error(self):
        for command in ("median", "stddev"):
            e = RpnEngine()
            e.press(command)
            assert e.error == "Statistics Error", command
            assert e.stack.depth == 0

    def test_sigma_minus_takes_a_point_back_out(self):
        e = accumulate(RpnEngine(), [10, 20, 999, 30])
        e.press("clear")
        for char in "999":
            e.press(char)
        e.press("sigma_minus")
        assert e.stack.peek(1) == 3.0  # n came back down
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(60.0)

    def test_sigma_minus_refuses_a_point_never_entered(self):
        """A 12C would subtract it anyway and quietly corrupt the totals."""
        e = accumulate(RpnEngine(), [10, 20])
        e.press("clear")
        for char in "77":
            e.press(char)
        e.press("sigma_minus")
        assert e.error == "Statistics Error"
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(30.0)  # totals untouched

    def test_sigma_minus_matches_the_pair_not_just_x(self):
        e = RpnEngine()
        for y, x in ((10, 1), (99, 1)):
            e.stack.clear()
            e.stack.push(float(y))
            e.stack.push(float(x))
            e.press("sum_plus")
        e.stack.clear()
        e.stack.push(99.0)
        e.stack.push(1.0)
        e.press("sigma_minus")          # removes (1, 99), not (1, 10)
        e.stack.clear()
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(1.0)   # Σx
        assert e.stack.peek(2) == pytest.approx(10.0)  # Σy - the 10 survived

    def test_sigma_minus_on_an_empty_stack_errors(self):
        e = RpnEngine()
        e.press("sigma_minus")
        assert e.error == "Too Few Arguments"

    def test_undo_takes_a_sigma_minus_back(self):
        e = accumulate(RpnEngine(), [4, 6])
        e.press("clear")
        for char in "6":
            e.press(char)
        e.press("sigma_minus")
        e.press("undo")
        e.press("clear")
        e.press("sigma_sum")
        assert e.stack.peek(1) == pytest.approx(10.0)

    def test_mean_without_any_data_errors(self):
        e = RpnEngine()
        e.press("mean")
        assert e.error == "Statistics Error"
        assert e.stack.depth == 0

    def test_clear_sigma_forgets_the_pairs_but_not_the_stack(self):
        e = RpnEngine()
        for k in ("5", "enter", "9", "sum_plus"):
            e.press(k)
        e.press("clear_sigma")
        assert e.stack.to_list() == [1.0, 5.0]  # untouched
        e.press("mean")
        assert e.error == "Statistics Error"

    def test_undo_takes_a_sum_plus_back_whole(self):
        e = RpnEngine()
        for k in ("8", "enter", "3", "sum_plus"):
            e.press(k)
        e.press("undo")
        # The snapshot predates the implicit ENTER, so the typed 3 goes back
        # with the Σ+ - one user action, one UNDO, as every other command.
        assert e.stack.to_list() == [8.0]
        e.press("mean")
        assert e.error == "Statistics Error"  # the pair went back too

    def test_an_unrelated_command_does_not_strand_the_accumulator(self):
        """The reason every UNDO snapshot carries the Σ registers with it.

        Undoing a later, unrelated command used to restore the stack while
        rolling the totals back to whatever they were before the Σ+ - wiping
        a pair the user never asked to undo.
        """
        e = RpnEngine()
        for k in ("2", "enter", "3", "sum_plus"):
            e.press(k)
        for k in ("5", "enter"):
            e.press(k)
        e.press("undo")
        e.press("mean")
        assert e.error is None
        assert e.stack.peek(1) == pytest.approx(3.0)  # the pair survived
