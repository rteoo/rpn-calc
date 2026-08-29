"""Developer ID signing and notarization, judged off a Mac.

`codesign` and `notarytool` only exist on macOS, so what is tested here is
every decision the release gate makes: which flags a signature carries, what
counts as an accepted submission, and what has to be refused before the
upload. A release step that only ever executes on the release runner has
never been tested.
"""

from __future__ import annotations

import importlib.util
import plistlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("build_exe")
notarize = _load("notarize_macos")

DEVELOPER_ID = "Developer ID Application: Rodrigo Teodoro (ABCDE12345)"


class TestSigningIdentity:
    def test_no_environment_means_ad_hoc(self, monkeypatch):
        monkeypatch.delenv("RPNCALC_CODESIGN_IDENTITY", raising=False)
        assert build.signing_identity() == "-"

    def test_an_empty_secret_means_ad_hoc(self, monkeypatch):
        # A workflow that forwards a secret nobody set hands us "".
        monkeypatch.setenv("RPNCALC_CODESIGN_IDENTITY", "   ")
        assert build.signing_identity() == "-"

    def test_a_developer_id_is_used_verbatim(self, monkeypatch):
        monkeypatch.setenv("RPNCALC_CODESIGN_IDENTITY", DEVELOPER_ID)
        assert build.signing_identity() == DEVELOPER_ID


class TestCodesignCommand:
    def test_ad_hoc_stays_out_of_the_hardened_runtime(self):
        command = build.codesign_command(Path("libpyside6.dylib"), "-")
        assert "--options" not in command
        assert "--entitlements" not in command
        assert "--timestamp=none" in command

    def test_a_developer_id_gets_runtime_entitlements_and_a_timestamp(self):
        command = build.codesign_command(Path("libpyside6.dylib"), DEVELOPER_ID)
        assert command[:4] == ["codesign", "--force", "--sign", DEVELOPER_ID]
        assert "--timestamp" in command
        assert "--timestamp=none" not in command
        assert command[command.index("--options") + 1] == "runtime"
        entitlements = Path(command[command.index("--entitlements") + 1])
        assert entitlements.is_file(), "the entitlements file must ship in the repo"

    def test_only_the_bundle_claims_the_identifier(self):
        nested = build.codesign_command(Path("QtCore.framework"), DEVELOPER_ID)
        bundle = build.codesign_command(Path("rpn-calc.app"), DEVELOPER_ID)
        assert "--identifier" not in nested
        assert bundle[bundle.index("--identifier") + 1] == "io.github.rteoo.rpncalc"

    def test_the_target_is_the_last_argument(self):
        for identity in ("-", DEVELOPER_ID):
            assert build.codesign_command(Path("a.dylib"), identity)[-1] == "a.dylib"


class TestSignsInsideOut:
    """The bundle is sealed last, and the main executable only once."""

    def test_the_order_is_deepest_first_and_the_bundle_last(self, tmp_path, monkeypatch):
        app = tmp_path / "rpn-calc.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Frameworks").mkdir()
        (app / "Contents" / "MacOS" / "rpncalc").write_bytes(b"\x00")
        (app / "Contents" / "Frameworks" / "libpyside6.dylib").write_bytes(b"\x00")
        with (app / "Contents" / "Info.plist").open("wb") as handle:
            plistlib.dump({"CFBundleExecutable": "rpncalc"}, handle)

        calls: list[list[str]] = []
        monkeypatch.setattr(
            build.subprocess, "run", lambda command, **kw: calls.append(command)
        )
        build.sign_app(app, DEVELOPER_ID)

        targets = [Path(call[-1]).name for call in calls]
        assert targets == ["libpyside6.dylib", "rpn-calc.app"]
        # The main executable is covered by the bundle's own signature.
        assert "rpncalc" not in targets


class TestCredentials:
    def test_all_three_are_required(self):
        with pytest.raises(notarize.NotarizeError, match="APPLE_TEAM_ID"):
            notarize.credentials({"APPLE_ID": "a@b.c", "APPLE_APP_PASSWORD": "x"})

    def test_a_blank_value_is_a_missing_value(self):
        with pytest.raises(notarize.NotarizeError, match="APPLE_APP_PASSWORD"):
            notarize.credentials(
                {
                    "APPLE_ID": "a@b.c",
                    "APPLE_TEAM_ID": "ABCDE12345",
                    "APPLE_APP_PASSWORD": " ",
                }
            )

    def test_a_full_set_is_returned(self):
        env = {
            "APPLE_ID": "a@b.c ",
            "APPLE_TEAM_ID": "ABCDE12345",
            "APPLE_APP_PASSWORD": "pw",
        }
        assert notarize.credentials(env)["APPLE_ID"] == "a@b.c"

    def test_the_submission_waits_for_a_verdict(self):
        creds = notarize.credentials(
            {
                "APPLE_ID": "a@b.c",
                "APPLE_TEAM_ID": "ABCDE12345",
                "APPLE_APP_PASSWORD": "pw",
            }
        )
        command = notarize.submit_command(Path("app.zip"), creds)
        assert command[:3] == ["xcrun", "notarytool", "submit"]
        assert command[command.index("--password") + 1] == "pw"
        assert "--wait" in command, "without --wait this is not a gate"
        assert command[command.index("--output-format") + 1] == "json"


