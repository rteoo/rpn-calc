import pytest

from rpncalc.keymap import KEY_ROWS, KEYS_BY_ID, Shift, ShiftState, resolve


class TestGrid:
    def test_shape_matches_the_faceplate(self):
        # Nav row + seven body rows; bottom row has four caps (ENTER spans 2).
        assert len(KEY_ROWS) == 8
        assert all(len(row) == 5 for row in KEY_ROWS[:-1])
        assert len(KEY_ROWS[-1]) == 4
        assert KEYS_BY_ID["enter"].span == 2

    def test_key_ids_are_unique(self):
        ids = [k.key_id for row in KEY_ROWS for k in row]
        assert len(ids) == len(set(ids)) == 39

    def test_digits_and_core_input_are_present(self):
        for digit in "0123456789":
            assert KEYS_BY_ID[digit].action == digit
        for key_id, action in [
            ("dot", "."),
            ("enter", "enter"),
            ("backspace", "backspace"),
            ("chs", "chs"),
            ("eex", "eex"),
            ("plus", "+"),
            ("minus", "-"),
            ("multiply", "*"),
            ("divide", "/"),
        ]:
            assert KEYS_BY_ID[key_id].action == action

    def test_every_key_does_something(self):
        for key in KEYS_BY_ID.values():
            assert key.is_live(), f"{key.key_id} has no action in any plane"

    def test_the_navigation_row_leads(self):
        nav = [k.key_id for k in KEY_ROWS[0]]
        assert nav == ["menu", "up", "down", "left", "right"]

    def test_single_yellow_shift(self):
        assert "shift_left" not in KEYS_BY_ID
        assert "alpha" not in KEYS_BY_ID
        assert KEYS_BY_ID["shift"].style == "shift_right"

    def test_finance_keys_are_on_the_face(self):
        for key_id in ("n", "i", "pv", "pmt", "fv"):
            assert KEYS_BY_ID[key_id].action.startswith("fin_")
        assert KEYS_BY_ID["up"].right_action == "finance"


class TestShiftPlanes:
    @pytest.mark.parametrize(
        "key_id, shift, expected",
        [
            ("sqrt", Shift.NONE, "sqrt"),
            ("sqrt", Shift.RIGHT, "xroot"),
            ("pow", Shift.RIGHT, "exp"),
            ("eex", Shift.RIGHT, "alog"),
            ("backspace", Shift.RIGHT, "clear"),
            ("pv", Shift.NONE, "fin_pv"),
            ("pv", Shift.RIGHT, "fin_npv"),
            ("percent", Shift.RIGHT, "delta_percent"),
            ("sum", Shift.RIGHT, "fact"),
            ("sum", Shift.NONE, "sum_plus"),
            ("inv", Shift.RIGHT, "mean"),
            ("on", Shift.RIGHT, "clear_sigma"),
        ],
    )
    def test_resolves(self, key_id, shift, expected):
        state = ShiftState()
        if shift is not Shift.NONE:
            state.press_shift()
        assert resolve(key_id, state) == expected

    def test_working_shift_legends_remain(self):
        assert KEYS_BY_ID["up"].right_label == "FINANCE"
        assert KEYS_BY_ID["pow"].left_action == "exp"
        assert KEYS_BY_ID["sqrt"].left_action == "xroot"
        assert KEYS_BY_ID["eex"].right_action == "alog"
        assert KEYS_BY_ID["backspace"].right_label == "CLEAR"


class TestShiftState:
    def test_starts_unarmed(self):
        assert ShiftState().shift is Shift.NONE

    def test_arming_is_one_shot(self):
        state = ShiftState()
        resolve("shift", state)
        assert state.shift is Shift.RIGHT
        assert resolve("sqrt", state) == "xroot"
        assert state.shift is Shift.NONE
        assert resolve("sqrt", state) == "sqrt"

    def test_same_shift_twice_cancels(self):
        state = ShiftState()
        resolve("shift", state)
        resolve("shift", state)
        assert state.shift is Shift.NONE

    def test_shift_keys_never_emit_a_command(self):
        state = ShiftState()
        assert resolve("shift", state) is None

    def test_shift_is_spent_even_on_an_unbound_plane(self):
        state = ShiftState()
        resolve("shift", state)
        assert resolve("divide", state) is None  # no shifted plane on ÷
        assert state.shift is Shift.NONE

    def test_clear_disarms(self):
        state = ShiftState()
        resolve("shift", state)
        state.clear()
        assert state.shift is Shift.NONE

    def test_unknown_key_is_ignored(self):
        assert resolve("nonexistent", ShiftState()) is None


class TestKeymapEngineContract:
    """Every legend on the face must reach a command the engine implements."""

    def test_every_bound_action_is_a_real_command(self):
        from rpncalc.rpn_engine import RpnEngine

        engine = RpnEngine()
        # Clipboard and the FINANCE screen toggle live on the backend, not
        # the pure engine — the contract accepts those as resolved elsewhere.
        backend_only = {"copy", "cut", "paste", "finance", "shift"}
        bound = {
            action
            for key in KEYS_BY_ID.values()
            for action in (key.action, key.left_action, key.right_action)
            if action and action not in backend_only
        }
        unknown = sorted(a for a in bound if not engine.knows(a))
        assert unknown == [], f"keys bound to commands the engine lacks: {unknown}"


class TestNoLegendIsStranded:
    """Every shift legend on the face has to reach a live command.

    `Key.action_for` collapses the two legend slots onto one shift plane and
    prefers `right_action`, so a key that filled both slots would silently
    lose its left one. No key does today; this is what notices if one starts.
    """

    def test_no_key_carries_two_shifted_actions(self):
        for key in KEYS_BY_ID.values():
            assert not (key.left_action and key.right_action), (
                f"{key.key_id} declares both planes; one is unreachable"
            )

    def test_every_shift_legend_resolves_to_a_command(self):
        for key in KEYS_BY_ID.values():
            if not (key.left_label or key.right_label):
                continue
            assert key.action_for(Shift.RIGHT) is not None, (
                f"{key.key_id} draws a shift legend that does nothing"
            )

    def test_the_statistics_trio_is_all_on_the_face(self):
        """Σ+ is only useful with something that reads the totals back."""
        assert KEYS_BY_ID["sum"].action == "sum_plus"
        assert KEYS_BY_ID["inv"].left_action == "mean"
        assert KEYS_BY_ID["on"].right_action == "clear_sigma"
        assert KEYS_BY_ID["inv"].left_label == "MEAN"
        assert KEYS_BY_ID["on"].right_label == "CLΣ"
