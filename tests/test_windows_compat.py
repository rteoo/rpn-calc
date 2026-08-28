"""Windows host contract — macOS work must not change these.

The Linux job cannot prove this; the windows-latest pytest job is the real
gate. These assertions pin the Windows paths in source so an Apple-only edit
fails here before it ships.
"""

from __future__ import annotations

import ctypes
from pathlib import Path

import pytest
from PySide6.QtGui import QIcon

from rpncalc import __main__ as entry
from rpncalc import host, launchkey, systemtheme
from rpncalc.backend import Backend
from rpncalc.systemtheme import SystemTheme

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def windows_host(monkeypatch):
    monkeypatch.setattr(host, "is_windows", lambda: True)
    monkeypatch.setattr(host, "is_macos", lambda: False)
    monkeypatch.setattr(host, "is_ios", lambda: False)
    monkeypatch.setattr(host, "is_linux", lambda: False)
    monkeypatch.setattr(host, "is_mobile", lambda: False)
    monkeypatch.setattr(host, "remembers_window_geometry", lambda: True)
    monkeypatch.setattr(host, "has_pointer_hover", lambda: True)
    monkeypatch.setattr(entry.host, "is_windows", lambda: True)
    monkeypatch.setattr(entry.host, "is_macos", lambda: False)
    monkeypatch.setattr(entry.host, "is_ios", lambda: False)
    monkeypatch.setattr(entry.sys, "platform", "win32")


def test_window_icon_is_ico_not_icns(windows_host):
    path = entry._window_icon_path()
    assert path is not None
    assert path.name == "rpncalc.ico"
    assert path.is_file()


def test_ico_still_has_the_windows_taskbar_sizes(qt_app):
    icon = QIcon(str(ROOT / "src/rpncalc/icons/rpncalc.ico"))
    sizes = {s.width() for s in icon.availableSizes()}
    assert {16, 32, 48, 256} <= sizes


def test_taskbar_identity_claims_the_windows_app_id(windows_host, monkeypatch):
    seen = {}

    class FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            seen["id"] = value

    class FakeWindll:
        shell32 = FakeShell32()

    monkeypatch.setattr(ctypes, "windll", FakeWindll(), raising=False)
    entry._claim_taskbar_identity()
    assert seen["id"] == "rpn-calc.rpncalc"


def test_windows_quits_with_its_window_too(windows_host, qt_app):
    # Not an Apple special case: nothing on any host may leave the process
    # running after the only window closes.
    assert qt_app.quitOnLastWindowClosed() is True


def test_backend_is_a_desktop_windows_host(windows_host, clean_settings):
    backend = Backend()
    assert backend.isMobile is False
    assert backend.hasPointerHover is True
    backend.saveWindowGeometry(100, 200, 420, 820, False)
    geo = backend.windowGeometry()
    assert geo["valid"] is True
    assert (geo["x"], geo["y"], geo["width"], geo["height"]) == (100, 200, 420, 820)
    assert geo["maximized"] is False


def test_text_scale_uses_windows_logpixels(qt_app, monkeypatch):
    monkeypatch.setattr(
        systemtheme,
        "_read_registry_dword",
        lambda key, name: 120 if name == "LogPixels" else None,
    )
    theme = SystemTheme()
    assert theme._detect_text_scale() == pytest.approx(1.25)


def test_launchkey_stays_winreg_and_pythonw():
    source = (ROOT / "src/rpncalc/launchkey.py").read_text(encoding="utf-8")
    assert "import winreg" in source
    assert "pythonw.exe" in source
    assert "AppKey\\18" in source
    if launchkey.supported():
        assert host.is_windows()
    else:
        assert not host.is_windows()


