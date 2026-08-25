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
from PySide6.QtCore import QRect, QSettings
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

    def test_the_window_icon_carries_the_sizes_the_host_asks_for(self, started):
        from rpncalc import host

        sizes = {size.width() for size in started.app.windowIcon().availableSizes()}
        # A single-frame icon gets scaled to mud. Windows Explorer wants
        # 16/32/48 plus 256 for the large-icon view. The Dock reads an
        # .icns, which has no 48px type — 16/32/256/512 instead.
        if host.is_macos():
            assert {16, 32, 256, 512} <= sizes
        else:
            assert {16, 32, 48, 256} <= sizes

    def test_the_ico_still_has_the_windows_frames(self):
        # The window may wear .icns on a Mac, but the committed .ico is what
        # Explorer and a favicon reach for and must not lose 48px.
        icon = QIcon(str(entry._PACKAGE_DIR / "icons" / "rpncalc.ico"))
        sizes = {size.width() for size in icon.availableSizes()}
        assert {16, 32, 48, 256} <= sizes

    def test_the_icon_ships_with_the_package(self):
        icon_path = entry._PACKAGE_DIR / "icons" / "rpncalc.ico"
        assert icon_path.is_file()
        assert not QIcon(str(icon_path)).isNull()

    def test_the_backend_calculates_through_the_built_app(self, started):
        for key in ("5", "enter", "3", "enter", "2", "+", "*"):
            started.backend.pressCommand(key)
        assert started.backend.stackLines == ["25"]

    def test_option_s_is_square_root(self, started):
        # On a Mac, Option is Qt.AltModifier. Matching event.key rather than
        # event.text is what stops ß swallowing √ — this is that path.
        from PySide6.QtCore import QEvent, QObject, Qt
        from PySide6.QtGui import QKeyEvent

        started.backend.pressCommand("9")
        started.backend.pressCommand("enter")
        face = started.window.findChild(QObject, "face")
        assert face is not None
        QGuiApplication.sendEvent(
            face,
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.AltModifier, "s"),
        )
        started.app.processEvents()
        assert started.backend.stackLines == ["3"]

    def test_smoke_refuses_an_offscreen_window(self, clean_settings):
        # A passing start() under QT_QPA_PLATFORM=offscreen is exactly what
        # issue #15 says is not enough. This suite forces that plugin.
        assert QGuiApplication.instance().platformName() == "offscreen"
        assert entry.smoke() == 2

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
        from PySide6.QtGui import QGuiApplication

        # Sized to fit the screen the test runs on: a window larger than its
        # display is shrunk on purpose, which TestWindowGeometry covers.
        room = QGuiApplication.primaryScreen().availableGeometry()
        width = min(420, room.width() - 100)
        height = min(700, room.height() - 100)

        settings = QSettings()
        settings.setValue("window/geometry", QRect(120, 80, width, height))
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        assert started.window.property("width") == width
        assert started.window.property("height") == height


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
        monkeypatch.setattr(entry.host, "is_windows", lambda: False)
        entry._claim_taskbar_identity()


class TestApplePresentation:
    def test_it_is_a_no_op_off_apple(self, monkeypatch, started):
        monkeypatch.setattr(entry.host, "is_macos", lambda: False)
        monkeypatch.setattr(entry.host, "is_ios", lambda: False)
        entry._apply_apple_presentation(started.app)

    def test_a_mac_quits_when_the_window_closes(self, monkeypatch, started):
        monkeypatch.setattr(entry.host, "is_macos", lambda: True)
        monkeypatch.setattr(entry.host, "is_ios", lambda: False)
        started.app.setQuitOnLastWindowClosed(False)
        entry._apply_apple_presentation(started.app)
        assert started.app.quitOnLastWindowClosed() is True


