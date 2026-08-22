"""End-to-end tests through the Qt backend, in both entry modes.

These are the only tests that need a QGuiApplication - everything below the
backend is pure Python and tested headless elsewhere. The platform is forced
offscreen and QSettings is redirected to a temporary directory so a test run
never touches the real window geometry or saved modes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from rpncalc.backend import Backend  # noqa: E402
from rpncalc.numeric import FIX  # noqa: E402


@pytest.fixture(scope="session")
def qt_app(tmp_path_factory):
    app = QGuiApplication.instance() or QGuiApplication([])
    QCoreApplication.setOrganizationName("rpncalc-tests")
    QCoreApplication.setApplicationName("suite")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path_factory.mktemp("settings")),
    )
    return app


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
        press_ids(backend, "1 6 enter")
        assert backend.shiftState == "none"
        backend.pressKeyId("shift_left")
        assert backend.shiftState == "left"
        backend.pressKeyId("sqrt")  # left-shift on the root key is x squared
        assert backend.shiftState == "none"
        assert backend.stackLines == ["256"]

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
        backend.pressKeyId("shift_left")
        backend.pressKeyId("backspace")  # left-shift DEL: cancel the entry
        assert backend.entering is False
        assert backend.stackLines == ["6"]

        backend.pressKeyId("shift_right")
        backend.pressKeyId("backspace")  # right-shift CLEAR: empty the stack
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
        assert live["stack"] is False

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

    def test_angle_mode_reaches_trigonometry(self, backend):
        backend.setAngleMode("DEG")
        press_ids(backend, "9 0 enter sin")
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

    def test_copy_takes_the_open_command_line(self, backend, clipboard):
        press_ids(backend, "1 enter 3 dot 5")
        backend.copyResult()
        assert clipboard.text() == "3.5"

    def test_paste_pushes_onto_the_stack_in_rpn(self, backend, clipboard):
        press_ids(backend, "7 enter")
        clipboard.setText(" 2,5 ")
        backend.pasteNumber()
        assert backend.stackLines == ["2.5", "7"]

    def test_paste_still_reaches_the_algebraic_entry(self, backend, clipboard):
        backend.toggleEntryMode()
        clipboard.setText("42.5")
        backend.pasteNumber()
        assert backend.display == "42.5"

    def test_copy_of_an_empty_stack_is_empty(self, backend, clipboard):
        backend.copyResult()
        assert clipboard.text() == ""


class TestInteractiveStack:
    """The stack browser as QML sees it: a cursor level and a soft menu."""

    def build(self, backend):
        press_ids(backend, "1 0 enter 1 0 enter 2 0 enter 3 0 enter")
        assert backend.stackLines == ["30", "20", "10", "10"]

    def test_closed_by_default(self, backend):
        self.build(backend)
        assert backend.cursorLevel == 0
        assert backend.menuLabels == []

    def test_the_stk_key_opens_the_browser(self, backend):
        self.build(backend)
        backend.pressKeyId("stk")
        assert backend.cursorLevel == 1
        assert backend.menuLabels == ["ECHO", "VIEW", "EDIT", "PICK", "ROLL", "ROLLD"]

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
        backend.pressKeyId("stk")
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
        for key_id in ("up", "down", "left", "right", "stk"):
            backend.pressKeyId(key_id)
        assert backend.cursorLevel == 0
        assert backend.menuLabels == []
        assert backend.display == "0"

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
