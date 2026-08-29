"""The Omarchy theme reader and the system theme probe.

Neither is exercised by the calculation tests, and both contain real logic: a
hand-written parser, and a dark/light decision made from background luminance
when the theme file does not say which it is. The parser is kept because it
costs nothing on Windows - the file is simply absent - and keeps the app usable
on the Linux desktop it came from.
"""

from __future__ import annotations

import pytest

from rpncalc.backend import _DARK_THEME, _LIGHT_THEME, Backend
from rpncalc.systemtheme import SystemTheme


@pytest.fixture
def omarchy(monkeypatch, tmp_path, clean_settings):
    """Point the theme reader at a writable fake home directory."""
    theme_dir = tmp_path / ".local/state/omarchy/current/theme"
    theme_dir.mkdir(parents=True)
    monkeypatch.setattr("rpncalc.backend.Path.home", staticmethod(lambda: tmp_path))

    def write(text: str) -> Backend:
        (theme_dir / "colors.toml").write_text(text, encoding="utf-8")
        return Backend()

    write.dir = theme_dir
    write.home = tmp_path
    return write


class TestThemeFile:
    def test_colours_are_read(self, omarchy):
        backend = omarchy(
            'mode = "light"\n'
            'background = "#fefefe"\n'
            'foreground = "#101010"\n'
            'accent = "#112233"\n'
            'selection = "#445566"\n'
        )
        assert backend.themeBackground == "#fefefe"
        assert backend.themeForeground == "#101010"
        assert backend.themeAccent == "#112233"
        assert backend.themeSelection == "#445566"
        assert backend.darkMode is False

    def test_a_dark_mode_declaration_is_honoured(self, omarchy):
        # The declaration wins over what the background colour suggests.
        backend = omarchy('mode = "dark"\nbackground = "#ffffff"\n')
        assert backend.darkMode is True

    @pytest.mark.parametrize(
        "background, expect_dark",
        [
            ("#000000", True),
            ("#101010", True),
            ("#2b2b2b", True),
            ("#ffffff", False),
            ("#fefefe", False),
            ("#e8e8e8", False),
            ("#0000ff", True),
            ("#ffff00", False),
        ],
    )
    def test_mode_is_inferred_from_background_luminance(
        self, omarchy, background, expect_dark
    ):
        backend = omarchy(f'background = "{background}"\n')
        assert backend.darkMode is expect_dark

    def test_single_quotes_are_accepted(self, omarchy):
        backend = omarchy("background = '#123456'\n")
        assert backend.themeBackground == "#123456"

    def test_unquoted_values_are_accepted(self, omarchy):
        backend = omarchy("background = #123456\n")
        assert backend.themeBackground == "#123456"

    def test_comments_and_blank_lines_are_skipped(self, omarchy):
        backend = omarchy(
            "# a comment\n"
            "\n"
            "   \n"
            '   background = "#222222"   \n'
        )
        assert backend.themeBackground == "#222222"

    def test_lines_without_an_equals_sign_are_skipped(self, omarchy):
        backend = omarchy('nonsense\nbackground = "#333333"\n')
        assert backend.themeBackground == "#333333"

    def test_unknown_keys_are_ignored(self, omarchy):
        backend = omarchy('cursor = "#abcdef"\nbackground = "#444444"\n')
        assert backend.themeBackground == "#444444"

    def test_partial_files_keep_the_defaults_for_what_is_missing(self, omarchy):
        backend = omarchy('background = "#101010"\n')
        assert backend.themeBackground == "#101010"
        assert backend.themeForeground == _DARK_THEME["foreground"]
        assert backend.themeAccent == _DARK_THEME["accent"]

    def test_an_unreadable_colour_leaves_the_mode_alone(self, omarchy):
        backend = omarchy('background = "not-a-colour"\n')
        assert backend.themeBackground == "not-a-colour"
        assert isinstance(backend.darkMode, bool)

    def test_an_empty_file_falls_back_to_the_built_in_palette(self, omarchy):
        backend = omarchy("")
        assert backend.themeBackground in (
            _DARK_THEME["background"],
            _LIGHT_THEME["background"],
        )

    def test_invalid_utf8_falls_back_to_the_built_in_palette(self, omarchy):
        (omarchy.dir / "colors.toml").write_bytes(b"background = '\xff'\n")
        backend = Backend()
        expected = _DARK_THEME if backend.darkMode else _LIGHT_THEME
        assert backend.themeBackground == expected["background"]

    def test_a_read_error_falls_back_to_the_built_in_palette(
        self, omarchy, monkeypatch
    ):
        original_read_text = omarchy.dir.joinpath("colors.toml").read_text

        def fail_for_theme(path, *args, **kwargs):
            if path == omarchy.dir / "colors.toml":
                raise OSError("theme disappeared while reading")
            return original_read_text(*args, **kwargs)

        monkeypatch.setattr("rpncalc.backend.Path.read_text", fail_for_theme)
        backend = Backend()
        expected = _DARK_THEME if backend.darkMode else _LIGHT_THEME
        assert backend.themeBackground == expected["background"]