class TestWindowIconPath:
    def test_windows_and_linux_prefer_the_ico(self, monkeypatch):
        monkeypatch.setattr(entry.host, "is_ios", lambda: False)
        monkeypatch.setattr(entry.host, "is_macos", lambda: False)
        monkeypatch.setattr(entry.sys, "platform", "linux")
        path = entry._window_icon_path()
        assert path.name == "rpncalc.ico"
        assert path.is_file()

    def test_macos_prefers_icns_when_present(self, monkeypatch):
        monkeypatch.setattr(entry.host, "is_ios", lambda: False)
        monkeypatch.setattr(entry.host, "is_macos", lambda: True)
        monkeypatch.setattr(entry.sys, "platform", "darwin")
        path = entry._window_icon_path()
        assert path.name == "rpncalc.icns"
        assert path.is_file()

    def test_ios_prefers_png(self, monkeypatch):
        monkeypatch.setattr(entry.host, "is_ios", lambda: True)
        monkeypatch.setattr(entry.host, "is_macos", lambda: False)
        path = entry._window_icon_path()
        assert path.name == "rpncalc.png"
        assert path.is_file()

    def test_falls_back_when_preferred_icons_are_missing(self, monkeypatch, tmp_path):
        (tmp_path / "icons").mkdir()
        monkeypatch.setattr(entry, "_PACKAGE_DIR", tmp_path)
        monkeypatch.setattr(entry.host, "is_ios", lambda: False)
        monkeypatch.setattr(entry.host, "is_macos", lambda: True)
        monkeypatch.setattr(entry.sys, "platform", "darwin")
        # None of the Apple candidates exist, so the Windows .ico name is what
        # the caller still looks for - and a missing file is their problem,
        # not a launch crash.
        assert entry._window_icon_path() == tmp_path / "icons" / "rpncalc.ico"

    def test_the_icns_ships_with_the_package(self):
        icns = entry._PACKAGE_DIR / "icons" / "rpncalc.icns"
        png = entry._PACKAGE_DIR / "icons" / "rpncalc-1024.png"
        assert icns.is_file()
        assert png.is_file()
        assert icns.read_bytes()[:4] == b"icns"


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


