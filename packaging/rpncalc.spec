# PyInstaller spec for the Windows build.  Build with tools/build_exe.py.
#
# One file, no console.  PySide6 drags in the whole Qt distribution unless it
# is told otherwise, so the excludes below are load-bearing: without them the
# executable carries WebEngine, 3D, multimedia and charting for a calculator
# that draws seven rows of buttons.

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "src" / "rpncalc"

# Qt modules this app never touches.  QtNetwork, QtOpenGL and QtQml stay: Qt
# Quick loads its scene graph and QML engine through them.
EXCLUDED_QT = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtGraphs", "PySide6.QtHelp",
    "PySide6.QtLocation", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning", "PySide6.QtPrintSupport", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialBus",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
    "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets", "PySide6.QtXml",
]

EXCLUDED_PYTHON = [
    "tkinter", "unittest", "pydoc_data", "test", "distutils",
    "email", "html", "http", "xmlrpc", "pytest", "PIL", "numpy",
]

ICON = PACKAGE / "icons" / "rpncalc.ico"

# The icon ships inside the package, not beside the spec: the app sets it as its
# own window icon at startup, so it has to be there when running from source too.
datas = [
    (str(PACKAGE / "qml"), "rpncalc/qml"),
    (str(PACKAGE / "fonts"), "rpncalc/fonts"),
    (str(PACKAGE / "icons"), "rpncalc/icons"),
]

# A windowed build has nowhere to print a traceback, which makes a failure to
# start look like a hang. RPNCALC_BUILD_DEBUG=1 produces a console build that
# says what went wrong.
DEBUG_BUILD = os.environ.get("RPNCALC_BUILD_DEBUG") == "1"

# One file is what "a distributable .exe" means, but it pays for that shape on
# every launch: the bootloader unpacks the whole 53 MB payload to a temporary
# directory before Qt starts, about three seconds each time, and it never warms
# up. A folder build starts in a fraction of that. RPNCALC_BUILD_ONEDIR=1
# selects it.
ONEDIR_BUILD = os.environ.get("RPNCALC_BUILD_ONEDIR") == "1"

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["rpncalc.backend", "rpncalc.systemtheme"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_PYTHON,
    noarchive=False,
    optimize=1,
)

# Excluding a PySide6 *module* does not stop PyInstaller's hook from copying the
# Qt *libraries* behind it, so the payload has to be pruned by hand. Without
# this the executable carries Qt6WebEngineCore.dll - a complete Chromium, 194 MB
# - because PySide6 ships it and the hook collects what it finds.
PRUNE = (
    "webengine",
    "qt63d", "qt3d",
    "quick3d",
    "charts",
    "datavisualization",
    "qt6graphs", "qtgraphs",
    "multimedia",
    "qt6pdf", "qtpdf",
    "qt6sql", "qtsql",
    "qt6test", "qttest",
    "qt6bluetooth", "qt6nfc", "qt6positioning", "qt6location",
    "qt6serialport", "qt6serialbus", "qt6sensors",
    "qt6texttospeech", "qt6scxml", "qt6statemachine",
    "qt6remoteobjects", "qt6websockets", "qt6webchannel",
    "qt6spatialaudio", "qt6designer", "qt6help", "qt6uitools",
    # Qt's own UI translations, for dialogs this app never opens.
    "pyside6/translations/",
    # TLS for networking this app never does.
    "libcrypto", "libssl",
    # Only the Material style is used; the others are whole extra skins.
    "controls2imagine", "controls2universal", "controls2fusion",
    "controls/imagine", "controls/universal", "controls/fusion",
)


def _pruned(entry):
    name = entry[0].replace("\\", "/").lower()
    # Never prune this application's own assets.
    if name.startswith("rpncalc/"):
        return False
    return any(token in name for token in PRUNE)


a.binaries = [entry for entry in a.binaries if not _pruned(entry)]
a.datas = [entry for entry in a.datas if not _pruned(entry)]

pyz = PYZ(a.pure)

name = "rpncalc-debug" if DEBUG_BUILD else "rpncalc"

exe = EXE(
    pyz,
    a.scripts,
    [] if ONEDIR_BUILD else a.binaries,
    [] if ONEDIR_BUILD else a.datas,
    exclude_binaries=ONEDIR_BUILD,
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # No console window: this is a GUI app, and a flashing terminal behind it
    # is the clearest sign of a Python program wearing an .exe costume.
    console=DEBUG_BUILD,
    disable_windowed_traceback=False,
    icon=str(ICON),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

if ONEDIR_BUILD:
    COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=name,
    )