class TestNoThemeFile:
    def test_the_built_in_palette_is_used(self, monkeypatch, tmp_path, clean_settings):
        # The Windows case: no Omarchy directory at all. This must be silent.
        monkeypatch.setattr("rpncalc.backend.Path.home", staticmethod(lambda: tmp_path))
        backend = Backend()
        expected = _DARK_THEME if backend.darkMode else _LIGHT_THEME
        assert backend.themeBackground == expected["background"]
        assert backend.themeForeground == expected["foreground"]

    def test_switching_dark_mode_swaps_the_built_in_palette(
        self, monkeypatch, tmp_path, clean_settings
    ):
        monkeypatch.setattr("rpncalc.backend.Path.home", staticmethod(lambda: tmp_path))
        backend = Backend()
        backend.darkMode = True
        assert backend.themeBackground == _DARK_THEME["background"]
        backend.darkMode = False
        assert backend.themeBackground == _LIGHT_THEME["background"]


class TestThemeWatching:
    def test_an_edit_to_the_file_is_picked_up(self, omarchy):
        backend = omarchy('background = "#101010"\n')
        assert backend.themeBackground == "#101010"

        (omarchy.dir / "colors.toml").write_text(
            'background = "#fefefe"\n', encoding="utf-8"
        )
        # The watcher fires this on a real desktop; call it directly rather than
        # waiting on filesystem notifications in a test.
        backend._handle_theme_file_changed(str(omarchy.dir / "colors.toml"))
        assert backend.themeBackground == "#fefefe"
        assert backend.darkMode is False

    def test_watching_survives_a_missing_directory(
        self, monkeypatch, tmp_path, clean_settings
    ):
        monkeypatch.setattr("rpncalc.backend.Path.home", staticmethod(lambda: tmp_path))
        backend = Backend()
        backend._watch_omarchy_theme()  # nothing to watch; must not raise
        assert backend.themeBackground.startswith("#")


class TestSystemTheme:
    def test_reports_usable_values(self, qt_app):
        theme = SystemTheme()
        assert isinstance(theme.darkMode(), bool)
        assert isinstance(theme.textScale(), float)
        assert theme.textScale() > 0

    def test_refresh_is_idempotent(self, qt_app):
        theme = SystemTheme()
        before = (theme.darkMode(), theme.textScale())
        theme.refresh()
        assert (theme.darkMode(), theme.textScale()) == before

    def test_a_dark_mode_change_emits_once(self, qt_app):
        theme = SystemTheme()
        seen = []
        theme.darkModeChanged.connect(seen.append)
        theme._set_dark_mode(not theme.darkMode())
        theme._set_dark_mode(theme.darkMode())  # the same value again
        assert len(seen) == 1

    def test_a_text_scale_change_emits_once(self, qt_app):
        theme = SystemTheme()
        seen = []
        theme.textScaleChanged.connect(seen.append)
        theme._set_text_scale(theme.textScale() * 2)
        theme._set_text_scale(theme.textScale())
        assert len(seen) == 1

    def test_the_registry_reader_survives_a_missing_key(self, qt_app):
        from rpncalc.systemtheme import _read_registry_dword

        assert _read_registry_dword(r"Software\rpncalc-does-not-exist", "Nope") is None

    def test_the_registry_reader_survives_a_non_numeric_value(
        self, qt_app, monkeypatch
    ):
        import rpncalc.systemtheme as module

        class FakeWinreg:
            HKEY_CURRENT_USER = object()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def OpenKey(self, *_args):
                return self

            def QueryValueEx(self, *_args):
                return "not-a-number", 1

        monkeypatch.setattr(module, "winreg", FakeWinreg())
        assert module._read_registry_dword("key", "value") is None

    def test_falls_back_when_qt_reports_an_unknown_scheme(self, qt_app, monkeypatch):
        from PySide6.QtCore import Qt

        import rpncalc.systemtheme as module

        class UnknownHints:
            def colorScheme(self):
                return Qt.ColorScheme.Unknown

        monkeypatch.setattr(
            module.QGuiApplication, "styleHints", staticmethod(UnknownHints)
        )
        theme = SystemTheme()
        # No opinion from Qt, so it falls through to the registry or to the
        # current value - either way it must still answer with a bool.
        assert isinstance(theme._detect_dark_mode(), bool)

    def test_text_scale_is_identity_without_a_windows_dpi(self, qt_app, monkeypatch):
        import rpncalc.systemtheme as module

        monkeypatch.setattr(module, "_read_registry_dword", lambda *_: None)
        theme = SystemTheme()
        # Retina on a Mac is Qt's problem, not ours: a 2.0 devicePixelRatio
        # must not double the window.
        assert theme._detect_text_scale() == 1.0
