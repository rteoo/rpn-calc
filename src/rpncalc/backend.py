"""Qt-facing calculator backend exposed to QML as `backend`.

Direct port of omacalc's `Backend`. This is the only file in the engine
layer that imports Qt; all the math and token state live in `alg_engine.py`
so the test suite can exercise them headless (mirrors upstream's own split -
`tests.pro` compiles `backend.cpp` without `systemtheme.cpp` for the same
reason).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QPoint,
    QFileSystemWatcher,
    QObject,
    QRect,
    QSettings,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QGuiApplication

from . import alg_engine, host, launchkey
from .keymap import KEY_ROWS, ShiftState, resolve
from .numeric import ENG, FIX, SCI, STD, NumberFormat, localize_number, parse_number
from .rpn_engine import DEFAULT_ANGLE_MODE, RpnEngine

_WINDOW_GEOMETRY_SETTING = "window/geometry"
_WINDOW_MAXIMIZED_SETTING = "window/maximized"

# Breathing room between the window and the edge of the screen's work area.
_SCREEN_MARGIN = 60
_RPN_MODE_SETTING = "mode/rpn"
_ANGLE_MODE_SETTING = "mode/angle"
_FORMAT_MODE_SETTING = "mode/format"
_FORMAT_DIGITS_SETTING = "mode/formatDigits"

# The SETTINGS panel's display-precision ladder: STD, then FIX 0 to FIX 11.
# `None` is STD, which `NumberFormat` spells as a mode rather than a count.
_DIGIT_LADDER: tuple[int | None, ...] = (None, *range(12))
_DECIMAL_COMMA_SETTING = "display/decimalComma"
_THOUSANDS_SETTING = "display/thousandsSeparator"


# Keys that type into the FINANCE screen's entry line. CHS and backspace join
# them only while a line is open - see `Backend._press_finance`.
_FINANCE_ENTRY_KEYS = frozenset("0123456789") | {".", "eex"}

# RPN command ids that mean something to the algebraic engine too. The 50g uses
# one keyboard for both modes, so the keypad never changes shape - keys that
# have no algebraic meaning simply dim.
_ALG_EQUIVALENT = {
    ".": ".",
    "enter": "=",
    "backspace": "backspace",
    "clear": "clear",
    "clear_entry": "clear",
    "chs": "sign",
    "percent": "%",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
}

_LIGHT_THEME = {
    "background": "#ffffff",
    "foreground": "#222324",
    "accent": "#2077b2",
    "selection": "#2077b2",
}
_DARK_THEME = {
    "background": "#101010",
    "foreground": "#eeeeee",
    "accent": "#5584aa",
    "selection": "#186a9a",
}


class Backend(QObject):
    """QObject facade over `AlgEngine`, exposed to `Main.qml` as `backend`."""

    calculationChanged = Signal()
    stackChanged = Signal()
    modeChanged = Signal()
    shiftChanged = Signal()
    darkModeChanged = Signal()
    textScaleChanged = Signal()
    themeColorsChanged = Signal()
    calculatorKeyChanged = Signal()
    displayLocaleChanged = Signal()
    financeChanged = Signal()
    settingsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = alg_engine.AlgEngine()
        self._rpn = RpnEngine()
        self._shift = ShiftState()
        self._rpn_mode = True
        self._decimal_comma = False
        self._thousands_separator = False
        self._finance_open = False
        self._settings_open = False
        self._settings_cursor = 0

        self._dark_mode = True
        self._text_scale = 1.0
        self._theme_background = ""
        self._theme_foreground = ""
        self._theme_accent = ""
        self._theme_selection = ""

        self._theme_watcher = QFileSystemWatcher(self)
        self._theme_watcher.fileChanged.connect(self._handle_theme_file_changed)
        self._theme_watcher.directoryChanged.connect(self._handle_theme_file_changed)

        self._load_modes()
        self._load_omarchy_theme()
        self._watch_omarchy_theme()

    # -- properties -----------------------------------------------------------

    def _get_expression(self) -> str:
        return self._localize_expression(self._engine.expression)

    def _get_display(self) -> str:
        return self._localize_display(self._engine.display)

    expression = Property(str, _get_expression, notify=calculationChanged)
    display = Property(str, _get_display, notify=calculationChanged)

    def _get_dark_mode(self) -> bool:
        return self._dark_mode

    def _set_dark_mode(self, dark_mode: bool) -> None:
        if self._dark_mode == dark_mode:
            return
        self._dark_mode = dark_mode
        self._load_omarchy_theme()
        self.darkModeChanged.emit()

    darkMode = Property(bool, _get_dark_mode, _set_dark_mode, notify=darkModeChanged)

    def _get_text_scale(self) -> float:
        return self._text_scale

    def _set_text_scale(self, text_scale: float) -> None:
        if math.isclose(self._text_scale, text_scale, rel_tol=1e-9, abs_tol=1e-9):
            return
        self._text_scale = text_scale
        self.textScaleChanged.emit()

    textScale = Property(float, _get_text_scale, _set_text_scale, notify=textScaleChanged)

    def _get_theme_background(self) -> str:
        return self._theme_background

    def _get_theme_foreground(self) -> str:
        return self._theme_foreground

    def _get_theme_accent(self) -> str:
        return self._theme_accent

    def _get_theme_selection(self) -> str:
        return self._theme_selection

    themeBackground = Property(str, _get_theme_background, notify=themeColorsChanged)
    themeForeground = Property(str, _get_theme_foreground, notify=themeColorsChanged)
    themeAccent = Property(str, _get_theme_accent, notify=themeColorsChanged)
    themeSelection = Property(str, _get_theme_selection, notify=themeColorsChanged)

    def _get_is_mobile(self) -> bool:
        return host.is_mobile()

    def _get_has_pointer_hover(self) -> bool:
        return host.has_pointer_hover()

    # Constant: the host does not change while the process is running. QML
    # uses these to skip window-geometry restore and to offer a long-press
    # instead of a right-click, without the calculation core knowing.
    isMobile = Property(bool, _get_is_mobile, constant=True)
    hasPointerHover = Property(bool, _get_has_pointer_hover, constant=True)

    # -- slots ------------------------------------------------------------------

    @Slot(str)
    def pressKey(self, key: str) -> None:
        self._engine.press(key)
        self.calculationChanged.emit()

    @Slot()
    def copyResult(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return
        if self._rpn_mode:
            text = self._rpn.copy_text()
            # The command line is typed with a canonical dot; copy what is
            # on the stack the way the display shows it.
            if text and self._rpn.command_line is None:
                text = self._localize(text)
        else:
            text = self._localize_display(self._engine.display)
        clipboard.setText(text)

    @Slot()
    def pasteNumber(self) -> None:
        # Paste replaces the current entry when the clipboard holds a
        # number, tolerating surrounding whitespace, a decimal comma, thousands
        # grouping, and the typographic minus this calculator itself puts in
        # expressions.
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return

        value = parse_number(
            clipboard.text(),
            decimal=self._decimal_char(),
            thousands=self._thousands_separator,
        )
        if value is None:
            return

        # Both engines are live at once, so paste has to reach the one on
        # screen - otherwise Ctrl+V lands in an invisible buffer.
        if self._rpn_mode:
            self._rpn.paste_value(value)
            self.stackChanged.emit()
        else:
            self._engine.paste_value(value)
            self.calculationChanged.emit()

    @Slot(result="QVariantMap")
    def windowGeometry(self) -> dict:
        if not host.remembers_window_geometry():
            return {
                "valid": False,
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
                "maximized": False,
            }
        settings = QSettings()
        geometry = settings.value(_WINDOW_GEOMETRY_SETTING, QRect())
        if not isinstance(geometry, QRect):
            geometry = QRect()
        # `type=bool` is load-bearing. QSettings stores a boolean as the text
        # "true" or "false", and bool("false") is True - so without this the
        # window restored maximized for ever after being maximized once, with
        # no way back.
        maximized = settings.value(_WINDOW_MAXIMIZED_SETTING, False, type=bool)
        return {
            # Positions can legitimately be negative on monitors left of or
            # above the primary, so validity travels separately instead of
            # being encoded as -1.
            "valid": geometry.isValid(),
            "x": geometry.x(),
            "y": geometry.y(),
            "width": geometry.width(),
            "height": geometry.height(),
            "maximized": maximized,
        }

    @Slot(int, int, int, int, result="QVariantMap")
    def fitToScreen(self, x: int, y: int, width: int, height: int) -> dict:
        """Shrink a window to the work area of the screen it opens on.

        The design size grown by a large desktop text scale can be taller than
        the display - 820 at 150% is 1230, which does not fit a 1080-pixel
        screen - and a window born bigger than its screen comes up filling it,
        which reads as "it opened maximized".

        This lives here rather than in QML because QML's Screen attached
        property offers `desktopAvailableHeight`, which spans the whole virtual
        desktop. Across monitors at different offsets that is far taller than
        any one of them, so nothing ever looked too big. Only
        `QScreen.availableGeometry` knows one screen's work area.
        """
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if screen is None or width <= 0 or height <= 0:  # pragma: no cover
            return {"width": width, "height": height}

        room = screen.availableGeometry()
        # A little back from the edges, so the frame and the taskbar have room.
        usable_width = max(1, room.width() - _SCREEN_MARGIN)
        usable_height = max(1, room.height() - _SCREEN_MARGIN)

        # Both sides shrink by the same factor: scaling only the height would
        # letterbox the keypad.
        shrink = min(1.0, usable_width / width, usable_height / height)
        return {
            "width": max(1, round(width * shrink)),
            "height": max(1, round(height * shrink)),
        }

    @Slot(int, int, int, int, bool)
    def saveWindowGeometry(self, x: int, y: int, width: int, height: int, maximized: bool) -> None:
        if not host.remembers_window_geometry():
            return
        settings = QSettings()
        settings.setValue(_WINDOW_GEOMETRY_SETTING, QRect(x, y, width, height))
        settings.setValue(_WINDOW_MAXIMIZED_SETTING, maximized)

    # -- Omarchy theme (degrades gracefully when the file is absent) ----------

    # -- RPN --------------------------------------------------------------

    def _get_rpn_mode(self) -> bool:
        return self._rpn_mode

    def _set_rpn_mode(self, rpn_mode: bool) -> None:
        if self._rpn_mode == rpn_mode:
            return
        self._rpn_mode = rpn_mode
        self._rpn.cursor_level = None
        self._shift.clear()
        self._save_modes()
        self.modeChanged.emit()
        self.shiftChanged.emit()
        self.stackChanged.emit()
        self.calculationChanged.emit()

    rpnMode = Property(bool, _get_rpn_mode, _set_rpn_mode, notify=modeChanged)

    def _get_stack_lines(self) -> list:
        return [self._localize(line) for line in self._rpn.stack_lines()]

    def _get_command_line(self) -> str:
        return self._rpn.command_line or ""

    def _get_entering(self) -> bool:
        return self._rpn.command_line is not None

    def _get_error_text(self) -> str:
        return self._rpn.error or ""

    stackLines = Property(list, _get_stack_lines, notify=stackChanged)
    commandLine = Property(str, _get_command_line, notify=stackChanged)
    entering = Property(bool, _get_entering, notify=stackChanged)
    errorText = Property(str, _get_error_text, notify=stackChanged)

    def _get_cursor_level(self) -> int:
        """The interactive stack cursor, or 0 when the browser is closed."""
        return self._rpn.cursor_level or 0

    def _get_menu_labels(self) -> list:
        if self._settings_open:
            return ["TOGGLE", "", "DONE"]
        if self._finance_open:
            # Three keys, as on the 50g FINANCE soft menu — empty F4–F6
            # slots used to draw blank caps over the overflowing form.
            return ["EDIT", "AMOR", "SOLVE"]
        return self._rpn.menu_labels()

    def _get_menu_enabled(self) -> list:
        if self._settings_open:
            return [True, False, True]
        if self._finance_open:
            return [True, False, True]
        return self._rpn.menu_enabled()

    cursorLevel = Property(int, _get_cursor_level, notify=stackChanged)
    menuLabels = Property(list, _get_menu_labels, notify=stackChanged)
    menuEnabled = Property(list, _get_menu_enabled, notify=stackChanged)

    @Slot(int)
    def pressMenu(self, index: int) -> None:
        """A soft key, F1 to F6 left to right."""
        if self._settings_open:
            if index == 0:
                self._toggle_settings_item()
            elif index == 2:
                self._settings_open = False
                self.settingsChanged.emit()
                self.stackChanged.emit()
            return
        if not self._rpn_mode:
            return
        if self._finance_open:
            self._rpn.finance_menu(index)
            self.stackChanged.emit()
            self.financeChanged.emit()
            return
        self._rpn.press_menu(index)
        self.stackChanged.emit()

    def _get_angle_mode(self) -> str:
        return self._rpn.angle_mode

    def _get_number_format_label(self) -> str:
        return self._rpn.number_format.label()

    angleMode = Property(str, _get_angle_mode, notify=modeChanged)
    numberFormatLabel = Property(str, _get_number_format_label, notify=modeChanged)

    def _get_shift_state(self) -> str:
        return self._shift.shift.value

    shiftState = Property(str, _get_shift_state, notify=shiftChanged)

    def _get_key_rows(self) -> list:
        """The faceplate as a model for QML: rows of keys, each with its planes."""
        rows = []
        for row in KEY_ROWS:
            cells = []
            for key in row:
                cells.append({
                    "keyId": key.key_id,
                    "label": key.label,
                    "labelLeft": key.left_label,
                    "labelRight": key.right_label,
                    "style": key.style,
                    "span": key.span,
                    "live": self._key_is_live(key),
                    # iA Writer Mono has no arrow glyphs, so these caps are
                    # drawn rather than typeset.
                    "icon": (
                        "backspace" if key.key_id == "backspace"
                        else key.key_id if key.key_id in ("up", "down", "left", "right")
                        else ""
                    ),
                })
            rows.append(cells)
        return rows

    keyRows = Property(list, _get_key_rows, notify=modeChanged)

    def _key_is_live(self, key) -> bool:
        if not key.is_live():
            return False
        if self._rpn_mode or key.style == "shift_right":
            return True
        # In algebraic mode only the keys omacalc's engine understands respond.
        return any(
            action in _ALG_EQUIVALENT or (action or "").isdigit()
            for action in (key.action, key.left_action, key.right_action)
            if action
        )

    def _get_finance_open(self) -> bool:
        return self._finance_open

    financeOpen = Property(bool, _get_finance_open, notify=financeChanged)

    def _finance_field_lines(self) -> list:
        """Register lines for the 50g-style FINANCE screen."""
        fin = self._rpn.finance
        fmt = self._rpn.number_format
        from .numeric import format_number

        def show(value: float) -> str:
            return self._localize(format_number(value, fmt))

        begin_end = "Begin" if fin.begin else "End"
        return [
            {"id": "n", "label": "N:", "value": show(fin.n)},
            {"id": "i_yr", "label": "I%YR:", "value": show(fin.i_yr)},
            {"id": "pv", "label": "PV:", "value": show(fin.pv)},
            {"id": "pmt", "label": "PMT:", "value": show(fin.pmt)},
            {"id": "fv", "label": "FV:", "value": show(fin.fv)},
            {"id": "pyr", "label": "P/YR:", "value": show(fin.pyr)},
            {"id": "begin", "label": begin_end, "value": ""},
        ]

    financeFields = Property(list, _finance_field_lines, notify=financeChanged)

    def _get_finance_cursor(self) -> int:
        return self._rpn.finance_cursor

    financeCursor = Property(int, _get_finance_cursor, notify=financeChanged)

    def _get_settings_open(self) -> bool:
        return self._settings_open

    settingsOpen = Property(bool, _get_settings_open, notify=settingsChanged)

    def _get_settings_cursor(self) -> int:
        return self._settings_cursor

    settingsCursor = Property(int, _get_settings_cursor, notify=settingsChanged)

    def _settings_rows(self) -> list:
        return [
            {
                "id": "decimal",
                "kind": "toggle",
                "label": "Use comma as decimal",
                "checked": self._decimal_comma,
                "value": "",
                "enabled": True,
            },
            {
                "id": "thousands",
                "kind": "toggle",
                "label": "Thousands separator",
                "checked": self._thousands_separator,
                "value": "",
                "enabled": True,
            },
            {
                "id": "digits",
                # Not a checkbox: it walks a ladder of settings rather than
                # having two states. ENTER steps it forward, ◀ and ▶ either way.
                "kind": "value",
                "label": "Decimal digits",
                "checked": False,
                # The status bar's own words, so the panel and the bar cannot
                # disagree about what the display is doing.
                "value": self._rpn.number_format.label(),
                "enabled": True,
            },
            {
                "id": "launchkey",
                "kind": "toggle",
                "label": "Launch on the calculator key",
                "checked": launchkey.is_bound(),
                "value": "",
                "enabled": launchkey.supported(),
            },
        ]

    settingsRows = Property(list, _settings_rows, notify=settingsChanged)

    @Slot(str)
    def pressKeyId(self, key_id: str) -> None:
        """A press on a physical keycap, resolved through the shift planes."""
        command = resolve(key_id, self._shift)
        self.shiftChanged.emit()
        if command is not None:
            self.pressCommand(command)

    @Slot(str)
    def pressCommand(self, command: str) -> None:
        """A resolved command, from the keypad or the physical keyboard."""
        if command == "settings":
            self._toggle_settings()
            return
        if self._settings_open:
            self._press_settings(command)
            return
        if command == "finance":
            self._toggle_finance()
            return
        if self._finance_open and self._rpn_mode:
            self._press_finance(command)
            return
        if command == "toggle_mode":
            self.toggleEntryMode()
            return
        if command in ("copy", "cut", "paste"):
            self._handle_clipboard(command)
            return

        if self._rpn_mode:
            self._rpn.press(command)
            self.stackChanged.emit()
            self.financeChanged.emit()
            return

        if command in ("up", "down", "left", "right") or command.startswith("ist_"):
            return  # the stack browser has nothing to browse in algebraic mode
        if command.startswith("fin_") or command in (
            "e", "fact", "sum_plus", "sigma_minus", "mean", "sigma_sum",
            "median", "stddev", "clear_sigma", "delta_percent", "finance", "settings",
        ):
            return
        key = command if command.isdigit() else _ALG_EQUIVALENT.get(command)
        if key is None:
            return
        self._engine.press(key)
        self.calculationChanged.emit()

    def _press_finance(self, command: str) -> None:
        """The FINANCE screen owns the keyboard while it is showing.

        It hides the stack, so anything it does not answer is swallowed rather
        than allowed through - a key that quietly rearranged the stack behind
        the form is the same mistake the interactive stack browser already
        refuses to make. Entry keys go to the ordinary command line, which the
        form draws, and ENTER stores it into the selected register.
        """
        rpn = self._rpn
        if command in ("up", "down"):
            rpn.finance_move(command)
        elif command in _FINANCE_ENTRY_KEYS:
            rpn.press(command)
        elif command in ("chs", "backspace") and rpn.command_line is not None:
            # Only while something is being typed: on an empty command line
            # these are NEG and DROP, which would reach behind the form.
            rpn.press(command)
        elif command == "enter":
            rpn.commit_finance_entry()
        elif command == "clear":
            # Shift-← empties the registers, as it empties the stack outside
            # the form. Nothing else on the face clears the TVM problem.
            rpn.clear_finance()
        elif command == "clear_entry":
            if rpn.command_line is None:
                self._finance_open = False
            else:
                rpn.command_line = None  # ON cancels the entry before the form
        else:
            return
        self.financeChanged.emit()
        self.stackChanged.emit()

    def _toggle_finance(self) -> None:
        if not self._rpn_mode:
            return
        self._settings_open = False
        self._finance_open = not self._finance_open
        if self._finance_open:
            self._rpn.cursor_level = None  # finance owns the display
        self.financeChanged.emit()
        self.settingsChanged.emit()
        self.stackChanged.emit()

    def _toggle_settings(self) -> None:
        self._settings_open = not self._settings_open
        if self._settings_open:
            self._finance_open = False
            self._rpn.cursor_level = None
            self._settings_cursor = 0
        self.settingsChanged.emit()
        self.financeChanged.emit()
        self.stackChanged.emit()

    def _press_settings(self, command: str) -> None:
        """SETTINGS owns the keyboard while it is showing."""
        n = len(self._settings_rows())
        if command == "up":
            self._settings_cursor = (self._settings_cursor - 1) % n
        elif command == "down":
            self._settings_cursor = (self._settings_cursor + 1) % n
        elif command == "enter":
            self._toggle_settings_item()
            return
        elif command in ("left", "right"):
            rows = self._settings_rows()
            row = rows[self._settings_cursor]
            if row["kind"] != "value" or not row["enabled"]:
                return  # nothing to step; a toggle needs ENTER
            self._step_digits(1 if command == "right" else -1)
        elif command in ("clear_entry", "settings"):
            self._settings_open = False
        else:
            return
        self.settingsChanged.emit()
        self.stackChanged.emit()

    def _toggle_settings_item(self) -> None:
        rows = self._settings_rows()
        if not 0 <= self._settings_cursor < len(rows):
            return
        row = rows[self._settings_cursor]
        if not row["enabled"]:
            return
        if row["id"] == "decimal":
            self.setDecimalComma(not self._decimal_comma)
        elif row["id"] == "thousands":
            self.setThousandsSeparator(not self._thousands_separator)
        elif row["id"] == "digits":
            self._step_digits(1)
        elif row["id"] == "launchkey":
            self.setCalculatorKeyBound(not launchkey.is_bound())
        self.settingsChanged.emit()

    def _step_digits(self, delta: int) -> None:
        """Walk the display-precision ladder: STD, then FIX 0 through FIX 11.

        STD is one end of the same ladder rather than a separate mode, because
        "as many decimals as it takes" is the answer to the same question the
        other twelve settings answer. SCI and ENG are not on it - nothing on
        the face reaches them - so stepping from one lands in FIX.
        """
        fmt = self._rpn.number_format
        rungs = len(_DIGIT_LADDER)
        index = 0 if fmt.mode == STD else _DIGIT_LADDER.index(fmt.digits)
        digits = _DIGIT_LADDER[(index + delta) % rungs]
        if digits is None:
            self.setNumberFormat(STD, fmt.digits)
        else:
            self.setNumberFormat(FIX, digits)

    @Slot(int)
    def activateSettingsRow(self, index: int) -> None:
        """A tap on a settings row selects it and toggles."""
        if not self._settings_open:
            return
        self._settings_cursor = index
        self._toggle_settings_item()
        self.settingsChanged.emit()
        self.stackChanged.emit()

    def _handle_clipboard(self, command: str) -> None:
        if command == "paste":
            self.pasteNumber()
            return
        self.copyResult()
        if command == "cut" and self._rpn_mode:
            self._rpn.press("drop")
            self.stackChanged.emit()

    @Slot()
    def toggleEntryMode(self) -> None:
        self._set_rpn_mode(not self._rpn_mode)

    @Slot(str)
    def setAngleMode(self, mode: str) -> None:
        self._rpn.set_angle_mode(mode)
        self._save_modes()
        self.modeChanged.emit()
        self.stackChanged.emit()

    @Slot(str, int)
    def setNumberFormat(self, mode: str, digits: int) -> None:
        self._rpn.set_number_format(NumberFormat(mode, digits))
        self._save_modes()
        self.modeChanged.emit()
        self.stackChanged.emit()

    def _get_decimal_comma(self) -> bool:
        return self._decimal_comma

    def _get_thousands_separator(self) -> bool:
        return self._thousands_separator

    decimalComma = Property(bool, _get_decimal_comma, notify=displayLocaleChanged)
    thousandsSeparator = Property(
        bool, _get_thousands_separator, notify=displayLocaleChanged)

    @Slot(bool)
    def setDecimalComma(self, enabled: bool) -> None:
        if self._decimal_comma == enabled:
            return
        self._decimal_comma = enabled
        self._display_locale_changed()

    @Slot(bool)
    def setThousandsSeparator(self, enabled: bool) -> None:
        if self._thousands_separator == enabled:
            return
        self._thousands_separator = enabled
        self._display_locale_changed()

    def _display_locale_changed(self) -> None:
        self._save_modes()
        self.displayLocaleChanged.emit()
        self.stackChanged.emit()
        self.calculationChanged.emit()

    def _decimal_char(self) -> str:
        return "," if self._decimal_comma else "."

    def _localize(self, text: str) -> str:
        return localize_number(
            text, decimal=self._decimal_char(), thousands=self._thousands_separator
        )

    def _localize_display(self, text: str) -> str:
        if text == "Error":
            return text
        return self._localize(text)

    def _localize_expression(self, text: str) -> str:
        if not text:
            return text
        return " ".join(
            self._localize(token) if any(char.isdigit() for char in token) else token
            for token in text.split(" ")
        )

    # -- the keyboard's dedicated calculator key ------------------------------

    def _get_calculator_key_supported(self) -> bool:
        return launchkey.supported()

    def _get_calculator_key_bound(self) -> bool:
        return launchkey.is_bound()

    # Read straight from the registry rather than cached: the binding is shared
    # desktop state that another install - or the user with regedit - can change
    # while this window is open.
    calculatorKeySupported = Property(bool, _get_calculator_key_supported, constant=True)
    calculatorKeyBound = Property(
        bool, _get_calculator_key_bound, notify=calculatorKeyChanged)

    @Slot(bool)
    def setCalculatorKeyBound(self, bound: bool) -> None:
        """Bind or release the calculator key, reporting a refusal rather than
        dying of it - a settings toggle must not be able to close the app."""
        try:
            if bound:
                launchkey.bind()
            else:
                launchkey.unbind()
        except OSError as error:
            print(f"could not rebind the calculator key: {error}", file=sys.stderr)
        # Emitted either way: on failure the property re-reads as whatever the
        # registry still holds, so the toggle snaps back instead of lying.
        self.calculatorKeyChanged.emit()

    def _load_modes(self) -> None:
        settings = QSettings()
        self._rpn_mode = settings.value(_RPN_MODE_SETTING, True, type=bool)
        angle = settings.value(_ANGLE_MODE_SETTING, DEFAULT_ANGLE_MODE, type=str)
        mode = settings.value(_FORMAT_MODE_SETTING, STD, type=str)
        digits = settings.value(_FORMAT_DIGITS_SETTING, 3, type=int)
        # Settings are user-editable text, so a bad value must not stop the app
        # from starting. Fall back to this module's declared default rather than
        # to whatever the engine happened to be constructed with - otherwise a
        # corrupt setting and a missing one produce different modes.
        try:
            self._rpn.set_angle_mode(angle)
        except ValueError:
            self._rpn.set_angle_mode(DEFAULT_ANGLE_MODE)
        try:
            self._rpn.set_number_format(NumberFormat(mode, digits))
        except ValueError:
            self._rpn.set_number_format(NumberFormat())
        self._decimal_comma = settings.value(_DECIMAL_COMMA_SETTING, False, type=bool)
        self._thousands_separator = settings.value(_THOUSANDS_SETTING, False, type=bool)

    def _save_modes(self) -> None:
        settings = QSettings()
        settings.setValue(_RPN_MODE_SETTING, self._rpn_mode)
        settings.setValue(_ANGLE_MODE_SETTING, self._rpn.angle_mode)
        settings.setValue(_FORMAT_MODE_SETTING, self._rpn.number_format.mode)
        settings.setValue(_FORMAT_DIGITS_SETTING, self._rpn.number_format.digits)
        settings.setValue(_DECIMAL_COMMA_SETTING, self._decimal_comma)
        settings.setValue(_THOUSANDS_SETTING, self._thousands_separator)

    def _load_omarchy_theme(self) -> None:
        defaults = _DARK_THEME if self._dark_mode else _LIGHT_THEME
        self._theme_background = defaults["background"]
        self._theme_foreground = defaults["foreground"]
        self._theme_accent = defaults["accent"]
        self._theme_selection = defaults["selection"]

        colors_path = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
        theme_mode = ""
        if colors_path.is_file():
            for raw_line in colors_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                equals = line.find("=")
                if equals < 0:
                    continue
                key = line[:equals].strip()
                value = line[equals + 1 :].strip()
                if len(value) >= 2 and (
                    (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")
                ):
                    value = value[1:-1]

                if key == "mode":
                    theme_mode = value
                elif key == "background":
                    self._theme_background = value
                elif key == "foreground":
                    self._theme_foreground = value
                elif key == "accent":
                    self._theme_accent = value
                elif key == "selection":
                    self._theme_selection = value

        theme_mode_known = False
        theme_is_dark = self._dark_mode
        if theme_mode == "dark":
            theme_is_dark = True
            theme_mode_known = True
        elif theme_mode == "light":
            theme_is_dark = False
            theme_mode_known = True
        else:
            background = QColor(self._theme_background)
            if background.isValid():
                luminance = (
                    0.299 * background.redF() + 0.587 * background.greenF() + 0.114 * background.blueF()
                )
                theme_is_dark = luminance < 0.5
                theme_mode_known = True

        if theme_mode_known and theme_is_dark != self._dark_mode:
            self._dark_mode = theme_is_dark
            self.darkModeChanged.emit()

        self.themeColorsChanged.emit()

    def _watch_omarchy_theme(self) -> None:
        watched = self._theme_watcher.files() + self._theme_watcher.directories()
        if watched:
            self._theme_watcher.removePaths(watched)

        current_dir = Path.home() / ".local/state/omarchy/current"
        theme_dir = current_dir / "theme"
        colors_path = theme_dir / "colors.toml"

        if current_dir.is_dir():
            self._theme_watcher.addPath(str(current_dir))
        if theme_dir.is_dir():
            self._theme_watcher.addPath(str(theme_dir))
        if colors_path.is_file():
            self._theme_watcher.addPath(str(colors_path))

    def _handle_theme_file_changed(self, _path: str) -> None:
        self._load_omarchy_theme()
        self._watch_omarchy_theme()
