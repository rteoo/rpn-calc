"""System dark-mode and text-scale detection.

Replaces omacalc's xdg-desktop-portal/D-Bus reader (Omarchy-specific) with a
Windows-native path, while keeping the same `SystemTheme` signal contract so
`backend.py` and `__main__.py` can wire it up exactly like the C++ original.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows platforms
    winreg = None  # type: ignore[assignment]

_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_DESKTOP_KEY = r"Control Panel\Desktop"


def _read_registry_dword(key_path: str, value_name: str) -> int | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return int(value)
    except OSError:
        return None


class SystemTheme(QObject):
    """Dark mode and text scale, refreshed from the OS."""

    darkModeChanged = Signal(bool)
    textScaleChanged = Signal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark_mode = True
        self._text_scale = 1.0

        style_hints = QGuiApplication.styleHints()
        if style_hints is not None and hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._handle_color_scheme_changed)

        self.refresh()

    def darkMode(self) -> bool:
        return self._dark_mode

    def textScale(self) -> float:
        return self._text_scale

    def refresh(self) -> None:
        self._set_dark_mode(self._detect_dark_mode())
        self._set_text_scale(self._detect_text_scale())

    # -- internals ------------------------------------------------------------

    def _handle_color_scheme_changed(self, _scheme: object) -> None:
        self._set_dark_mode(self._detect_dark_mode())

    def _detect_dark_mode(self) -> bool:
        # Qt 6.5+ reports the platform's color scheme directly; prefer it.
        style_hints = QGuiApplication.styleHints()
        if style_hints is not None:
            scheme = style_hints.colorScheme()
            # Qt.ColorScheme: Unknown = 0, Light = 1, Dark = 2.
            if int(scheme) == 2:
                return True
            if int(scheme) == 1:
                return False

        # Fall back to the registry key Windows Explorer itself reads.
        apps_use_light_theme = _read_registry_dword(_PERSONALIZE_KEY, "AppsUseLightTheme")
        if apps_use_light_theme is not None:
            return apps_use_light_theme == 0

        return self._dark_mode

    def _detect_text_scale(self) -> float:
        log_pixels = _read_registry_dword(_DESKTOP_KEY, "LogPixels")
        if log_pixels:
            return log_pixels / 96.0
        return 1.0

    def _set_dark_mode(self, dark_mode: bool) -> None:
        if self._dark_mode == dark_mode:
            return
        self._dark_mode = dark_mode
        self.darkModeChanged.emit(dark_mode)

    def _set_text_scale(self, text_scale: float) -> None:
        if abs(self._text_scale - text_scale) < 1e-9:
            return
        self._text_scale = text_scale
        self.textScaleChanged.emit(text_scale)
