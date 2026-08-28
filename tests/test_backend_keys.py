"""End-to-end tests through the Qt backend, in both entry modes.

Everything below the backend is pure Python and tested headless elsewhere.
The offscreen platform and the QSettings redirection live in `conftest.py`, so
a test run never opens a window or touches real saved state.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from rpncalc.backend import Backend  # noqa: E402
from rpncalc.numeric import FIX  # noqa: E402


@pytest.fixture
def clipboard(qt_app):
    board = QGuiApplication.clipboard()
    board.clear()
    return board


@pytest.fixture
def backend(qt_app):
    QSettings().clear()
    return Backend()


def press_ids(backend: Backend, key_ids: str) -> None:
    """Press physical keycaps, shift planes and all."""
    for key_id in key_ids.split():
        backend.pressKeyId(key_id)


def press_commands(backend: Backend, commands: str) -> None:
    for command in commands.split():
        backend.pressCommand(command)


class TestRpnMode:
    def test_starts_in_rpn(self, backend):
        assert backend.rpnMode is True
        assert backend.stackLines == []
        assert backend.entering is False

    def test_keycaps_drive_the_stack(self, backend):
        press_ids(backend, "5 enter 3 enter 2 plus multiply")
        assert backend.stackLines == ["25"]

    def test_shift_plane_reaches_a_function(self, backend):
        press_ids(backend, "2 enter")
        assert backend.shiftState == "none"
        backend.pressKeyId("shift")
        assert backend.shiftState == "right"
        backend.pressKeyId("eex")  # shift-EEX is 10^x
        assert backend.shiftState == "none"
        assert backend.stackLines == ["100"]

    def test_unshifted_root_key_is_square_root(self, backend):
        press_ids(backend, "8 1 enter sqrt")
        assert backend.stackLines == ["9"]

    def test_command_line_state_is_exposed(self, backend):
        assert backend.entering is False
        press_ids(backend, "2 dot 5")
        assert backend.entering is True
        assert backend.commandLine == "2.5"
        press_ids(backend, "enter")
        assert backend.entering is False
        assert backend.stackLines == ["2.5"]

    def test_backspace_drops_once_the_line_is_empty(self, backend):
        press_ids(backend, "7 enter 4 2")
        assert backend.commandLine == "42"
        press_ids(backend, "backspace backspace")
        assert backend.entering is False
        assert backend.stackLines == ["7"]
        press_ids(backend, "backspace")
        assert backend.stackLines == []

    def test_error_is_surfaced_and_the_stack_survives(self, backend):
        press_ids(backend, "1 enter 0 divide")
        assert backend.errorText == "Infinite Result"
        assert backend.stackLines == ["0", "1"]
        press_ids(backend, "9")
        assert backend.errorText == ""

    def test_clear_and_clear_entry_differ(self, backend):
        press_ids(backend, "6 enter 1 2")
        backend.pressKeyId("on")  # ON: cancel the entry
        assert backend.entering is False
        assert backend.stackLines == ["6"]

        backend.pressKeyId("shift")
        backend.pressKeyId("backspace")  # shift-CLEAR: empty the stack
        assert backend.stackLines == []


class TestAlgMode:
    def test_toggle_switches_and_keeps_omacalc_behaviour(self, backend):
        backend.toggleEntryMode()
        assert backend.rpnMode is False
        press_commands(backend, "4 2 * 3 + 7 enter")
        assert backend.display == "133"
        assert backend.expression == "42 × 3 + 7"

    def test_enter_acts_as_equals(self, backend):
        backend.toggleEntryMode()
        press_ids(backend, "2 plus 3 enter")
        assert backend.display == "5"

    def test_rpn_only_keys_are_inert(self, backend):
        backend.toggleEntryMode()
        press_commands(backend, "4 swap rot dup")
        assert backend.display == "4"  # ignored, not crashed

    def test_keys_without_algebraic_meaning_are_marked_dead(self, backend):
        backend.toggleEntryMode()
        live = {
            cell["keyId"]: cell["live"] for row in backend.keyRows for cell in row
        }
        assert live["7"] is True
        assert live["plus"] is True
        assert live["enter"] is True
        assert live["sqrt"] is False
        assert live["pv"] is False  # finance keys are RPN-only on this face

    def test_switching_back_preserves_the_stack(self, backend):
        press_ids(backend, "1 2 enter")
        backend.toggleEntryMode()
        backend.toggleEntryMode()
        assert backend.rpnMode is True
        assert backend.stackLines == ["12"]


class TestModePersistence:
    def test_modes_survive_a_restart(self, backend):
        backend.setAngleMode("DEG")
        backend.setNumberFormat(FIX, 2)
        backend.toggleEntryMode()

        revived = Backend()
        assert revived.angleMode == "DEG"
        assert revived.numberFormatLabel == "FIX 2"
        assert revived.rpnMode is False

    def test_display_locale_survives_a_restart(self, backend):
        backend.setDecimalComma(False)
        backend.setThousandsSeparator(False)
        backend.setDecimalComma(True)
        backend.setThousandsSeparator(True)

        revived = Backend()
        assert revived.decimalComma is True
        assert revived.thousandsSeparator is True

    def test_a_corrupt_setting_does_not_stop_startup(self, backend):
        settings = QSettings()
        settings.setValue("mode/angle", "GRADIANS-ISH")
        settings.setValue("mode/format", "HEX")
        settings.sync()

        revived = Backend()
        assert revived.angleMode == "RAD"  # falls back, does not adopt the junk
        assert revived.numberFormatLabel == "STD"


class TestDisplayFormatting:
    def test_number_format_reaches_the_stack_display(self, backend):
        press_ids(backend, "1 enter 3 divide")
        assert backend.stackLines == ["0.333333333333333"]
        backend.setNumberFormat(FIX, 2)
        assert backend.stackLines == ["0.33"]

    def test_thousands_separator_groups_the_integer_part(self, backend):
        press_commands(backend, "1 0 0 enter 1 0 0 . 0 0 1 enter")
        press_commands(backend, "1 0 0 0 0 0 enter 1 0 0 0 0 0 . 0 0 0 1 enter")
        backend.setThousandsSeparator(True)
        assert backend.stackLines == [
            "100,000.0001",
            "100,000",
            "100.001",
            "100",
        ]

    def test_a_decimal_comma_swaps_the_point(self, backend):
        press_commands(backend, "1 0 0 . 0 0 1 enter")
        backend.setDecimalComma(True)
        assert backend.stackLines == ["100,001"]

    def test_thousands_follows_the_decimal_comma(self, backend):
        press_commands(backend, "1 0 0 0 0 0 . 0 0 0 1 enter")
        backend.setDecimalComma(True)
        backend.setThousandsSeparator(True)
        assert backend.stackLines == ["100.000,0001"]

    def test_the_command_line_stays_canonical(self, backend):
        press_ids(backend, "1 0 0 0 0 0")
        backend.setThousandsSeparator(True)
        backend.setDecimalComma(True)
        assert backend.commandLine == "100000"

    def test_echo_writes_canonical_text_onto_the_command_line(self, backend):
        press_commands(backend, "1 0 0 0 0 0 enter")
        backend.setThousandsSeparator(True)
        assert backend.stackLines == ["100,000"]
        backend.pressKeyId("up")
        backend.pressMenu(0)  # ECHO
        assert backend.commandLine == "100000"

    def test_algebraic_display_follows_the_decimal_comma(self, backend):
        backend.toggleEntryMode()
        press_commands(backend, "1 / 2 enter")
        assert backend.display == "0.5"
        backend.setDecimalComma(True)
        assert backend.display == "0,5"

    def test_algebraic_entry_shows_the_decimal_comma(self, backend):
        backend.toggleEntryMode()
        press_commands(backend, "1 . 5")
        backend.setDecimalComma(True)
        assert backend.display == "1,5"

    def test_algebraic_error_is_not_grouped(self, backend):
        backend.toggleEntryMode()
        press_commands(backend, "1 / 0 enter")
        backend.setThousandsSeparator(True)
        assert backend.display == "Error"

    def test_algebraic_expression_localizes_its_numbers(self, backend):
        backend.toggleEntryMode()
        press_commands(backend, "0 . 1 + 0 . 2 enter")
        backend.setDecimalComma(True)
        assert backend.display == "0,3"
        assert backend.expression == "0,1 + 0,2"

    def test_angle_mode_reaches_trigonometry(self, backend):
        backend.setAngleMode("DEG")
        # Trig is off the faceplate; drive the engine command directly.
        press_commands(backend, "9 0 enter sin")
        assert backend.stackLines == ["1"]


class TestSystemTheme:
    """`SystemTheme` is constructed only by `__main__`, so nothing else here
    would catch it crashing on a real desktop - which it did, coercing Qt's
    ColorScheme enum with int()."""

    def test_reports_usable_values(self, qt_app):
        from rpncalc.systemtheme import SystemTheme

        theme = SystemTheme()
        assert isinstance(theme.darkMode(), bool)
        assert isinstance(theme.textScale(), float)
        assert theme.textScale() > 0

    def test_refresh_is_idempotent(self, qt_app):
        from rpncalc.systemtheme import SystemTheme

        theme = SystemTheme()
        before = (theme.darkMode(), theme.textScale())
        theme.refresh()
        assert (theme.darkMode(), theme.textScale()) == before

    def test_drives_the_backend_dark_mode(self, qt_app):
        from rpncalc.systemtheme import SystemTheme

        theme = SystemTheme()
        backend = Backend()
        backend.darkMode = theme.darkMode()
        assert backend.darkMode == theme.darkMode()
        assert backend.themeBackground.startswith("#")


class TestClipboard:
    """Both engines are live at once, so the clipboard has to reach the one
    actually on screen. It used to always reach the algebraic one, which meant
    copy and paste silently did nothing in RPN - the default mode."""

    def test_copy_takes_level_one_in_rpn(self, backend, clipboard):
        press_ids(backend, "4 2 enter")
        backend.copyResult()
        assert clipboard.text() == "42"

    def test_copy_takes_the_grouped_display(self, backend, clipboard):
        press_commands(backend, "1 0 0 0 0 0 enter")
        backend.setThousandsSeparator(True)
        backend.copyResult()
        assert clipboard.text() == "100,000"

    def test_copy_takes_the_open_command_line(self, backend, clipboard):
        press_ids(backend, "1 enter 3 dot 5")
        backend.copyResult()
        assert clipboard.text() == "3.5"

    def test_copy_of_the_command_line_stays_canonical(self, backend, clipboard):
        press_ids(backend, "1 0 0 0 0 0")
        backend.setThousandsSeparator(True)
        backend.copyResult()
        assert clipboard.text() == "100000"

    def test_paste_pushes_onto_the_stack_in_rpn(self, backend, clipboard):
        press_ids(backend, "7 enter")
        clipboard.setText(" 2,5 ")
        backend.pasteNumber()
        assert backend.stackLines == ["2.5", "7"]

    def test_paste_accepts_grouped_text(self, backend, clipboard):
        backend.setThousandsSeparator(True)
        clipboard.setText("100,000")
        backend.pasteNumber()
        backend.setThousandsSeparator(False)
        assert backend.stackLines == ["100000"]

    def test_paste_still_reaches_the_algebraic_entry(self, backend, clipboard):
        backend.toggleEntryMode()
        clipboard.setText("42.5")
        backend.pasteNumber()
        assert backend.display == "42.5"

    def test_copy_of_an_empty_stack_is_empty(self, backend, clipboard):
        backend.copyResult()
        assert clipboard.text() == ""

    def test_copy_takes_the_localized_algebraic_result(self, backend, clipboard):
        backend.toggleEntryMode()
        press_commands(backend, "1 / 2 enter")
        backend.setDecimalComma(True)
        backend.copyResult()
        assert clipboard.text() == "0,5"


class TestInteractiveStack:
    """The stack browser as QML sees it: a cursor level and a soft menu."""

    def build(self, backend):
        press_ids(backend, "1 0 enter 1 0 enter 2 0 enter 3 0 enter")
        assert backend.stackLines == ["30", "20", "10", "10"]

    def test_closed_by_default(self, backend):
        self.build(backend)
        assert backend.cursorLevel == 0
        assert backend.menuLabels == []

    def test_the_up_key_opens_the_browser(self, backend):
        self.build(backend)
        backend.pressKeyId("up")
        assert backend.cursorLevel == 1
        assert backend.menuLabels == ["ECHO", "VIEW", "EDIT", "PICK", "ROLL", "ROLLD"]

    def test_the_menu_key_opens_settings(self, backend):
        assert not backend.settingsOpen
        backend.pressKeyId("menu")
        assert backend.settingsOpen
        assert backend.menuLabels == ["TOGGLE", "", "DONE"]
        assert [row["label"] for row in backend.settingsRows] == [
            "Use comma as decimal",
            "Thousands separator",
            "Launch on the calculator key",
        ]
        backend.pressCommand("enter")  # toggle decimal comma
        assert backend.decimalComma is True
        backend.pressKeyId("menu")  # closes
        assert not backend.settingsOpen

    def test_the_up_key_opens_and_walks(self, backend):
        self.build(backend)
        for _ in range(3):
            backend.pressKeyId("up")
        assert backend.cursorLevel == 3

    def test_pick_from_the_soft_menu(self, backend):
        self.build(backend)
        for _ in range(4):
            backend.pressKeyId("up")
        backend.pressMenu(3)  # PICK
        assert backend.stackLines == ["10", "30", "20", "10", "10"]
        assert backend.cursorLevel == 4

    def test_roll_from_the_soft_menu(self, backend):
        self.build(backend)
        for _ in range(3):
            backend.pressKeyId("up")
        backend.pressMenu(4)  # ROLL
        assert backend.stackLines == ["10", "30", "20", "10"]

    def test_view_is_disabled(self, backend):
        self.build(backend)
        backend.pressKeyId("up")
        assert backend.menuEnabled == [True, False, True, True, True, True]
        before = backend.stackLines
        backend.pressMenu(1)
        assert backend.stackLines == before

    def test_enter_closes_the_browser(self, backend):
        self.build(backend)
        press_ids(backend, "up up enter")
        assert backend.cursorLevel == 0
        assert backend.menuLabels == []

    def test_arrows_do_nothing_in_algebraic_mode(self, backend):
        backend.toggleEntryMode()
        for key_id in ("up", "down", "left", "right"):
            backend.pressKeyId(key_id)
        assert backend.cursorLevel == 0
        assert backend.menuLabels == []
        assert backend.display == "0"
        # MENU opens settings in either mode.
        backend.pressKeyId("menu")
        assert backend.settingsOpen

    def test_switching_mode_closes_the_browser(self, backend):
        self.build(backend)
        press_ids(backend, "up up")
        assert backend.cursorLevel == 2
        backend.toggleEntryMode()
        assert backend.cursorLevel == 0
        backend.toggleEntryMode()
        # The stack survived; only the cursor was put away.
        assert backend.stackLines == ["30", "20", "10", "10"]
        assert backend.cursorLevel == 0

    def test_soft_menu_is_ignored_when_no_menu_is_showing(self, backend):
        self.build(backend)
        before = backend.stackLines
        for index in range(6):
            backend.pressMenu(index)
        assert backend.stackLines == before


class TestMobileHost:
    """iOS (and Android) have no window to remember and no calculator key."""

    def test_desktop_is_not_mobile(self, backend):
        from rpncalc import host

        assert backend.isMobile is host.is_mobile()
        assert backend.hasPointerHover is host.has_pointer_hover()

    def test_geometry_is_not_saved_or_restored(self, monkeypatch, qt_app, clean_settings):
        monkeypatch.setattr("rpncalc.backend.host.remembers_window_geometry", lambda: False)
        monkeypatch.setattr("rpncalc.backend.host.is_mobile", lambda: True)
        monkeypatch.setattr("rpncalc.backend.host.has_pointer_hover", lambda: False)
        backend = Backend()
        assert backend.isMobile is True
        assert backend.hasPointerHover is False
        assert backend.windowGeometry()["valid"] is False
        backend.saveWindowGeometry(10, 20, 400, 800, True)
        assert QSettings().value("window/geometry") is None
        assert QSettings().value("window/maximized") is None


class TestFinanceScreenOwnsTheKeyboard:
    """The FINANCE form hides the stack, so it must answer for the keyboard.

    It used to let every unhandled key through to the RPN engine: typing 360
    on the form opened an *invisible* command line, EDIT then failed with
    "Too Few Arguments", and pressing an operator quietly rearranged a stack
    nobody could see. Same rule the interactive stack browser already follows.
    """

    def open_form(self, backend):
        backend.pressCommand("finance")
        assert backend.financeOpen
        return backend

    def test_typing_shows_on_the_form_and_enter_stores_it(self, backend):
        self.open_form(backend)
        press_commands(backend, "3 6 0")
        # The form draws the command line, because the stack view is hidden.
        assert backend.commandLine == "360"
        backend.pressCommand("enter")
        assert backend.commandLine == ""
        assert backend.financeFields[0]["label"] == "N:"
        assert backend.financeFields[0]["value"] == "360"

    def test_a_full_tvm_problem_typed_into_the_form(self, backend):
        """The 12C's classic mortgage, entered the way the form intends."""
        self.open_form(backend)
        press_commands(backend, "3 6 0 enter")          # N
        backend.pressCommand("down")
        press_commands(backend, "9 enter")              # I%YR, over 12 P/YR
        backend.pressCommand("down")
        press_commands(backend, "1 0 0 0 0 0 enter")    # PV
        backend.pressCommand("down")                    # cursor on PMT
        backend.pressMenu(2)                            # SOLVE
        assert backend._rpn.stack.peek(1) == pytest.approx(-804.62, abs=0.01)

    def test_arithmetic_never_reaches_the_hidden_stack(self, backend):
        press_commands(backend, "8 enter 2")
        before = backend._rpn.stack.to_list()
        self.open_form(backend)
        for key in ("+", "-", "*", "/", "swap", "drop", "dup", "percent"):
            backend.pressCommand(key)
        assert backend._rpn.stack.to_list() == before

    def test_backspace_and_chs_do_not_reach_behind_the_form(self, backend):
        """On an empty command line these are DROP and NEG."""
        press_commands(backend, "7 enter")
        self.open_form(backend)
        backend.pressCommand("backspace")
        backend.pressCommand("chs")
        assert backend._rpn.stack.to_list() == [7.0]

    def test_backspace_and_chs_still_edit_what_is_being_typed(self, backend):
        self.open_form(backend)
        press_commands(backend, "1 2 3")
        backend.pressCommand("backspace")
        assert backend.commandLine == "12"
        backend.pressCommand("chs")
        assert backend.commandLine.startswith("-")

    def test_a_negative_value_reaches_the_register(self, backend):
        self.open_form(backend)
        backend.pressCommand("down")
        backend.pressCommand("down")
        press_commands(backend, "5 0 0 chs enter")
        assert backend.financeFields[2]["label"] == "PV:"
        assert backend._rpn.finance.pv == pytest.approx(-500.0)

    def test_cut_cannot_drop_a_level_behind_the_form(self, backend):
        press_commands(backend, "7 enter 9")
        self.open_form(backend)
        before = backend._rpn.stack.to_list()
        backend.pressCommand("cut")
        assert backend._rpn.stack.to_list() == before

    def test_on_cancels_the_entry_before_it_closes_the_form(self, backend):
        self.open_form(backend)
        press_commands(backend, "4 2")
        backend.pressCommand("clear_entry")
        assert backend.financeOpen          # the entry went, the form stayed
        assert backend.commandLine == ""
        backend.pressCommand("clear_entry")
        assert not backend.financeOpen

    def test_enter_with_nothing_typed_leaves_the_field_alone(self, backend):
        self.open_form(backend)
        press_commands(backend, "3 6 0 enter")
        backend.pressCommand("enter")   # again, with an empty entry line
        assert backend._rpn.finance.n == 360.0
        assert backend._rpn.error is None

    def test_enter_toggles_the_begin_end_row(self, backend):
        self.open_form(backend)
        for _ in range(6):
            backend.pressCommand("down")
        assert backend.financeFields[6]["label"] == "End"
        backend.pressCommand("enter")
        assert backend.financeFields[6]["label"] == "Begin"
        backend.pressCommand("enter")
        assert backend.financeFields[6]["label"] == "End"

    def test_an_unreadable_entry_is_refused_not_stored(self, backend):
        self.open_form(backend)
        backend._rpn.command_line = "1e"  # EEX left dangling
        backend.pressCommand("enter")
        assert backend._rpn.error == "Invalid Input"
        assert backend._rpn.finance.n == 0.0

    def test_zero_periods_per_year_is_refused(self, backend):
        self.open_form(backend)
        for _ in range(5):
            backend.pressCommand("down")
        assert backend.financeFields[5]["label"] == "P/YR:"
        press_commands(backend, "0 enter")
        assert backend._rpn.error == "Compound Interest Error"
        assert backend._rpn.finance.pyr == 12.0

    def test_the_arrows_walk_the_fields_and_wrap(self, backend):
        self.open_form(backend)
        assert backend.financeCursor == 0
        backend.pressCommand("up")
        assert backend.financeCursor == len(backend.financeFields) - 1
        backend.pressCommand("down")
        assert backend.financeCursor == 0

    def test_the_form_ignores_the_keyboard_in_algebraic_mode(self, backend):
        backend.toggleEntryMode()
        backend.pressCommand("finance")
        assert not backend.financeOpen
