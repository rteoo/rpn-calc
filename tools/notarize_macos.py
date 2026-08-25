"""Notarize and staple the macOS bundle.

    python tools/notarize_macos.py dist/rpn-calc.app

Needs a Developer ID signature already on the bundle (`RPNCALC_CODESIGN_IDENTITY`
during `tools/build_exe.py`) and three credentials in the environment:

    APPLE_ID            the Apple ID that owns the Developer Program membership
    APPLE_TEAM_ID       the 10-character team identifier
    APPLE_APP_PASSWORD  an app-specific password, not the account password

Apple notarizes an archive but Gatekeeper reads the ticket off the bundle, so
the order is: zip, submit, staple the .app, zip again. The zip that ships is
the second one - the first never carries the ticket.

The judging is split from the running (`credentials`, `submit_command`,
`submission_verdict`, `signature_verdict`) so every branch of this gate is
unit-tested off a Mac. A release step that only ever executes on the release
runner is not tested at all.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ID = "io.github.rteoo.rpncalc"
CREDENTIAL_VARS = ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")


class NotarizeError(Exception):
    """A refusal. `submission_id` is set once Apple has one to look up by."""

    def __init__(self, message: str, submission_id: str = "") -> None:
        super().__init__(message)
        self.submission_id = submission_id


def credentials(env: dict[str, str]) -> dict[str, str]:
    """The three notarytool credentials, or a message naming what is missing."""
    found = {name: env.get(name, "").strip() for name in CREDENTIAL_VARS}
    missing = [name for name, value in found.items() if not value]
    if missing:
        raise NotarizeError(f"missing credentials: {', '.join(missing)}")
    return found


def signature_verdict(returncode: int, blob: str) -> str:
    """Refuse a bundle Apple will reject, before spending the upload.

    An ad-hoc signature has no team behind it and notarization declines it
    with a message about the signing certificate that reads like a keychain
    problem. Say the real thing here instead.
    """
    if returncode != 0:
        raise NotarizeError(blob.strip() or "codesign -dv failed; is the bundle signed?")
    if "Signature=adhoc" in blob or "flags=0x2(adhoc)" in blob:
        raise NotarizeError(
            "bundle is ad-hoc signed; notarization needs a Developer ID "
            "(set RPNCALC_CODESIGN_IDENTITY and rebuild)"
        )
    for line in blob.splitlines():
        if line.startswith("Authority=") and "Developer ID Application" in line:
            return line.strip()
    raise NotarizeError("no Developer ID Application authority in the signature")


def submit_command(archive: Path, creds: dict[str, str]) -> list[str]:
    """The notarytool argv. The password reaches it as an argument, not a file.

    `--wait` blocks until Apple decides, which is what makes this a gate
    rather than a fire-and-forget upload.
    """
    return [
        "xcrun", "notarytool", "submit", str(archive),
        "--apple-id", creds["APPLE_ID"],
        "--team-id", creds["APPLE_TEAM_ID"],
        "--password", creds["APPLE_APP_PASSWORD"],
        "--wait",
        "--output-format", "json",
    ]


def submission_verdict(returncode: int, stdout: str) -> str:
    """The submission id, or the reason this build must not ship.

    notarytool exits non-zero for a rejected submission *and* for a network
    failure, and prints JSON for the first but not always the second, so the
    payload is what decides - the exit code alone cannot tell them apart.
    """
    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError):
        raise NotarizeError(
            f"notarytool returned {returncode} and no JSON: {stdout.strip() or '(empty)'}"
        ) from None
    status = str(payload.get("status", "")).strip()
    submission_id = str(payload.get("id", "")).strip()
    if status != "Accepted":
        message = payload.get("message") or "no message"
        raise NotarizeError(
            f"notarization {status or 'failed'} ({message})",
            submission_id=submission_id,
        )
    return submission_id


def zip_app(app: Path, archive: Path) -> Path:
    """Zip the bundle the way Finder does, preserving the .app package."""
    archive.unlink(missing_ok=True)
    subprocess.run(
        ["ditto", "-c", "-k", "--keepParent", str(app), str(archive)],
        check=True,
    )
    return archive


def check_signature(app: Path) -> str:
    result = subprocess.run(
        ["codesign", "-dv", "--verbose=2", str(app)],
        capture_output=True,
        text=True,
    )
    # codesign -dv writes to stderr.
    return signature_verdict(result.returncode, result.stderr + result.stdout)


def submit(archive: Path, creds: dict[str, str]) -> str:
    result = subprocess.run(
        submit_command(archive, creds), capture_output=True, text=True
    )
    try:
        return submission_verdict(result.returncode, result.stdout)
    except NotarizeError:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        raise


def notarization_log(submission_id: str, creds: dict[str, str]) -> str:
    """Why Apple said no. Without this the failure is an id and nothing else."""
    result = subprocess.run(
        [
            "xcrun", "notarytool", "log", submission_id,
            "--apple-id", creds["APPLE_ID"],
            "--team-id", creds["APPLE_TEAM_ID"],
            "--password", creds["APPLE_APP_PASSWORD"],
        ],
        capture_output=True,
        text=True,
    )
    return (result.stdout + result.stderr).strip()


def staple(app: Path) -> None:
    subprocess.run(["xcrun", "stapler", "staple", str(app)], check=True)
    # Stapling can report success and leave a ticket Gatekeeper will not read.
    subprocess.run(["xcrun", "stapler", "validate", str(app)], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="path to rpn-calc.app")
    args = parser.parse_args(argv)

    app = args.app.resolve()
    if app.suffix != ".app" or not app.is_dir():
        print(f"NOTARIZE_FAIL: {app} is not an .app bundle", file=sys.stderr)
        return 1

    creds: dict[str, str] = {}
    try:
        creds = credentials(dict(os.environ))
        print(f"SIGN {check_signature(app)}")
        with tempfile.TemporaryDirectory() as scratch:
            upload = zip_app(app, Path(scratch) / "submission.zip")
            print(f"submitting {upload.stat().st_size / 1_048_576:.1f} MB to Apple")
            submission_id = submit(upload, creds)
        print(f"ACCEPTED id={submission_id}")
        staple(app)
    except NotarizeError as error:
        print(f"NOTARIZE_FAIL: {error}", file=sys.stderr)
        if error.submission_id:
            print(notarization_log(error.submission_id, creds), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"NOTARIZE_FAIL: {error}", file=sys.stderr)
        return 1

    # The shipped zip has to be made after stapling: the ticket lives in the
    # bundle, and the archive Apple saw does not have one.
    archive = zip_app(app, app.parent / f"{app.name}.zip")
    print(f"STAPLED {archive}  ({archive.stat().st_size / 1_048_576:.1f} MB)")
    print("NOTARIZE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
