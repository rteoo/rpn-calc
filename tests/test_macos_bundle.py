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
