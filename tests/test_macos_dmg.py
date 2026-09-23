"""macOS disk image layout and commands. hdiutil itself runs in the macos-app job."""

from __future__ import annotations

import importlib.util
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_make_dmg():
    spec = importlib.util.spec_from_file_location("make_dmg", ROOT / "tools" / "make_dmg.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_dmg = _load_make_dmg()


def _bundle(root: Path, version: str = "0.6.4") -> Path:
    app = root / "rpn-calc.app"
    (app / "Contents").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": version}, handle)
    return app


def test_image_is_named_for_the_bundle_version_beside_it(tmp_path):
    app = _bundle(tmp_path, "1.2.3")
    assert make_dmg.dmg_path(app) == tmp_path / "rpncalc-1.2.3.dmg"


def test_staging_renames_the_app_and_links_applications(tmp_path, monkeypatch):
    app = _bundle(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    calls, links = [], []
    monkeypatch.setattr(make_dmg.subprocess, "run", lambda cmd, check: calls.append(cmd))
    monkeypatch.setattr(make_dmg.os, "symlink", lambda src, dst: links.append((src, dst)))

    target = make_dmg.stage(app, staging)

    assert target == staging / "RPN Calc.app"
    assert calls == [["ditto", str(app), str(target)]]
    assert links == [("/Applications", staging / "Applications")]


def test_create_command_builds_a_compressed_named_volume(tmp_path):
    image = tmp_path / "rpncalc-0.6.4.dmg"
    command = make_dmg.create_command(tmp_path / "staging", image)
    assert command[:2] == ["hdiutil", "create"]
    assert command[command.index("-volname") + 1] == "RPN Calc"
    assert command[command.index("-srcfolder") + 1] == str(tmp_path / "staging")
    assert command[command.index("-format") + 1] == "UDZO"
    assert command[-1] == str(image)


def test_make_dmg_creates_then_verifies_the_image(tmp_path, monkeypatch):
    app = _bundle(tmp_path)
    calls = []
    monkeypatch.setattr(make_dmg.subprocess, "run", lambda cmd, check: calls.append(cmd))
    monkeypatch.setattr(make_dmg.os, "symlink", lambda src, dst: None)

    image = make_dmg.make_dmg(app)

    assert image == tmp_path / "rpncalc-0.6.4.dmg"
    assert [cmd[:2] for cmd in calls] == [
        ["ditto", str(app)],
        ["hdiutil", "create"],
        ["hdiutil", "verify"],
    ]
    assert calls[-1] == ["hdiutil", "verify", str(image)]


def test_main_refuses_a_non_mac_host(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(make_dmg.sys, "platform", "win32")
    assert make_dmg.main([str(_bundle(tmp_path))]) == 1
    assert "needs macOS" in capsys.readouterr().err


def test_main_refuses_a_path_that_is_not_a_bundle(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(make_dmg.sys, "platform", "darwin")
    assert make_dmg.main([str(tmp_path / "missing.app")]) == 1
    assert "not an app bundle" in capsys.readouterr().err


def test_main_reports_a_failed_hdiutil(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(make_dmg.sys, "platform", "darwin")

    def fail(cmd, check):
        raise make_dmg.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(make_dmg.subprocess, "run", fail)
    assert make_dmg.main([str(_bundle(tmp_path))]) == 1
    assert "disk image failed" in capsys.readouterr().err


def test_workflows_build_smoke_and_publish_the_dmg():
    test_workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "python tools/make_dmg.py dist/rpn-calc.app" in test_workflow
    assert 'python tools/smoke_macos.py "$mount/RPN Calc.app"' in test_workflow

    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # The image must be made from the stapled bundle, so after notarization.
    assert release.index("tools/notarize_macos.py") < release.index("tools/make_dmg.py")
    assert "dist/rpncalc-*.dmg" in release
    assert "artifacts/rpn-calc-macos/rpncalc-*.dmg" in release
