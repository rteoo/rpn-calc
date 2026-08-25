"""Application entry point, port of omacalc's `main.cpp`."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from . import host
from .backend import Backend
from .systemtheme import SystemTheme


def _resource_dir() -> Path:
    """Where the QML and fonts live.

    A PyInstaller one-file build unpacks its data into a temporary directory
    and points `sys._MEIPASS` at it, so `__file__` is not where the assets are.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "rpncalc"
    return Path(__file__).resolve().parent


_PACKAGE_DIR = _resource_dir()


def _window_icon_path() -> Path:
    """The icon the window and the dock should wear.

    Windows reads every frame out of the multi-resolution `.ico`. The Dock
    and a macOS `.app` bundle prefer `.icns`; iOS ships its own asset
    catalog and falls back to the PNG. Missing files skip to the next
    candidate so a checkout that has not regenerated icons still launches.
    """
    icons = _PACKAGE_DIR / "icons"
    if host.is_ios():
        names = ("rpncalc.png", "rpncalc-1024.png", "rpncalc.ico")
    elif host.is_macos() or sys.platform == "darwin":
        names = ("rpncalc.icns", "rpncalc.png", "rpncalc.ico")
    else:
        names = ("rpncalc.ico", "rpncalc.png")
    for name in names:
        candidate = icons / name
        if candidate.is_file():
            return candidate
    return icons / "rpncalc.ico"


def _claim_taskbar_identity() -> None:
    """Stop Windows from lending this process python.exe's icon.

    The taskbar groups buttons by AppUserModelID, and a process launched by the
    interpreter inherits the interpreter's - so `python -m rpncalc` shows the
    Python logo in the taskbar however the window icon is set. Claiming an ID of
    our own detaches the button and lets `setWindowIcon` reach it.
    """
    if not host.is_windows():
        return
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("rpn-calc.rpncalc")


@dataclass
class Startup:
    """Everything `main` builds before handing control to the event loop.

    Kept separate so the startup path can be tested: `main` itself blocks in
    `app.exec()`, and this is where a broken theme reader or a QML file that
    stopped loading would show up. It has caught a real crash before - Qt's
    colorScheme() enum being coerced with int() - which no headless test of the
    engine could have found.
    """

    app: QGuiApplication
    backend: Backend
    system_theme: SystemTheme
    engine: QQmlApplicationEngine
    window: QObject | None

    @property
    def loaded(self) -> bool:
        return self.window is not None


def start(argv: list[str] | None = None) -> Startup:
    # Reuse an existing application when there is one: Qt allows only one per
    # process, and a test suite has already made it.
    app = QGuiApplication.instance() or QGuiApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("rpncalc")
    app.setOrganizationName("rpncalc")
    app.setOrganizationDomain("rpn-calc")

    # One multi-resolution .ico serves the window, the taskbar and the frozen
    # executable's resource on Windows; macOS prefers the .icns next to it.
    _claim_taskbar_identity()
    app.setWindowIcon(QIcon(str(_window_icon_path())))

    QFontDatabase.addApplicationFont(str(_PACKAGE_DIR / "fonts" / "iAWriterMonoS-Regular.ttf"))
    QFontDatabase.addApplicationFont(str(_PACKAGE_DIR / "fonts" / "iAWriterMonoS-Bold.ttf"))

    QQuickStyle.setStyle("Material")

    backend = Backend(app)
    system_theme = SystemTheme(app)
    backend.darkMode = system_theme.darkMode()
    system_theme.darkModeChanged.connect(lambda dark_mode: setattr(backend, "darkMode", dark_mode))

    # Carry the desktop's text scale into the default font so the chrome that
    # inherits it (menus, dialogs) grows along with the keypad.
    interface_font = QFont("iA Writer Mono S")
    base_point_size = (
        interface_font.pointSizeF() if interface_font.pointSizeF() > 0 else app.font().pointSizeF()
    )

    def apply_interface_font(text_scale: float) -> None:
        scaled = QFont(interface_font)
        scaled.setPointSizeF(base_point_size * text_scale)
        app.setFont(scaled)

    apply_interface_font(system_theme.textScale())
    backend.textScale = system_theme.textScale()

    def handle_text_scale_changed(text_scale: float) -> None:
        apply_interface_font(text_scale)
        backend.textScale = text_scale

    system_theme.textScaleChanged.connect(handle_text_scale_changed)

    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warnings: [print(warning.toString()) for warning in warnings])
    engine.rootContext().setContextProperty("backend", backend)

    qml_path = _PACKAGE_DIR / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    roots = engine.rootObjects()
    if not roots:
        print(
            f"Could not load the rpncalc interface; file available: {qml_path.exists()}",
            file=sys.stderr,
        )

    return Startup(
        app=app,
        backend=backend,
        system_theme=system_theme,
        engine=engine,
        window=roots[0] if roots else None,
    )


