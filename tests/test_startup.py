"""The application startup path.

`main` blocks in the Qt event loop, so nothing used to exercise this file at
all - and it is where the one crash that reached a real desktop lived: Qt's
`colorScheme()` returns an enum, and coercing it with `int()` raised on launch.
Every headless test of the engine passed while the app would not open.

`start` exists to make this testable: it does everything `main` does except
enter the event loop.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon

from rpncalc import __main__ as entry
from rpncalc.__main__ import Startup, main, start


@pytest.fixture
def started(clean_settings):
    return start([])


class TestStart:
    def test_the_window_is_built(self, started):
        assert started.loaded
        assert started.window is not None
        assert started.window.property("title") == "rpn-calc"

    def test_the_window_has_a_usable_size(self, started):
        width = started.window.property("width")
        height = started.window.property("height")
        assert width >= started.window.property("minimumWidth") > 0
        assert height >= started.window.property("minimumHeight") > 0

    def test_the_window_is_visible(self, started):
        # A window that is built but never shown is the failure mode that made
        # the packaged build look like a hang.
        assert started.window.property("visible") is True

    def test_the_qml_loads_without_warnings(self, started, capsys):
        # `start` prints QML warnings; a clean load prints nothing.
        assert started.loaded
        captured = capsys.readouterr()
        assert "Main.qml" not in captured.out
        assert "Main.qml" not in captured.err

    def test_the_backend_is_wired_to_qml(self, started):
        backend = started.engine.rootContext().contextProperty("backend")
        assert backend is started.backend

    def test_the_application_identifies_itself(self, started):
        assert started.app.applicationName() == "rpncalc"
        assert started.app.organizationName() == "rpncalc"

    def test_the_bundled_font_is_registered(self, started):
        assert "iA Writer Mono S" in QFontDatabase.families()

    def test_the_application_wears_its_own_icon(self, started):
        # Without this the window and taskbar fall back to the interpreter's
        # icon, which is what a Python program wearing an .exe costume looks
        # like from the dock.
        icon = started.app.windowIcon()
        assert not icon.isNull()

    def test_the_icon_carries_every_size_windows_asks_for(self, started):
        sizes = {size.width() for size in started.app.windowIcon().availableSizes()}
        # 16/32/48 are the frames Explorer and a favicon reach for; 256 is the
        # one the large-icon view uses.  A single-frame icon gets scaled to mud.
        assert {16, 32, 48, 256} <= sizes

    def test_the_icon_ships_with_the_package(self):
        icon_path = entry._PACKAGE_DIR / "icons" / "rpncalc.ico"
        assert icon_path.is_file()
        assert not QIcon(str(icon_path)).isNull()

    def test_the_backend_calculates_through_the_built_app(self, started):
        for key in ("5", "enter", "3", "enter", "2", "+", "*"):
            started.backend.pressCommand(key)
        assert started.backend.stackLines == ["25"]

    def test_the_system_theme_reaches_the_backend(self, started):
        assert started.backend.darkMode == started.system_theme.darkMode()
        assert started.backend.themeBackground.startswith("#")

    def test_a_text_scale_change_propagates(self, started):
        started.system_theme.textScaleChanged.emit(1.25)
        assert started.backend.textScale == pytest.approx(1.25)

    def test_a_dark_mode_change_propagates(self, started):
        before = started.backend.darkMode
        started.system_theme.darkModeChanged.emit(not before)
        assert started.backend.darkMode is (not before)

    def test_starting_twice_reuses_the_one_application(self, clean_settings):
        first = start([])
        second = start([])
        assert first.app is second.app is QGuiApplication.instance()

    def test_saved_geometry_is_restored(self, clean_settings):
        settings = QSettings()
        settings.setValue("window/geometry", __import__("PySide6.QtCore", fromlist=["QRect"]).QRect(120, 80, 460, 900))
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        assert started.window.property("width") == 460
        assert started.window.property("height") == 900


class TestMain:
    def test_main_reports_failure_when_the_interface_will_not_load(
        self, monkeypatch, clean_settings, capsys
    ):
        broken = Startup(
            app=QGuiApplication.instance(),
            backend=None,
            system_theme=None,
            engine=None,
            window=None,
        )
        monkeypatch.setattr(entry, "start", lambda: broken)
        assert main() == -1

    def test_main_runs_the_event_loop_when_the_interface_loads(
        self, monkeypatch, clean_settings
    ):
        started = start([])
        assert started.loaded
        monkeypatch.setattr(entry, "start", lambda: started)
        monkeypatch.setattr(type(started.app), "exec", lambda self: 7)
        assert main() == 7


class TestTaskbarIdentity:
    def test_it_is_a_no_op_off_windows(self, monkeypatch):
        # ctypes.windll does not exist anywhere else, so an unguarded call
        # would take the app down on launch rather than merely look wrong.
        monkeypatch.setattr(entry.sys, "platform", "linux")
        entry._claim_taskbar_identity()


class TestResourceDir:
    def test_resolves_next_to_the_package_when_not_frozen(self):
        resolved = entry._resource_dir()
        assert (resolved / "qml" / "Main.qml").is_file()
        assert (resolved / "fonts" / "iAWriterMonoS-Regular.ttf").is_file()

    def test_follows_meipass_in_a_frozen_build(self, monkeypatch, tmp_path):
        # PyInstaller one-file unpacks the payload and points sys._MEIPASS at
        # it; __file__ is not where the assets are.
        monkeypatch.setattr(entry.sys, "_MEIPASS", str(tmp_path), raising=False)
        assert entry._resource_dir() == tmp_path / "rpncalc"
