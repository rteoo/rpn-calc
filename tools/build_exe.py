"""Build the distributable desktop application.

    python tools/build_exe.py

Windows writes `dist/rpncalc.exe`. macOS writes `dist/rpn-calc.app`.
Needs the build extra: `pip install -e ".[build]"`.

    --onedir   a folder build that starts in a fraction of the time
               (macOS always produces a folder inside the .app)
    --debug    a console build that prints why it failed to start

The Windows version resource is generated here rather than committed, so
it cannot drift from the version in pyproject.toml.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"

VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Rodrigo Teodoro'),
        StringStruct('FileDescription', 'rpn-calc - HP 50g-style RPN calculator'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'rpncalc'),
        StringStruct('LegalCopyright',
                     'MIT. Derived from omacalc. iA Writer Mono S under OFL 1.1.'),
        StringStruct('OriginalFilename', 'rpncalc.exe'),
        StringStruct('ProductName', 'rpn-calc'),
        StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def write_version_resource(version: str) -> None:
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(p) if p.isdigit() else 0 for p in parts)
    (PACKAGING / "version_info.txt").write_text(
        VERSION_TEMPLATE.format(
            major=major, minor=minor, patch=patch, version=version
        ),
        encoding="utf-8",
    )


def adhoc_sign(app: Path) -> None:
    """Ad-hoc sign so `codesign -dv` succeeds and local `open` is less unhappy.

    Notarization needs a Developer ID and is a release-secret step, not this.
    `--deep` is what actually reaches the PyInstaller binaries inside the
    bundle; without it Gatekeeper still sees unsigned Mach-O in Helpers/.
    """
    subprocess.run(
        [
            "codesign",
            "--force",
            "--deep",
            "--sign", "-",
            "--timestamp=none",
            "--identifier", "io.github.rteoo.rpncalc",
            str(app),
        ],
        check=True,
    )


def zip_app(app: Path) -> Path:
    """Zip the bundle the way Finder does, preserving the .app package."""
    archive = app.parent / f"{app.name}.zip"
    archive.unlink(missing_ok=True)
    subprocess.run(
        ["ditto", "-c", "-k", "--keepParent", str(app), str(archive)],
        check=True,
    )
    return archive


def main() -> int:
    debug = "--debug" in sys.argv
    onedir = "--onedir" in sys.argv
    if debug:
        os.environ["RPNCALC_BUILD_DEBUG"] = "1"
    if onedir:
        os.environ["RPNCALC_BUILD_ONEDIR"] = "1"

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print('PyInstaller is missing. Run: pip install -e ".[build]"', file=sys.stderr)
        return 1

    icons = ROOT / "src" / "rpncalc" / "icons"
    if sys.platform == "darwin":
        if not (icons / "rpncalc.icns").exists():
            print("Icon missing. Run: python tools/make_icon.py", file=sys.stderr)
            return 1
    elif not (icons / "rpncalc.ico").exists():
        print("Icon missing. Run: python tools/make_icon.py", file=sys.stderr)
        return 1

    version = project_version()
    os.environ["RPNCALC_VERSION"] = version
    if sys.platform == "win32":
        write_version_resource(version)
    shape = "macOS app" if sys.platform == "darwin" else ("folder" if onedir else "one file")
    print(f"building rpn-calc {version} ({shape}{', debug console' if debug else ''})")

    # A stale build directory is the usual reason a change does not show up in
    # the executable, so start from nothing every time.
    for path in (DIST, ROOT / "build"):
        shutil.rmtree(path, ignore_errors=True)

    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            "--distpath", str(DIST),
            "--workpath", str(ROOT / "build"),
            str(PACKAGING / "rpncalc.spec"),
        ],
        cwd=ROOT,
    )
    if result.returncode != 0:
        return result.returncode

    stem = "rpncalc-debug" if debug else "rpncalc"
    if sys.platform == "darwin":
        app = DIST / "rpn-calc.app"
        if not app.is_dir():
            print("build reported success but produced no .app bundle", file=sys.stderr)
            return 1
        total = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
        print(f"\n{app}  ({total / 1_048_576:.1f} MB)")
        try:
            adhoc_sign(app)
            print("ad-hoc signed (not notarized; first-open is right-click → Open)")
        except subprocess.CalledProcessError as error:
            print(f"codesign failed: {error}", file=sys.stderr)
            return 1
        archive = zip_app(app)
        print(f"{archive}  ({archive.stat().st_size / 1_048_576:.1f} MB)")
        return 0

    exe = DIST / stem / f"{stem}.exe" if onedir else DIST / f"{stem}.exe"
    if sys.platform != "win32":
        # Linux (and anything else): the binary has no .exe suffix.
        candidate = DIST / stem / stem if onedir else DIST / stem
        if candidate.exists():
            exe = candidate
    if not exe.exists():
        print("build reported success but produced no executable", file=sys.stderr)
        return 1

    if onedir:
        total = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
        print(f"\n{exe.parent}  ({total / 1_048_576:.1f} MB in the folder)")
    else:
        print(f"\n{exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