class TestWindowGeometry:
    """Restoring the window.

    Two bugs met here and made the app open maximized with no way back:
    QSettings stores a boolean as the text "true"/"false" and bool("false") is
    True, so `maximized` was always true once anything had been saved; and the
    design size grown by a 150% text scale is 1230 pixels tall, which does not
    fit a 1080-pixel screen, so the window was born filling its display.

    Restoring a saved maximized flag is also refused: the faceplate is a fixed
    proportion, and a stale true (left by those bugs) re-maximized on every
    launch, then wrote itself back on close. A leftover windowed frame the
    size of the work area is refused the same way: it still "fits", so it
    would otherwise open ~1920 pixels wide.
    """

    def geometry_of(self, started):
        return (
            started.window.property("width"),
            started.window.property("height"),
        )

    def available(self):
        from PySide6.QtGui import QGuiApplication

        return QGuiApplication.primaryScreen().availableGeometry()

    def test_a_fresh_window_is_not_maximized(self, clean_settings):
        from PySide6.QtCore import QSettings
        from PySide6.QtGui import QWindow

        assert QSettings().value("window/maximized") is None
        started = start([])
        assert started.window.property("visibility") != QWindow.Maximized

    def test_maximized_false_round_trips(self, clean_settings):
        backend_only = start([]).backend
        backend_only.saveWindowGeometry(10, 20, 400, 800, False)
        assert backend_only.windowGeometry()["maximized"] is False

    def test_maximized_true_round_trips(self, clean_settings):
        backend_only = start([]).backend
        backend_only.saveWindowGeometry(10, 20, 400, 800, True)
        assert backend_only.windowGeometry()["maximized"] is True

    def test_a_saved_false_does_not_restore_maximized(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings
        from PySide6.QtGui import QWindow

        settings = QSettings()
        settings.setValue("window/geometry", QRect(40, 40, 420, 700))
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        assert started.window.property("visibility") != QWindow.Maximized

    def test_a_stale_maximized_flag_does_not_reopen_maximized(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings
        from PySide6.QtGui import QWindow

        # The reported case: window/maximized stuck at true from the original
        # oversized-window bug. Opening maximized would stretch the faceplate
        # and write the flag straight back, so there was no way out.
        room = self.available()
        settings = QSettings()
        settings.setValue(
            "window/geometry", QRect(40, 40, room.width() * 2, room.height() * 2)
        )
        settings.setValue("window/maximized", True)
        settings.sync()

        started = start([])
        assert started.window.property("visibility") != QWindow.Maximized
        width, height = self.geometry_of(started)
        design_w = round(420 * started.backend.textScale)
        design_h = round(820 * started.backend.textScale)
        fitted = started.backend.fitToScreen(40, 40, design_w, design_h)
        assert (width, height) == (
            max(started.window.property("minimumWidth"), fitted["width"]),
            max(started.window.property("minimumHeight"), fitted["height"]),
        )

    def test_a_screen_filling_saved_size_opens_at_the_design_face(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings

        # The leftover the 0.1.1 fix did not catch: a windowed frame the size
        # of the work area still "fits", so fitToScreen left a 1920-wide face.
        room = self.available()
        settings = QSettings()
        settings.setValue(
            "window/geometry", QRect(0, 0, room.width(), room.height())
        )
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        width, height = self.geometry_of(started)
        design_w = round(420 * started.backend.textScale)
        design_h = round(820 * started.backend.textScale)
        fitted = started.backend.fitToScreen(0, 0, design_w, design_h)
        assert (width, height) == (
            max(started.window.property("minimumWidth"), fitted["width"]),
            max(started.window.property("minimumHeight"), fitted["height"]),
        )
        assert width < room.width()

    def test_a_window_taller_than_the_screen_is_shrunk_to_fit(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings

        room = self.available()
        settings = QSettings()
        # The reported state: 420x820 grown by a 150% text scale.
        settings.setValue(
            "window/geometry", QRect(0, 0, room.width() * 2, room.height() * 2)
        )
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        width, height = self.geometry_of(started)
        design_w = round(420 * started.backend.textScale)
        design_h = round(820 * started.backend.textScale)
        fitted = started.backend.fitToScreen(0, 0, design_w, design_h)
        assert (width, height) == (
            max(started.window.property("minimumWidth"), fitted["width"]),
            max(started.window.property("minimumHeight"), fitted["height"]),
        )

    def test_shrinking_keeps_the_proportions_of_the_face(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings

        room = self.available()
        settings = QSettings()
        settings.setValue("window/geometry", QRect(0, 0, 4200, 8200))
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        width, height = self.geometry_of(started)
        # A leftover stretch is discarded; the design face (420x820) is fitted.
        assert width / height == pytest.approx(420 / 820, rel=0.02)
        assert width <= room.width() and height <= room.height()
        assert width <= round(420 * started.backend.textScale)

    def test_a_window_that_already_fits_is_left_alone(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings

        room = self.available()
        wanted_width = min(420, room.width() - 100)
        wanted_height = min(700, room.height() - 100)
        settings = QSettings()
        settings.setValue(
            "window/geometry", QRect(30, 30, wanted_width, wanted_height)
        )
        settings.setValue("window/maximized", False)
        settings.sync()

        assert self.geometry_of(start([])) == (wanted_width, wanted_height)

    def test_shrinking_never_goes_below_the_minimum(self, clean_settings):
        from PySide6.QtCore import QRect, QSettings

        settings = QSettings()
        settings.setValue("window/geometry", QRect(0, 0, 100000, 100000))
        settings.setValue("window/maximized", False)
        settings.sync()

        started = start([])
        width, height = self.geometry_of(started)
        assert width >= started.window.property("minimumWidth")
        assert height >= started.window.property("minimumHeight")


class TestFitToScreen:
    """Sizing a window against the screen it opens on.

    This lives in the backend because QML's Screen attached property only
    exposes `desktopAvailableWidth`/`Height`, which span the whole virtual
    desktop. On a multi-monitor setup with different vertical offsets that is
    taller than any single screen, so an oversized window measured as fitting
    and was never shrunk - the first version of this fix did nothing at all.
    """

    def room(self):
        from PySide6.QtGui import QGuiApplication

        return QGuiApplication.primaryScreen().availableGeometry()

    def backend_of(self, clean_settings):
        return start([]).backend

    def test_a_window_that_fits_is_returned_unchanged(self, clean_settings):
        backend = self.backend_of(clean_settings)
        room = self.room()
        wanted = (min(420, room.width() // 2), min(700, room.height() // 2))
        fitted = backend.fitToScreen(0, 0, *wanted)
        assert (fitted["width"], fitted["height"]) == wanted

    def test_an_oversized_window_is_shrunk_inside_the_work_area(self, clean_settings):
        backend = self.backend_of(clean_settings)
        room = self.room()
        fitted = backend.fitToScreen(0, 0, room.width() * 2, room.height() * 2)
        assert fitted["width"] <= room.width()
        assert fitted["height"] <= room.height()

    def test_shrinking_preserves_the_aspect_ratio(self, clean_settings):
        backend = self.backend_of(clean_settings)
        room = self.room()
        wanted_width, wanted_height = room.width() * 3, room.height() * 3
        fitted = backend.fitToScreen(0, 0, wanted_width, wanted_height)
        assert fitted["width"] / fitted["height"] == pytest.approx(
            wanted_width / wanted_height, rel=0.01
        )

    def test_only_the_offending_dimension_forces_the_shrink(self, clean_settings):
        # Tall but narrow: the height is what does not fit, and the width comes
        # down with it rather than the face being letterboxed.
        backend = self.backend_of(clean_settings)
        room = self.room()
        fitted = backend.fitToScreen(0, 0, 420, room.height() * 2)
        assert fitted["height"] <= room.height()
        assert fitted["width"] < 420

    def test_a_zero_size_is_returned_as_is(self, clean_settings):
        backend = self.backend_of(clean_settings)
        assert backend.fitToScreen(0, 0, 0, 0) == {"width": 0, "height": 0}

    def test_a_position_off_every_screen_still_fits_somewhere(self, clean_settings):
        # screenAt() returns nothing out there, so it falls back to the primary
        # screen rather than declining to size the window at all.
        backend = self.backend_of(clean_settings)
        room = self.room()
        fitted = backend.fitToScreen(-99999, -99999, room.width() * 2, room.height() * 2)
        assert 0 < fitted["width"] <= room.width()
        assert 0 < fitted["height"] <= room.height()

    def test_the_reported_case(self, clean_settings):
        # 420x820 grown by a 150% desktop text scale, which is what was on disk.
        backend = self.backend_of(clean_settings)
        room = self.room()
        fitted = backend.fitToScreen(0, 0, 630, 1230)
        if room.height() >= 1230 + 60:
            assert (fitted["width"], fitted["height"]) == (630, 1230)
        else:
            assert fitted["height"] <= room.height()
            assert fitted["width"] / fitted["height"] == pytest.approx(630 / 1230, rel=0.01)


class TestSettingsMenu:
    """The calculator-key toggle is the only settings surface.

    Material MenuItem sizes itself against the style font, then this app draws
    it with the scaled interface font, so the popup was too narrow and the
    label elided to "Launch on th…".
    """

    LABEL = "Launch on the calculator key"

    def test_the_item_keeps_its_full_label(self, clean_settings):
        from PySide6.QtCore import QObject

        started = start([])
        item = started.window.findChild(QObject, "calculatorKeyItem")
        assert item is not None
        assert item.property("text") == self.LABEL

    def test_the_popup_is_wider_than_the_label(self, clean_settings):
        from PySide6.QtCore import QObject
        from PySide6.QtGui import QFontMetrics

        started = start([])
        menu = started.window.findChild(QObject, "settingsMenu")
        item = started.window.findChild(QObject, "calculatorKeyItem")
        assert menu is not None and item is not None

        font = item.property("font")
        advance = QFontMetrics(font).horizontalAdvance(self.LABEL)
        em = font.pixelSize() if font.pixelSize() > 0 else max(1, round(font.pointSizeF() * 4 / 3))
        assert menu.property("width") >= advance + em
