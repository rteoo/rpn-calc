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


def _apply_apple_presentation(app: QGuiApplication) -> None:
    """Dock / home-indicator behaviour that only applies on Apple hosts.

    A single-window utility should quit when its window closes. macOS would
    otherwise keep a menuless process sitting in the Dock. iOS has nowhere
    for that process to live either.
    """
    if not (host.is_macos() or host.is_ios()):
        return
    app.setQuitOnLastWindowClosed(True)


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
    _apply_apple_presentation(app)
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
    smoke_mode = "--smoke" in sys.argv
    if smoke_mode:
        sys.argv = [arg for arg in sys.argv if arg != "--smoke"]
        return smoke()
    started = start()
    if not started.loaded:
        return -1
    return started.app.exec()


def smoke() -> int:
    """Open the real window, report what it is, and quit.

    Offscreen is refused: a passing `start()` under `QT_QPA_PLATFORM=offscreen`
    is not evidence the app opens, which is the whole point of this path.
    On a Mac this must be cocoa. Drains a few events so the platform maps a
    native window, then closes it — no event loop, so CI cannot hang here.
    """
    started = start()
    if not started.loaded or started.window is None:
        print("SMOKE_FAIL: the interface did not load", file=sys.stderr)
        return -1

    platform = started.app.platformName()
    if platform in ("offscreen", "minimal", "null"):
        print(
            f"SMOKE_FAIL: platform {platform!r} is not a real window "
            "(unset QT_QPA_PLATFORM)",
            file=sys.stderr,
        )
        return 2
    if sys.platform == "darwin" and platform != "cocoa":
        print(f"SMOKE_FAIL: expected cocoa on macOS, got {platform!r}", file=sys.stderr)
        return 2

    from PySide6.QtCore import QElapsedTimer

    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < 400:
        started.app.processEvents()

    window = started.window
    width = int(window.property("width") or 0)
    height = int(window.property("height") or 0)
    visible = bool(window.property("visible"))
    title = str(window.property("title") or "")
    icon_sizes = {size.width() for size in started.app.windowIcon().availableSizes()}
    native = int(window.winId()) != 0
    text_scale = float(started.backend.textScale)
    dark_mode = bool(started.backend.darkMode)
    quit_on_close = bool(started.app.quitOnLastWindowClosed())
    calculator_key = bool(started.backend.calculatorKeySupported)
    icon_name = _window_icon_path().name

    report = (
        f"SMOKE platform={platform} visible={visible} title={title!r} "
        f"width={width} height={height} native={native} "
        f"textScale={text_scale} darkMode={dark_mode} "
        f"quitOnClose={quit_on_close} icon={icon_name} "
        f"calculatorKey={calculator_key} iconSizes={sorted(icon_sizes)}"
    )
    print(report)

    if not visible:
        print("SMOKE_FAIL: window is not visible", file=sys.stderr)
        window.close()
        return 3
    if title != "rpn-calc":
        print(f"SMOKE_FAIL: unexpected title {title!r}", file=sys.stderr)
        window.close()
        return 3
    if width < 330 or height < 640:
        print("SMOKE_FAIL: window smaller than the faceplate minimum", file=sys.stderr)
        window.close()
        return 3
    screen = started.app.primaryScreen()
    if screen is not None:
        room = screen.availableGeometry()
        if width >= room.width() or height >= room.height():
            print("SMOKE_FAIL: window fills the display", file=sys.stderr)
            window.close()
            return 3
    if abs(width / height - 420 / 820) > 0.05:
        print("SMOKE_FAIL: window lost the 420×820 face proportion", file=sys.stderr)
        window.close()
        return 3
    if started.app.windowIcon().isNull():
        print("SMOKE_FAIL: no window icon", file=sys.stderr)
        window.close()
        return 3
    if host.is_macos() and text_scale != 1.0:
        print("SMOKE_FAIL: Retina must not double the window", file=sys.stderr)
        window.close()
        return 3
    if host.is_macos() and not quit_on_close:
        print("SMOKE_FAIL: closing the window must quit on macOS", file=sys.stderr)
        window.close()
        return 3
    if host.is_macos() and calculator_key:
        print("SMOKE_FAIL: the calculator key is a Windows binding", file=sys.stderr)
        window.close()
        return 3
    if not native:
        print("SMOKE_FAIL: no native window handle", file=sys.stderr)
        window.close()
        return 3

    window.close()
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