class TestSignatureVerdict:
    def test_an_unsigned_bundle_is_refused(self):
        with pytest.raises(notarize.NotarizeError, match="not signed"):
            notarize.signature_verdict(1, "code object is not signed at all")

    def test_a_silent_failure_still_reports_something(self):
        with pytest.raises(notarize.NotarizeError, match="codesign -dv failed"):
            notarize.signature_verdict(1, "   ")

    def test_ad_hoc_is_refused_before_the_upload(self):
        blob = "Identifier=io.github.rteoo.rpncalc\nSignature=adhoc\n"
        with pytest.raises(notarize.NotarizeError, match="ad-hoc"):
            notarize.signature_verdict(0, blob)

    def test_another_certificate_is_not_a_developer_id(self):
        blob = "Authority=Apple Development: someone (X)\n"
        with pytest.raises(notarize.NotarizeError, match="Developer ID"):
            notarize.signature_verdict(0, blob)

    def test_a_developer_id_passes(self):
        blob = f"Identifier=io.github.rteoo.rpncalc\nAuthority={DEVELOPER_ID}\n"
        assert notarize.signature_verdict(0, blob) == f"Authority={DEVELOPER_ID}"


class TestSubmissionVerdict:
    def test_accepted_returns_the_id(self):
        payload = '{"id": "abc-123", "status": "Accepted", "message": "Received"}'
        assert notarize.submission_verdict(0, payload) == "abc-123"

    def test_invalid_is_a_failure_carrying_the_id_for_the_log(self):
        payload = '{"id": "abc-123", "status": "Invalid", "message": "Package Invalid"}'
        with pytest.raises(notarize.NotarizeError) as caught:
            notarize.submission_verdict(1, payload)
        assert "Invalid" in str(caught.value)
        assert caught.value.submission_id == "abc-123"

    def test_a_zero_exit_with_a_bad_status_still_fails(self):
        # The payload decides, not the exit code: they disagree.
        payload = '{"id": "abc-123", "status": "Rejected"}'
        with pytest.raises(notarize.NotarizeError, match="Rejected"):
            notarize.submission_verdict(0, payload)

    def test_a_network_failure_prints_what_it_got(self):
        with pytest.raises(notarize.NotarizeError, match="could not connect"):
            notarize.submission_verdict(1, "error: could not connect")

    def test_no_output_at_all_is_still_a_readable_failure(self):
        with pytest.raises(notarize.NotarizeError, match=r"\(empty\)"):
            notarize.submission_verdict(70, "")


class TestEntryPoint:
    def test_something_that_is_not_a_bundle_is_refused(self, tmp_path, capsys):
        assert notarize.main([str(tmp_path / "nope.app")]) == 1
        assert "not an .app bundle" in capsys.readouterr().err

    def test_missing_credentials_fail_before_anything_runs(
        self, tmp_path, monkeypatch, capsys
    ):
        app = tmp_path / "rpn-calc.app"
        app.mkdir()
        for name in notarize.CREDENTIAL_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(
            notarize,
            "check_signature",
            lambda app: pytest.fail("ran before the credential check"),
        )
        assert notarize.main([str(app)]) == 1
        assert "missing credentials" in capsys.readouterr().err

    def test_a_failure_rebuilding_the_stapled_archive_is_reported(
        self, tmp_path, monkeypatch, capsys
    ):
        app = tmp_path / "rpn-calc.app"
        app.mkdir()
        for name in notarize.CREDENTIAL_VARS:
            monkeypatch.setenv(name, "configured")

        monkeypatch.setattr(notarize, "check_signature", lambda _app: "Developer ID")
        monkeypatch.setattr(notarize, "submit", lambda _archive, _creds: "abc-123")
        monkeypatch.setattr(notarize, "staple", lambda _app: None)
        calls = 0

        def zip_twice(_app, _archive):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise subprocess.CalledProcessError(1, "ditto")
            _archive.write_bytes(b"zip")
            return _archive

        monkeypatch.setattr(notarize, "zip_app", zip_twice)

        assert notarize.main([str(app)]) == 1
        captured = capsys.readouterr()
        assert "NOTARIZE_FAIL" in captured.err
        assert "Traceback" not in captured.err
        assert calls == 2

    def test_success_rebuilds_the_archive_after_stapling(
        self, tmp_path, monkeypatch, capsys
    ):
        app = tmp_path / "rpn-calc.app"
        app.mkdir()
        for name in notarize.CREDENTIAL_VARS:
            monkeypatch.setenv(name, "configured")

        monkeypatch.setattr(notarize, "check_signature", lambda _app: "Developer ID")
        monkeypatch.setattr(notarize, "submit", lambda _archive, _creds: "abc-123")
        events = []
        monkeypatch.setattr(notarize, "staple", lambda _app: events.append("staple"))

        def zip_record(_app, archive):
            events.append("zip")
            archive.write_bytes(b"zip")
            return archive

        monkeypatch.setattr(notarize, "zip_app", zip_record)

        assert notarize.main([str(app)]) == 0
        assert events == ["zip", "staple", "zip"]
        assert "NOTARIZE_OK" in capsys.readouterr().out
