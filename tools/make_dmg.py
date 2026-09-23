"""Wrap a finished macOS bundle in a drag-to-install disk image.

    python tools/make_dmg.py dist/rpn-calc.app

Writes `dist/rpncalc-<version>.dmg`, the version read from the bundle's
Info.plist. The image holds the app as `RPN Calc.app` beside a link to
/Applications. Renaming the bundle directory leaves its signature intact:
codesign seals the contents, not the folder name.

Run it after signing and, for a release, after `tools/notarize_macos.py`.
The stapled ticket lives inside the bundle, so the image carries it along.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "RPN Calc"


def bundle_version(app: Path) -> str:
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        return plistlib.load(handle)["CFBundleShortVersionString"]


def dmg_path(app: Path) -> Path:
    return app.parent / f"rpncalc-{bundle_version(app)}.dmg"


def stage(app: Path, staging: Path) -> Path:
    """Lay out the image's contents: the renamed app and an Applications link."""
    target = staging / f"{APP_NAME}.app"
    # ditto keeps the symlinks, extended attributes and stapled ticket that a
    # plain copy can drop from a framework-laden bundle.
    subprocess.run(["ditto", str(app), str(target)], check=True)
    os.symlink("/Applications", staging / "Applications")
    return target


def create_command(staging: Path, image: Path) -> list[str]:
    return [
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(staging),
        "-fs", "HFS+",
        "-format", "UDZO",
        "-ov",
        str(image),
    ]


def make_dmg(app: Path) -> Path:
    image = dmg_path(app)
    with tempfile.TemporaryDirectory() as scratch:
        staging = Path(scratch) / "staging"
        staging.mkdir()
        stage(app, staging)
        subprocess.run(create_command(staging, image), check=True)
    subprocess.run(["hdiutil", "verify", str(image)], check=True)
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", type=Path, help="path to rpn-calc.app")
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        print("make_dmg needs macOS: hdiutil and ditto are Apple tools", file=sys.stderr)
        return 1
    if not (args.app / "Contents" / "Info.plist").is_file():
        print(f"{args.app} is not an app bundle", file=sys.stderr)
        return 1
    try:
        image = make_dmg(args.app)
    except subprocess.CalledProcessError as error:
        print(f"disk image failed: {error}", file=sys.stderr)
        return 1
    print(f"{image}  ({image.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
