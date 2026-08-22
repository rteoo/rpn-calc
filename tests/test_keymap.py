import pytest

from rpncalc.keymap import KEY_ROWS, KEYS_BY_ID, Shift, ShiftState, resolve


class TestGrid:
    def test_shape_matches_the_faceplate(self):
        # Seven rows of five, per 50G.kml's y-offsets 347..582.
        assert len(KEY_ROWS) == 7
        assert all(len(row) == 5 for row in KEY_ROWS)

    def test_key_ids_are_unique(self):
        ids = [k.key_id for row in KEY_ROWS for k in row]
        assert len(ids) == len(set(ids)) == 35

    def test_digits_and_core_input_are_present(self):
        for digit in "0123456789":
            assert KEYS_BY_ID[digit].action == digit
        for key_id, action in [
            ("dot", "."),
            ("enter", "enter"),
            ("spc", "spc"),
            ("backspace", "backspace"),
            ("chs", "chs"),
            ("eex", "eex"),
            ("plus", "+"),
            ("minus", "-"),
            ("multiply", "*"),
            ("divide", "/"),
        ]:
            assert KEYS_BY_ID[key_id].action == action

    def test_dead_keys_are_declared_dead(self):
        # No CAS, no soft menus: these carry their real legend and no action.
        for key_id in ("eval", "quote", "symb", "alpha"):
            assert not KEYS_BY_ID[key_id].is_live()

    def test_every_other_key_does_something(self):
        dead = {"eval", "quote", "symb", "alpha"}
        for key in KEYS_BY_ID.values():
            if key.key_id not in dead:
                assert key.is_live(), f"{key.key_id} has no action in any plane"

    def test_shift_keys_are_styled_for_the_faceplate(self):
        assert KEYS_BY_ID["shift_left"].style == "shift_left"
        assert KEYS_BY_ID["shift_right"].style == "shift_right"
        assert KEYS_BY_ID["alpha"].style == "alpha"


class TestShiftPlanes:
    @pytest.mark.parametrize(
        "key_id, shift, expected",
        [
            ("sqrt", Shift.NONE, "sqrt"),
            ("sqrt", Shift.LEFT, "sq"),
            ("sqrt", Shift.RIGHT, "xroot"),
            ("pow", Shift.LEFT, "exp"),
            ("pow", Shift.RIGHT, "ln"),
            ("eex", Shift.LEFT, "alog"),
            ("eex", Shift.RIGHT, "log"),
            ("sin", Shift.LEFT, "asin"),
            ("cos", Shift.LEFT, "acos"),
            ("tan", Shift.LEFT, "atan"),
            ("divide", Shift.LEFT, "abs"),
            ("spc", Shift.LEFT, "pi"),
            ("backspace", Shift.LEFT, "clear_entry"),
            ("backspace", Shift.RIGHT, "clear"),
            ("hist", Shift.RIGHT, "undo"),
            ("stack", Shift.NONE, "swap"),
            ("stack", Shift.LEFT, "rot"),
            ("stack", Shift.RIGHT, "over"),
        ],
    )
    def test_resolves(self, key_id, shift, expected):
        state = ShiftState()
        if shift is not Shift.NONE:
            state.press_shift(shift)
        assert resolve(key_id, state) == expected

    def test_unbound_plane_returns_none(self):
        state = ShiftState()
        state.press_shift(Shift.RIGHT)
        assert resolve("sin", state) is None  # right-shift SIN is the CAS sigma


class TestShiftState:
    def test_starts_unarmed(self):
        assert ShiftState().shift is Shift.NONE

    def test_arming_is_one_shot(self):
        state = ShiftState()
        resolve("shift_left", state)
        assert state.shift is Shift.LEFT
        assert resolve("sqrt", state) == "sq"
        assert state.shift is Shift.NONE
        assert resolve("sqrt", state) == "sqrt"

    def test_same_shift_twice_cancels(self):
        state = ShiftState()
        resolve("shift_left", state)
        resolve("shift_left", state)
        assert state.shift is Shift.NONE

    def test_opposite_shift_switches_plane(self):
        state = ShiftState()
        resolve("shift_left", state)
        resolve("shift_right", state)
        assert state.shift is Shift.RIGHT

    def test_shift_keys_never_emit_a_command(self):
        state = ShiftState()
        assert resolve("shift_left", state) is None
        assert resolve("shift_right", state) is None

    def test_shift_is_spent_even_on_a_dead_key(self):
        # The calculator spends a shift on whatever you press next.
        state = ShiftState()
        resolve("shift_left", state)
        assert resolve("eval", state) is None
        assert state.shift is Shift.NONE

    def test_clear_disarms(self):
        state = ShiftState()
        resolve("shift_right", state)
        state.clear()
        assert state.shift is Shift.NONE

    def test_unknown_key_is_ignored(self):
        assert resolve("nonexistent", ShiftState()) is None


class TestKeymapEngineContract:
    """Every legend on the face must reach a command the engine implements.

    This is the seam where the keyboard and the engine were built separately;
    without it, a key can look live and do nothing.
    """

    def test_every_bound_action_is_a_real_command(self):
        from rpncalc.rpn_engine import RpnEngine

        engine = RpnEngine()
        bound = {
            action
            for key in KEYS_BY_ID.values()
            for action in (key.action, key.left_action, key.right_action)
            if action and action not in ("shift_left", "shift_right")
        }
        unknown = sorted(a for a in bound if not engine.knows(a))
        assert unknown == [], f"keys bound to commands the engine lacks: {unknown}"