def test_qml_keeps_windows_ctrl_shortcuts_and_settings_panel():
    qml = (ROOT / "src/rpncalc/qml/Main.qml").read_text(encoding="utf-8")
    for seq in ("Ctrl+C", "Ctrl+V", "Ctrl+Z", "Ctrl+M", "Ctrl+Q", "Ctrl+,"):
        assert f'sequence: "{seq}"' in qml
    # Qt already maps Ctrl to Command on macOS. Binding Meta as well would
    # claim Super+Q and Super+M here, which the window manager owns.
    assert "Meta+" not in qml
    assert "SettingsView" in qml
    assert 'backend.pressCommand("settings")' in qml
    assert "hoverEnabled: backend.hasPointerHover" in qml
    settings = (ROOT / "src/rpncalc/qml/SettingsView.qml").read_text(encoding="utf-8")
    assert "Launch on the calculator key" not in settings  # label comes from backend
    assert "rowActivated" in settings


def test_pyinstaller_spec_still_builds_a_windows_exe():
    spec = (ROOT / "packaging/rpncalc.spec").read_text(encoding="utf-8")
    assert "rpncalc.ico" in spec
    assert "version_info.txt" in spec
    assert 'name = "rpncalc-debug" if DEBUG_BUILD else "rpncalc"' in spec
    assert 'if sys.platform == "win32":' in spec
    assert 'exe_kwargs["version"]' in spec
    # The Windows icon is the fallback when this is not a Mac.
    assert "elif ICON_ICO.is_file():" in spec


def test_pyinstaller_spec_defaults_to_the_folder_build():
    """One file is opt-in, because it costs ~3 s on every launch.

    The bootloader unpacks its payload to a new temporary directory each
    time, so the folder build is what meets the startup budget - and what a
    release ships, zipped, the way the .app already does.
    """
    spec = (ROOT / "packaging/rpncalc.spec").read_text(encoding="utf-8")
    assert 'ONEFILE_BUILD = os.environ.get("RPNCALC_BUILD_ONEFILE") == "1" and not MACOS' in spec
    assert "ONEDIR_BUILD = not ONEFILE_BUILD" in spec
    # A Mac must not be able to select one file: a folder is what goes inside
    # the .app bundle, and one-file .app is what Gatekeeper fights.
    assert "and not MACOS" in spec


def test_build_exe_windows_artifact_is_the_folder_and_its_zip():
    source = (ROOT / "tools/build_exe.py").read_text(encoding="utf-8")
    assert 'DIST / f"{stem}.exe"' in source
    assert "write_version_resource(version)" in source
    assert 'if sys.platform == "win32":' in source
    assert 'suffix = "windows" if sys.platform == "win32" else sys.platform' in source
    assert 'zip_folder(exe.parent, f"{stem}-{suffix}")' in source
    # macOS is a branch after the build; the Windows path is the default.
    assert 'app = DIST / ("rpn-calc-debug.app" if debug else "rpn-calc.app")' in source
    darwin_bundle = source.index("app = DIST / (\"rpn-calc-debug.app\"")
    exe_line = source.index('DIST / f"{stem}.exe"')
    assert exe_line > darwin_bundle


def test_zip_folder_keeps_the_folder_inside_the_archive(tmp_path):
    """Unzipping must produce `rpncalc/`, not a hundred loose Qt DLLs."""
    import zipfile
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import build_exe

    folder = tmp_path / "rpncalc"
    (folder / "_internal").mkdir(parents=True)
    (folder / "rpncalc.exe").write_bytes(b"MZ")
    (folder / "_internal" / "Qt6Core.dll").write_bytes(b"dll")

    archive = build_exe.zip_folder(folder, "rpncalc-windows")

    assert archive.name == "rpncalc-windows.zip"
    assert archive.parent == tmp_path
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
    assert "rpncalc/rpncalc.exe" in names
    assert "rpncalc/_internal/Qt6Core.dll" in names
    assert all(name.startswith("rpncalc/") for name in names)


def test_release_workflow_still_uploads_the_windows_build():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "dist/rpncalc-windows.zip" in workflow
    assert "artifacts/rpncalc-windows/rpncalc-windows.zip" in workflow
    test_workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "windows-latest" in test_workflow


def test_engine_layer_still_has_no_qt():
    for name in ("numeric.py", "stack.py", "rpn_engine.py", "alg_engine.py", "keymap.py"):
        text = (ROOT / "src/rpncalc" / name).read_text(encoding="utf-8")
        assert "PySide" not in text
        assert "from PySide" not in text