def main() -> int:
    if "--smoke" in sys.argv:
        sys.argv = [arg for arg in sys.argv if arg != "--smoke"]
        return smoke()
    started = start()
    if not started.loaded:
        return -1
    return started.app.exec()


# `--smoke` exit codes. Distinct so CI can tell "you ran it under the wrong
# plugin" from "the window that opened is not the faceplate".
SMOKE_OK = 0
SMOKE_NOT_LOADED = -1
SMOKE_WRONG_PLATFORM = 2
SMOKE_WRONG_WINDOW = 3

# How long to spin the event queue waiting for the compositor to map the
# window. Generous: a cold CI Mac is slower than a desktop, and the loop
# stops the moment the window is exposed.
_EXPOSE_TIMEOUT_MS = 3000


def platform_verdict(platform: str, *, on_mac: bool) -> tuple[int, str]:
    """Whether this Qt platform plugin can produce a real window.

    Offscreen is refused: a passing `start()` under `QT_QPA_PLATFORM=offscreen`
    is not evidence the app opens, which is the whole point of this path. On a
    Mac it has to be cocoa specifically.
    """
    if platform in ("offscreen", "minimal", "null"):
        return (
            SMOKE_WRONG_PLATFORM,
            f"platform {platform!r} is not a real window (unset QT_QPA_PLATFORM)",
        )
    if on_mac and platform != "cocoa":
        return SMOKE_WRONG_PLATFORM, f"expected cocoa on macOS, got {platform!r}"
    return SMOKE_OK, ""


@dataclass(frozen=True)
class SmokeReading:
    """What the window that opened actually is.

    Plain data, read off the live window and then judged separately, so every
    branch of `window_verdict` can be tested without a display. The checks are
    what a release depends on; testing them only on a CI Mac would mean the
    gate itself is never exercised.
    """

    platform: str
    title: str
    width: int
    height: int
    exposed: bool
    icon_sizes: tuple[int, ...]
    text_scale: float
    dark_mode: bool
    quit_on_close: bool
    calculator_key: bool
    icon_name: str
    # The screen's available geometry, or None where Qt reports no screen.
    room: tuple[int, int] | None
    on_mac: bool

    def line(self) -> str:
        return (
            f"SMOKE platform={self.platform} exposed={self.exposed} "
            f"title={self.title!r} width={self.width} height={self.height} "
            f"textScale={self.text_scale} darkMode={self.dark_mode} "
            f"quitOnClose={self.quit_on_close} icon={self.icon_name} "
            f"calculatorKey={self.calculator_key} "
            f"iconSizes={list(self.icon_sizes)}"
        )


# The faceplate is drawn at 420x820 and the window keeps that shape.
_FACE_RATIO = 420 / 820
_FACE_RATIO_TOLERANCE = 0.05
_FACE_MIN_WIDTH = 330
_FACE_MIN_HEIGHT = 640


