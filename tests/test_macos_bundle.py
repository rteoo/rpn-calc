"""macOS bundle inspection. No Qt, no launch — those live in --smoke."""

from __future__ import annotations

import importlib.util
import plistlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "smoke_macos", ROOT / "tools" / "smoke_macos.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()


def _write_bundle(root: Path, *, bundle_id: str = "io.github.rteoo.rpncalc") -> Path:
    app = root / "rpn-calc.app"
    macos = app / "Contents" / "MacOS"
    resources = app / "Contents" / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir()
    (macos / "rpncalc").write_bytes(b"\x00")
    (resources / "rpncalc.icns").write_bytes(b"icns")
    info = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleExecutable": "rpncalc",
        "CFBundleShortVersionString": "0.2.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    }
    with (app / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    return app


def test_a_well_formed_bundle_is_accepted(tmp_path):
    app = _write_bundle(tmp_path)
    details = smoke.inspect_app(app)
    assert details["bundle_id"] == "io.github.rteoo.rpncalc"
    assert Path(details["executable"]).name == "rpncalc"
    assert Path(details["icon"]).suffix == ".icns"


def test_the_wrong_bundle_id_is_refused(tmp_path):
    app = _write_bundle(tmp_path, bundle_id="com.example.wrong")
    with pytest.raises(smoke.BundleError, match="CFBundleIdentifier"):
        smoke.inspect_app(app)


def test_a_missing_icon_is_refused(tmp_path):
    app = _write_bundle(tmp_path)
    next(app.joinpath("Contents/Resources").glob("*.icns")).unlink()
    with pytest.raises(smoke.BundleError, match="icns"):
        smoke.inspect_app(app)


def test_a_bare_directory_is_refused(tmp_path):
    with pytest.raises(smoke.BundleError, match="not an .app"):
        smoke.inspect_app(tmp_path / "not-an-app")


def test_skip_launch_reports_ok_on_any_host(tmp_path):
    app = _write_bundle(tmp_path)
    assert smoke.main([str(app), "--skip-launch"]) == 0


def _load_build() -> object:
    spec = importlib.util.spec_from_file_location(
        "build_exe", ROOT / "tools" / "build_exe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNestedCode:
    """What `codesign` has to reach before it seals the bundle.

    `--deep` used to stand in for this walk. Apple deprecated it for signing
    and a notarized build cannot use it, so the ordering is tested here rather
    than discovered on a release day.
    """

    def _bundle(self, tmp_path: Path) -> Path:
        app = _write_bundle(tmp_path)
        frameworks = app / "Contents" / "Frameworks"
        (frameworks / "QtCore.framework" / "Versions" / "A").mkdir(parents=True)
        (frameworks / "QtCore.framework" / "Versions" / "A" / "QtCore").write_bytes(b"\x00")
        (frameworks / "QtCore.framework" / "Versions" / "A" / "inner.dylib").write_bytes(b"\x00")
        (frameworks / "libpyside6.dylib").write_bytes(b"\x00")
        (frameworks / "PySide6" / "QtCore.abi3.so").parent.mkdir(parents=True)
        (frameworks / "PySide6" / "QtCore.abi3.so").write_bytes(b"\x00")
        (app / "Contents" / "MacOS" / "Python").write_bytes(b"\x00")
        (app / "Contents" / "Resources" / "qml.txt").write_text("not code")
        return app

    def test_it_finds_the_code_and_not_the_data(self, tmp_path):
        build = _load_build()
        found = {p.name for p in build.nested_code(self._bundle(tmp_path))}
        assert "libpyside6.dylib" in found
        assert "QtCore.abi3.so" in found
        assert "Python" in found  # a helper binary with no suffix
        assert "rpncalc" in found  # the main executable, skipped when signing
        assert "qml.txt" not in found

    def test_a_framework_is_sealed_as_a_unit(self, tmp_path):
        build = _load_build()
        found = build.nested_code(self._bundle(tmp_path))
        names = [p.name for p in found]
        assert "QtCore.framework" in names
        # Its inner binary must not be signed separately: signing the
        # framework afterwards would invalidate it.
        assert not any(".framework" in str(p) and p.name != "QtCore.framework" for p in found)

    def test_deepest_paths_are_signed_first(self, tmp_path):
        build = _load_build()
        depths = [len(p.parts) for p in build.nested_code(self._bundle(tmp_path))]
        assert depths == sorted(depths, reverse=True)

    def test_the_main_executable_is_read_from_the_plist(self, tmp_path):
        build = _load_build()
        assert build.bundle_executable(_write_bundle(tmp_path)) == "rpncalc"
