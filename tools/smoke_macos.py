"""Inspect and launch a macOS .app the way a user would.

    python tools/smoke_macos.py dist/rpn-calc.app
    python tools/smoke_macos.py --source

Refuses `QT_QPA_PLATFORM=offscreen`. A passing `start()` under that plugin
is not this test — see issue #15 and AGENTS.md.

The bundle checks (Info.plist, icon, executable) run on any host so the
parser can be unit-tested. Launching the binary is macOS-only.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ID = "io.github.rteoo.rpncalc"


class BundleError(Exception):
    pass


def inspect_app(app: Path) -> dict[str, object]:
    """Read what Finder and Gatekeeper read. No Qt, no launch."""
    if app.suffix != ".app" or not app.is_dir():
        raise BundleError(f"{app} is not an .app bundle")

    info_path = app / "Contents" / "Info.plist"
    if not info_path.is_file():
        raise BundleError("Contents/Info.plist is missing")
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)

    bundle_id = info.get("CFBundleIdentifier")
    if bundle_id != BUNDLE_ID:
        raise BundleError(f"CFBundleIdentifier is {bundle_id!r}, expected {BUNDLE_ID!r}")

    if info.get("NSHighResolutionCapable") not in (True, "true", 1):
        raise BundleError("NSHighResolutionCapable is not set")
    if info.get("NSRequiresAquaSystemAppearance") not in (False, "false", 0, None):
        raise BundleError("NSRequiresAquaSystemAppearance must allow Dark Mode")

    executable = info.get("CFBundleExecutable")
    binary = app / "Contents" / "MacOS" / str(executable or "")
    if not executable or not binary.is_file():
        raise BundleError(f"Contents/MacOS/{executable} is missing")

    resources = app / "Contents" / "Resources"
    icns = list(resources.glob("*.icns")) if resources.is_dir() else []
    if not icns:
        raise BundleError("no .icns in Contents/Resources")

    return {
        "bundle_id": bundle_id,
        "executable": str(binary),
        "icon": str(icns[0]),
        "version": info.get("CFBundleShortVersionString"),
        "high_dpi": True,
    }


def codesign_identity(app: Path) -> str:
    result = subprocess.run(
        ["codesign", "-dv", "--verbose=2", str(app)],
        capture_output=True,
        text=True,
    )
    # codesign -dv writes to stderr. An unsigned bundle exits non-zero.
    blob = result.stderr + result.stdout
    if result.returncode != 0 and "code object is not signed" in blob:
        raise BundleError("bundle is not signed")
    for line in blob.splitlines():
        if line.startswith("Identifier="):
            identifier = line.split("=", 1)[1].strip()
            if identifier and identifier != BUNDLE_ID:
                raise BundleError(
                    f"codesign Identifier is {identifier!r}, expected {BUNDLE_ID!r}"
                )
        if line.startswith("Authority=") or "Signature=adhoc" in line or "flags=0x2(adhoc)" in line:
            return line.strip()
    if result.returncode != 0:
        raise BundleError(blob.strip() or "codesign -dv failed")
    return "signed"


def launch_smoke(binary: Path) -> int:
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    result = subprocess.run(
        [str(binary), "--smoke"],
        cwd=ROOT,
        env=env,
    )
    return result.returncode


def source_smoke() -> int:
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    return subprocess.run(
        [sys.executable, "-m", "rpncalc", "--smoke"],
        cwd=ROOT,
        env=env,
    ).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "app",
        nargs="?",
        type=Path,
        help="path to rpn-calc.app (omit with --source)",
    )
    parser.add_argument(
        "--source",
        action="store_true",
        help="launch `python -m rpncalc --smoke` instead of a bundle",
    )
    parser.add_argument(
        "--skip-launch",
        action="store_true",
        help="only inspect the bundle; do not run the binary",
    )
    args = parser.parse_args(argv)

    if args.source:
        if sys.platform != "darwin":
            print("source smoke is macOS-only (needs cocoa)", file=sys.stderr)
            return 1
        return source_smoke()

    if args.app is None:
        parser.error("pass dist/rpn-calc.app or --source")

    app = args.app.resolve()
    try:
        details = inspect_app(app)
        print(
            "BUNDLE "
            f"id={details['bundle_id']} "
            f"exe={details['executable']} "
            f"icon={details['icon']} "
            f"version={details['version']}"
        )
        if sys.platform == "darwin" and not args.skip_launch:
            identity = codesign_identity(app)
            print(f"SIGN {identity}")
    except BundleError as error:
        print(f"SMOKE_FAIL: {error}", file=sys.stderr)
        return 1

    if args.skip_launch:
        print("SMOKE_OK")
        return 0
    if sys.platform != "darwin":
        print("launch is macOS-only; bundle checks passed", file=sys.stderr)
        return 0
    return launch_smoke(Path(str(details["executable"])))


if __name__ == "__main__":
    raise SystemExit(main())
