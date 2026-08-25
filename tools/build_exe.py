"""Build the distributable desktop application.

    python tools/build_exe.py

Windows writes `dist/rpncalc/` and zips it to `dist/rpncalc-windows.zip`.
macOS writes `dist/rpn-calc.app` and its zip. Needs the build extra:
`pip install -e ".[build]"`.

    --onefile  a single .exe instead of the folder. Convenient to hand to
               someone, but it unpacks its whole payload to a new temporary
               directory on every launch: 4.0 s to a window against 0.8 s
               for the folder. Ignored on macOS.
    --debug    a console build that prints why it failed to start

On macOS the bundle is ad-hoc signed unless RPNCALC_CODESIGN_IDENTITY names a
Developer ID, which switches on Hardened Runtime and the entitlements
notarization requires. `tools/notarize_macos.py` is the step after that.

The Windows version resource is generated here rather than committed, so
it cannot drift from the version in pyproject.toml.
"""

from __future__ import annotations

import os
import plistlib
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


# Mach-O by extension. PyInstaller lays the Qt libraries and the extension
# modules out beside the executable; every one of them is code and has to
# carry its own signature.
NESTED_CODE_SUFFIXES = (".dylib", ".so")


def nested_code(app: Path) -> list[Path]:
    """Everything inside the bundle that has to be signed before the bundle is.

    Deepest first: a signature covers the contents of what it seals, so a
    framework signed after its parent invalidates the parent. This is what
    `--deep` used to paper over - Apple deprecated it for signing, and a
    notarized build has to do the walk properly anyway.
    """
    contents = app / "Contents"
    found: set[Path] = set()
    for path in contents.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in NESTED_CODE_SUFFIXES:
            found.add(path)
    # Bundled frameworks are sealed as a unit, not file by file.
    for framework in contents.rglob("*.framework"):
        if framework.is_dir():
            found = {p for p in found if framework not in p.parents}
            found.add(framework)
    # The helper binaries in Contents/MacOS have no suffix to recognise them
    # by; the main executable is signed last, with the bundle.
    macos = contents / "MacOS"
    if macos.is_dir():
        for path in macos.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix == "":
                found.add(path)
    return sorted(found, key=lambda p: (-len(p.parts), str(p)))


def bundle_executable(app: Path) -> str:
    """The CFBundleExecutable name, which a debug build changes."""
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        return str(plistlib.load(handle)["CFBundleExecutable"])


ADHOC_IDENTITY = "-"
BUNDLE_ID = "io.github.rteoo.rpncalc"
ENTITLEMENTS = PACKAGING / "macos" / "rpncalc.entitlements"


def signing_identity() -> str:
    """The codesign identity: a Developer ID from the environment, or ad-hoc.

    Set by the release workflow once the certificate is in a keychain. An
    empty value is the same as an absent one, because a workflow that
    forwards a missing secret hands us the empty string.
    """
    return os.environ.get("RPNCALC_CODESIGN_IDENTITY", "").strip() or ADHOC_IDENTITY


def codesign_command(target: Path, identity: str) -> list[str]:
    """The argv for one `codesign` call.

    An ad-hoc signature is for a local build and cannot be notarized, so it
    skips Hardened Runtime: enabling it without a Developer ID only buys the
    library-validation crashes it exists to prevent. A real identity gets the
    runtime, the entitlements PyInstaller's CPython needs under it, and a
    secure timestamp - notarization rejects a signature without one.
    """
    adhoc = identity == ADHOC_IDENTITY
    command = ["codesign", "--force", "--sign", identity]
    command += ["--timestamp=none"] if adhoc else ["--timestamp"]
    if not adhoc:
        command += ["--options", "runtime", "--entitlements", str(ENTITLEMENTS)]
    if target.suffix == ".app":
        command += ["--identifier", BUNDLE_ID]
    command.append(str(target))
    return command


def sign_app(app: Path, identity: str = ADHOC_IDENTITY) -> None:
    """Sign inside out, so `codesign -dv` succeeds on the bundle.

    A signature covers the contents of what it seals, so the bundle is signed
    last. This is what `--deep` used to paper over; Apple deprecated it for
    signing and notarization will not accept it.
    """
    main_executable = app / "Contents" / "MacOS" / bundle_executable(app)
    for target in nested_code(app):
        if target == main_executable:
            continue
        subprocess.run(codesign_command(target, identity), check=True)
    subprocess.run(codesign_command(app, identity), check=True)


def zip_app(app: Path) -> Path:
    """Zip the bundle the way Finder does, preserving the .app package."""
    archive = app.parent / f"{app.name}.zip"
    archive.unlink(missing_ok=True)
    subprocess.run(
        ["ditto", "-c", "-k", "--keepParent", str(app), str(archive)],
        check=True,
    )
    return archive


def zip_folder(folder: Path, archive_stem: str) -> Path:
    """Zip a folder build for release, keeping the folder itself inside.

    The archive holds `rpncalc/...` rather than the loose files, so unzipping
    cannot scatter a hundred-odd Qt DLLs across whatever directory the user
    happened to be sitting in.
    """
    archive = folder.parent / f"{archive_stem}.zip"
    archive.unlink(missing_ok=True)
    shutil.make_archive(
        str(archive.with_suffix("")),
        "zip",
        root_dir=str(folder.parent),
        base_dir=folder.name,
    )
    return archive


def main() -> int:
    debug = "--debug" in sys.argv
    # A folder is the default: one file costs about three extra seconds on
    # every launch, and a release ships the folder zipped anyway.
    onefile = "--onefile" in sys.argv and sys.platform != "darwin"
    onedir = not onefile
    if debug:
        os.environ["RPNCALC_BUILD_DEBUG"] = "1"
    if onefile:
        os.environ["RPNCALC_BUILD_ONEFILE"] = "1"

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
        app = DIST / ("rpn-calc-debug.app" if debug else "rpn-calc.app")
        if not app.is_dir():
            print("build reported success but produced no .app bundle", file=sys.stderr)
            return 1
        total = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
        print(f"\n{app}  ({total / 1_048_576:.1f} MB)")
        identity = signing_identity()
        try:
            sign_app(app, identity)
        except subprocess.CalledProcessError as error:
            print(f"codesign failed: {error}", file=sys.stderr)
            return 1
        if identity == ADHOC_IDENTITY:
            print("ad-hoc signed (not notarized; first-open is right-click → Open)")
        else:
            print(f"signed with {identity} (hardened runtime)")
            print("notarize next: python tools/notarize_macos.py dist/rpn-calc.app")
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
        # The folder is what starts fast; the zip is what a release attaches.
        # Named for the host it was built on, because a Linux folder is not a
        # Windows one and a release should not have to guess which it got.
        suffix = "windows" if sys.platform == "win32" else sys.platform
        archive = zip_folder(exe.parent, f"{stem}-{suffix}")
        print(f"{archive}  ({archive.stat().st_size / 1_048_576:.1f} MB zipped)")
    else:
        print(f"\n{exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
