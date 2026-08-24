"""Application entry point, port of omacalc's `main.cpp`."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

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
    started = start()
    if not started.loaded:
        return -1
    return started.app.exec()


if __name__ == "__main__":
    sys.exit(main())