def window_verdict(reading: SmokeReading) -> tuple[int, str]:
    """Whether the window that opened is the calculator."""
    # Exposure, not `visible`: `visible` is a literal in Main.qml and would
    # read true for a window the compositor never mapped. Being exposed is
    # the platform saying it put pixels somewhere.
    if not reading.exposed:
        return SMOKE_WRONG_WINDOW, "window was never exposed by the compositor"
    if reading.title != "rpn-calc":
        return SMOKE_WRONG_WINDOW, f"unexpected title {reading.title!r}"
    if reading.width < _FACE_MIN_WIDTH or reading.height < _FACE_MIN_HEIGHT:
        return SMOKE_WRONG_WINDOW, "window smaller than the faceplate minimum"
    if reading.room is not None:
        room_width, room_height = reading.room
        if reading.width >= room_width or reading.height >= room_height:
            return SMOKE_WRONG_WINDOW, "window fills the display"
    # Safe to divide: the minimum height above has already rejected zero.
    ratio = reading.width / reading.height
    if abs(ratio - _FACE_RATIO) > _FACE_RATIO_TOLERANCE:
        return SMOKE_WRONG_WINDOW, "window lost the 420x820 face proportion"
    if not reading.icon_sizes:
        return SMOKE_WRONG_WINDOW, "no window icon"
    if reading.on_mac and reading.text_scale != 1.0:
        return SMOKE_WRONG_WINDOW, "Retina must not double the window"
    if not reading.quit_on_close:
        # Qt's default, pinned here: a single-window utility that leaves a
        # process behind after its window closes has nowhere to live.
        return SMOKE_WRONG_WINDOW, "closing the window must quit the app"
    if reading.on_mac and reading.calculator_key:
        return SMOKE_WRONG_WINDOW, "the calculator key is a Windows binding"
    return SMOKE_OK, ""


def _read_window(started: Startup) -> SmokeReading:
    """Drain the event queue until the window is mapped, then measure it."""
    from PySide6.QtCore import QElapsedTimer

    window = started.window
    timer = QElapsedTimer()
    timer.start()
    while not window.isExposed() and timer.elapsed() < _EXPOSE_TIMEOUT_MS:
        started.app.processEvents()

    screen = started.app.primaryScreen()
    room = None
    if screen is not None:
        available = screen.availableGeometry()
        room = (available.width(), available.height())

    icon = started.app.windowIcon()
    return SmokeReading(
        platform=started.app.platformName(),
        title=str(window.property("title") or ""),
        width=int(window.property("width") or 0),
        height=int(window.property("height") or 0),
        exposed=bool(window.isExposed()),
        icon_sizes=tuple(sorted(size.width() for size in icon.availableSizes())),
        text_scale=float(started.backend.textScale),
        dark_mode=bool(started.backend.darkMode),
        quit_on_close=bool(started.app.quitOnLastWindowClosed()),
        calculator_key=bool(started.backend.calculatorKeySupported),
        icon_name=_window_icon_path().name,
        room=room,
        on_mac=host.is_macos(),
    )


def smoke() -> int:
    """Open the real window, report what it is, and quit.

    No event loop, so CI cannot hang here: the wait for the window to be
    mapped is bounded, and the window is closed on every path out.
    """
    started = start()
    if not started.loaded or started.window is None:
        print("SMOKE_FAIL: the interface did not load", file=sys.stderr)
        return SMOKE_NOT_LOADED

    code, reason = platform_verdict(
        started.app.platformName(), on_mac=host.is_macos()
    )
    if code != SMOKE_OK:
        print(f"SMOKE_FAIL: {reason}", file=sys.stderr)
        return code

    reading = _read_window(started)
    print(reading.line())

    code, reason = window_verdict(reading)
    started.window.close()
    if code != SMOKE_OK:
        print(f"SMOKE_FAIL: {reason}", file=sys.stderr)
        return code

    print("SMOKE_OK")
    return SMOKE_OK


if __name__ == "__main__":
    sys.exit(main())
