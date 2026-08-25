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
from .keymap import KEY_ROWS, Shift, ShiftState, resolve
from .numeric import ENG, FIX, SCI, STD, NumberFormat, parse_number
from .rpn_engine import DEFAULT_ANGLE_MODE, RpnEngine

_WINDOW_GEOMETRY_SETTING = "window/geometry"
_WINDOW_MAXIMIZED_SETTING = "window/maximized"

# Breathing room between the window and the edge of the screen's work area.
_SCREEN_MARGIN = 60
_RPN_MODE_SETTING = "mode/rpn"
_ANGLE_MODE_SETTING = "mode/angle"
_FORMAT_MODE_SETTING = "mode/format"
_FORMAT_DIGITS_SETTING = "mode/formatDigits"


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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = alg_engine.AlgEngine()
        self._rpn = RpnEngine()
        self._shift = ShiftState()
        self._rpn_mode = True

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
        return self._engine.expression

    def _get_display(self) -> str:
        return self._engine.display

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
        if clipboard is not None:
            clipboard.setText(
                self._rpn.copy_text() if self._rpn_mode else self._engine.display)

    @Slot()
    def pasteNumber(self) -> None:
        # Paste replaces the current entry when the clipboard holds a
        # number, tolerating surrounding whitespace, a decimal comma, and
        # the typographic minus this calculator itself puts in expressions.
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return

        value = parse_number(clipboard.text())
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
        return self._rpn.stack_lines()

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
        return self._rpn.menu_labels()

    def _get_menu_enabled(self) -> list:
        return self._rpn.menu_enabled()

    cursorLevel = Property(int, _get_cursor_level, notify=stackChanged)
    menuLabels = Property(list, _get_menu_labels, notify=stackChanged)
    menuEnabled = Property(list, _get_menu_enabled, notify=stackChanged)

    @Slot(int)
    def pressMenu(self, index: int) -> None:
        """A soft key, F1 to F6 left to right."""
        if not self._rpn_mode:
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
                    "alpha": key.alpha,
                    "style": key.style,
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
        if self._rpn_mode or key.style in ("shift_left", "shift_right"):
            return True
        # In algebraic mode only the keys omacalc's engine understands respond.
        return any(
            action in _ALG_EQUIVALENT or (action or "").isdigit()
            for action in (key.action, key.left_action, key.right_action)
            if action
        )

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
        if self._rpn_mode:
            self._rpn.press(command)
            self.stackChanged.emit()
            return

        if command in ("up", "down", "left", "right") or command.startswith("ist_"):
            return  # the stack browser has nothing to browse in algebraic mode
        key = command if command.isdigit() else _ALG_EQUIVALENT.get(command)
        if key is None:
            return
        self._engine.press(key)
        self.calculationChanged.emit()

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

    def _save_modes(self) -> None:
        settings = QSettings()
        settings.setValue(_RPN_MODE_SETTING, self._rpn_mode)
        settings.setValue(_ANGLE_MODE_SETTING, self._rpn.angle_mode)
        settings.setValue(_FORMAT_MODE_SETTING, self._rpn.number_format.mode)
        settings.setValue(_FORMAT_DIGITS_SETTING, self._rpn.number_format.digits)

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
