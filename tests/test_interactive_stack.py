"""The 50g's interactive stack: a cursor walking the levels, with a soft menu
acting on whichever one it sits on.

Behaviour here was read off a recording of the real calculator rather than from
memory - in particular that PICK leaves the cursor on the same level *number*
while the objects shift up underneath it.
"""

from __future__ import annotations

import pytest

from rpncalc.rpn_engine import INTERACTIVE_MENU, RpnEngine


def press(engine: RpnEngine, keys: str) -> None:
    for key in keys.split():
        engine.press(key)


@pytest.fixture
def engine():
    """A stack of 4:10  3:10  2:20  1:30, the one built in the recording."""
    e = RpnEngine()
    press(e, "1 0 enter 1 0 enter 2 0 enter 3 0 enter")
    assert e.stack_lines() == ["30", "20", "10", "10"]
    return e


class TestOpeningAndClosing:
    def test_up_opens_the_browser_on_level_one(self, engine):
        assert engine.cursor_level is None
        engine.press("up")
        assert engine.cursor_level == 1

    def test_up_walks_the_cursor_into_the_stack(self, engine):
        press(engine, "up up up")
        assert engine.cursor_level == 3

    def test_the_cursor_stops_at_the_deepest_level(self, engine):
        press(engine, "up up up up up up up up")
        assert engine.cursor_level == engine.depth == 4

    def test_down_from_level_one_leaves_the_browser(self, engine):
        press(engine, "up up")
        assert engine.cursor_level == 2
        engine.press("down")
        assert engine.cursor_level == 1
        engine.press("down")
        assert engine.cursor_level is None

    def test_enter_leaves_the_browser(self, engine):
        press(engine, "up up enter")
        assert engine.cursor_level is None
        assert engine.stack_lines() == ["30", "20", "10", "10"]  # untouched

    def test_an_empty_stack_has_nothing_to_browse(self):
        e = RpnEngine()
        e.press("up")
        assert e.cursor_level is None

    def test_left_and_right_jump_to_the_ends(self, engine):
        engine.press("up")
        engine.press("right")
        assert engine.cursor_level == 4
        engine.press("left")
        assert engine.cursor_level == 1


class TestMenu:
    def test_the_menu_shows_only_while_browsing(self, engine):
        assert engine.menu_labels() == []
        engine.press("up")
        assert engine.menu_labels() == list(INTERACTIVE_MENU)
        engine.press("enter")
        assert engine.menu_labels() == []

    def test_view_is_declared_unimplemented(self, engine):
        engine.press("up")
        enabled = engine.menu_enabled()
        assert enabled == [True, False, True, True, True, True]
        assert INTERACTIVE_MENU[1] == "VIEW"

    def test_press_menu_runs_the_labelled_command(self, engine):
        press(engine, "up up up up")  # cursor on level 4
        engine.press_menu(3)  # PICK
        assert engine.stack_lines() == ["10", "30", "20", "10", "10"]

    def test_press_menu_ignores_an_unimplemented_slot(self, engine):
        press(engine, "up up")
        before = engine.stack_lines()
        engine.press_menu(1)  # VIEW
        assert engine.stack_lines() == before

    @pytest.mark.parametrize("index", [-1, 6, 99])
    def test_press_menu_ignores_a_bad_index(self, engine, index):
        engine.press("up")
        before = engine.stack_lines()
        engine.press_menu(index)
        assert engine.stack_lines() == before

    def test_menu_keys_do_nothing_while_the_browser_is_closed(self, engine):
        before = engine.stack_lines()
        for command in ("ist_pick", "ist_roll", "ist_rolld", "ist_echo", "ist_edit"):
            engine.press(command)
        assert engine.stack_lines() == before
        assert engine.cursor_level is None


class TestPick:
    def test_copies_the_selected_level_to_level_one(self, engine):
        press(engine, "up up up up")  # level 4, holding 10
        engine.press("ist_pick")
        assert engine.stack_lines() == ["10", "30", "20", "10", "10"]

    def test_leaves_the_cursor_on_the_same_level_number(self, engine):
        press(engine, "up up up up")
        engine.press("ist_pick")
        # The objects shifted up underneath it; the pointer did not chase them.
        assert engine.cursor_level == 4

    def test_grows_the_stack_by_one(self, engine):
        press(engine, "up up")
        before = engine.depth
        engine.press("ist_pick")
        assert engine.depth == before + 1


class TestRoll:
    def test_moves_the_selected_level_to_level_one(self, engine):
        press(engine, "up up up")  # level 3, holding 10
        engine.press("ist_roll")
        assert engine.stack_lines() == ["10", "30", "20", "10"]

    def test_keeps_the_depth(self, engine):
        press(engine, "up up up")
        engine.press("ist_roll")
        assert engine.depth == 4

    def test_rolld_sends_level_one_down_to_the_cursor(self, engine):
        press(engine, "up up up")  # level 3
        engine.press("ist_rolld")
        assert engine.stack_lines() == ["20", "10", "30", "10"]

    def test_roll_and_rolld_undo_each_other(self, engine):
        before = engine.stack_lines()
        press(engine, "up up up")
        engine.press("ist_roll")
        engine.press("ist_rolld")
        assert engine.stack_lines() == before


class TestEchoAndEdit:
    def test_echo_copies_the_value_into_the_command_line(self, engine):
        press(engine, "up up up")  # level 3, holding 10
        engine.press("ist_echo")
        assert engine.command_line == "10"
        assert engine.stack_lines() == ["30", "20", "10", "10"]  # stack untouched

    def test_echo_appends_to_an_open_command_line(self, engine):
        press(engine, "up up up ist_echo")
        engine.press("down")
        engine.press("down")
        engine.press("ist_echo")
        assert engine.command_line == "10 30"

    def test_echoed_values_enter_as_separate_numbers(self, engine):
        press(engine, "up up up ist_echo")
        engine.press("enter")  # leaves the browser
        engine.press("enter")  # commits the command line
        assert engine.stack_lines() == ["10", "30", "20", "10", "10"]

    def test_edit_lifts_the_level_off_the_stack(self, engine):
        press(engine, "up up up")  # level 3, holding 10
        engine.press("ist_edit")
        assert engine.command_line == "10"
        assert engine.stack_lines() == ["30", "20", "10"]
        assert engine.cursor_level is None


class TestDrop:
    def test_backspace_drops_the_selected_level(self, engine):
        press(engine, "up up up")  # level 3
        engine.press("backspace")
        assert engine.stack_lines() == ["30", "20", "10"]

    def test_the_cursor_clamps_to_the_new_depth(self, engine):
        press(engine, "up up up up")  # level 4, the deepest
        engine.press("backspace")
        assert engine.depth == 3
        assert engine.cursor_level == 3

    def test_dropping_the_last_level_closes_the_browser(self):
        e = RpnEngine()
        press(e, "7 enter up")
        assert e.cursor_level == 1
        e.press("backspace")
        assert e.depth == 0
        assert e.cursor_level is None


class TestIsolation:
    def test_arithmetic_is_ignored_while_browsing(self, engine):
        press(engine, "up up")
        before = engine.stack_lines()
        for command in ("+", "-", "*", "/", "sqrt", "5", "drop", "swap"):
            engine.press(command)
        assert engine.stack_lines() == before
        assert engine.cursor_level == 2

    def test_undo_takes_back_an_interactive_reorder(self, engine):
        before = engine.stack_lines()
        press(engine, "up up up up ist_pick enter")
        assert engine.stack_lines() != before
        engine.press("undo")
        assert engine.stack_lines() == before
