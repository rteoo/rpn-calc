# PyInstaller spec for the desktop builds.  Build with tools/build_exe.py.
#
# Windows: a folder build, zipped, no console.  macOS: an .app bundle (a folder
# build inside, because one-file .app is what Gatekeeper fights).  PySide6 drags
# in the whole Qt distribution unless it is told otherwise, so the excludes
# below are load-bearing: without them the payload carries WebEngine, 3D,
# multimedia and charting for a calculator that draws seven rows of buttons.

import os
import sys
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

ICON_ICO = PACKAGE / "icons" / "rpncalc.ico"
ICON_ICNS = PACKAGE / "icons" / "rpncalc.icns"
MACOS = sys.platform == "darwin"
VERSION = os.environ.get("RPNCALC_VERSION", "0.0.0")

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

# A folder build is the default everywhere, because one file pays for its shape
# on every single launch.  The bootloader unpacks the whole payload to a fresh
# temporary directory before Qt starts: measured on Windows, a median 3544 ms
# to a mapped window against 727 ms for the folder.  It never warms up, and it
# cannot - the unpack directory is new every time, so Qt's compiled-QML cache is
# keyed to a path that no longer exists and every launch reparses the QML too.
#
# The folder ships zipped, which is what macOS already does with the .app, so a
# release download is the same size either way.  RPNCALC_BUILD_ONEFILE=1 still
# builds the single .exe for anyone who wants to hand someone one file; macOS
# ignores it, because a folder is what goes inside the .app bundle.
ONEFILE_BUILD = os.environ.get("RPNCALC_BUILD_ONEFILE") == "1" and not MACOS
ONEDIR_BUILD = not ONEFILE_BUILD

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["rpncalc.backend", "rpncalc.systemtheme", "rpncalc.host", "rpncalc.launchkey"],
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

# Qt on Windows imports the system ICU forwarder.  PyInstaller follows the
# current PATH while resolving that import, so an unrelated toolchain can
# otherwise leak its private ICU build into the package.  A versioned ICU
# implementation then shadows Windows' forwarder and QtCore fails to import.
WINDOWS_AMBIENT_ICU = {"icuuc.dll", "icudt78.dll"}


def _pruned(entry):
    name = entry[0].replace("\\", "/").lower()
    # Never prune this application's own assets.
    if name.startswith("rpncalc/"):
        return False
    if sys.platform == "win32" and Path(name).name in WINDOWS_AMBIENT_ICU:
        return True
    return any(token in name for token in PRUNE)


a.binaries = [entry for entry in a.binaries if not _pruned(entry)]
a.datas = [entry for entry in a.datas if not _pruned(entry)]

pyz = PYZ(a.pure)

name = "rpncalc-debug" if DEBUG_BUILD else "rpncalc"

exe_kwargs = dict(
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
)
if MACOS and ICON_ICNS.is_file():
    exe_kwargs["icon"] = str(ICON_ICNS)
elif ICON_ICO.is_file():
    exe_kwargs["icon"] = str(ICON_ICO)
if sys.platform == "win32":
    exe_kwargs["version"] = str(ROOT / "packaging" / "version_info.txt")

exe = EXE(
    pyz,
    a.scripts,
    [] if ONEDIR_BUILD else a.binaries,
    [] if ONEDIR_BUILD else a.datas,
    **exe_kwargs,
)

if ONEDIR_BUILD:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=name,
    )
    if MACOS:
        # A debug build gets its own bundle so it cannot overwrite the
        # release one sitting next to it in dist/.
        BUNDLE(
            coll,
            name="rpn-calc-debug.app" if DEBUG_BUILD else "rpn-calc.app",
            icon=str(ICON_ICNS) if ICON_ICNS.is_file() else None,
            bundle_identifier="io.github.rteoo.rpncalc",
            info_plist={
                "CFBundleName": "rpn-calc-debug" if DEBUG_BUILD else "rpn-calc",
                "CFBundleDisplayName": "rpn-calc-debug" if DEBUG_BUILD else "rpn-calc",
                "CFBundleIdentifier": "io.github.rteoo.rpncalc",
                "CFBundleVersion": VERSION,
                "CFBundleShortVersionString": VERSION,
                "CFBundlePackageType": "APPL",
                "CFBundleSignature": "????",
                "LSMinimumSystemVersion": "12.0",
                "LSApplicationCategoryType": "public.app-category.utilities",
                "NSHighResolutionCapable": True,
                "NSRequiresAquaSystemAppearance": False,
                "NSSupportsAutomaticGraphicsSwitching": True,
                "NSHumanReadableCopyright": (
                    "MIT. Derived from omacalc. iA Writer Mono S under OFL 1.1."
                ),
                "CFBundleIconFile": "rpncalc.icns",
            },
        )
