"""Qt-facing calculator backend exposed to QML as `backend`.

Direct port of omacalc's `Backend`. This is the only file in the engine
layer that imports Qt; all the math and token state live in `alg_engine.py`
so the test suite can exercise them headless (mirrors upstream's own split -
`tests.pro` compiles `backend.cpp` without `systemtheme.cpp` for the same
reason).
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QFileSystemWatcher,
    QObject,
    QRect,
    QSettings,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QGuiApplication

from . import alg_engine
from .numeric import parse_number

_WINDOW_GEOMETRY_SETTING = "window/geometry"
_WINDOW_MAXIMIZED_SETTING = "window/maximized"

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
    darkModeChanged = Signal()
    textScaleChanged = Signal()
    themeColorsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = alg_engine.AlgEngine()

        self._dark_mode = True
        self._text_scale = 1.0
        self._theme_background = ""
        self._theme_foreground = ""
        self._theme_accent = ""
        self._theme_selection = ""

        self._theme_watcher = QFileSystemWatcher(self)
        self._theme_watcher.fileChanged.connect(self._handle_theme_file_changed)
        self._theme_watcher.directoryChanged.connect(self._handle_theme_file_changed)

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

    # -- slots ------------------------------------------------------------------

    @Slot(str)
    def pressKey(self, key: str) -> None:
        self._engine.press(key)
        self.calculationChanged.emit()

    @Slot()
    def copyResult(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._engine.display)

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

        self._engine.paste_value(value)
        self.calculationChanged.emit()

    @Slot(result="QVariantMap")
    def windowGeometry(self) -> dict:
        settings = QSettings()
        geometry = settings.value(_WINDOW_GEOMETRY_SETTING, QRect())
        if not isinstance(geometry, QRect):
            geometry = QRect()
        maximized = settings.value(_WINDOW_MAXIMIZED_SETTING, False)
        return {
            # Positions can legitimately be negative on monitors left of or
            # above the primary, so validity travels separately instead of
            # being encoded as -1.
            "valid": geometry.isValid(),
            "x": geometry.x(),
            "y": geometry.y(),
            "width": geometry.width(),
            "height": geometry.height(),
            "maximized": bool(maximized),
        }

    @Slot(int, int, int, int, bool)
    def saveWindowGeometry(self, x: int, y: int, width: int, height: int, maximized: bool) -> None:
        settings = QSettings()
        settings.setValue(_WINDOW_GEOMETRY_SETTING, QRect(x, y, width, height))
        settings.setValue(_WINDOW_MAXIMIZED_SETTING, maximized)

    # -- Omarchy theme (degrades gracefully when the file is absent) ----------

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
