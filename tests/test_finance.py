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
        assert e.stack.peek(1) == 1.0
        e.press("4")
        e.press("sum_plus")  # single-argument form
        assert e.stack.peek(1) == 2.0
        e.press("drop")
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
        calls = {"n": 0}
        real = payment

        def flaky(n, i_pct, pv, fv, begin):
            calls["n"] += 1
            if calls["n"] < 3:
                raise FinanceError("Compound Interest Error")
            return real(n, i_pct, pv, fv, begin)

        monkeypatch.setattr("rpncalc.finance.payment", flaky)
        assert rate(36, 10000.0, -332.14, 0.0, False) == pytest.approx(1.0, abs=0.05)

    def test_rate_gives_up(self, monkeypatch):
        monkeypatch.setattr(
            "rpncalc.finance.payment",
            lambda *a, **k: 999999.0,
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
