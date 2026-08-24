r"""The keyboard's dedicated calculator key.

These tests drive the real registry rather than a mock of it, because the part
worth testing *is* the registry round-trip - whether a value written as REG_SZ
reads back byte-identical, and whether releasing the key leaves somebody else's
binding alone. They point `launchkey` at a scratch subkey first: the live
`AppKey\18` is the user's actual desktop setting, and a test run has no
business rewriting it.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rpncalc import launchkey  # noqa: E402

windows_only = pytest.mark.skipif(
    not launchkey.supported(), reason="the calculator key is a Windows binding"
)

_SCRATCH_KEY = r"Software\rpncalc-tests\AppKey\18"


@pytest.fixture
def scratch_key(monkeypatch):
    """Redirect the binding at a subkey this test run owns, and sweep up."""
    import winreg

    monkeypatch.setattr(launchkey, "APP_KEY_PATH", _SCRATCH_KEY)
    yield
    for path in (
        _SCRATCH_KEY,
        r"Software\rpncalc-tests\AppKey",
        r"Software\rpncalc-tests",
    ):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


class TestLaunchCommand:
    def test_a_frozen_build_names_its_own_executable(self, monkeypatch):
        monkeypatch.setattr(launchkey.sys, "frozen", True, raising=False)
        monkeypatch.setattr(launchkey.sys, "executable", r"C:\apps\rpncalc.exe")
        assert launchkey.launch_command() == r'"C:\apps\rpncalc.exe"'

    def test_a_source_checkout_prefers_the_windowless_interpreter(
        self, monkeypatch, tmp_path
    ):
        # A console interpreter would flash a window on every press.
        (tmp_path / "python.exe").write_text("")
        (tmp_path / "pythonw.exe").write_text("")
        monkeypatch.delattr(launchkey.sys, "frozen", raising=False)
        monkeypatch.setattr(launchkey.sys, "executable", str(tmp_path / "python.exe"))
        assert launchkey.launch_command() == f'"{tmp_path / "pythonw.exe"}" -m rpncalc'

    def test_a_source_checkout_falls_back_when_pythonw_is_absent(
        self, monkeypatch, tmp_path
    ):
        interpreter = tmp_path / "python3"
        interpreter.write_text("")
        monkeypatch.delattr(launchkey.sys, "frozen", raising=False)
        monkeypatch.setattr(launchkey.sys, "executable", str(interpreter))
        assert launchkey.launch_command() == f'"{interpreter}" -m rpncalc'

    def test_the_command_is_quoted_against_spaces_in_the_path(self, monkeypatch):
        monkeypatch.setattr(launchkey.sys, "frozen", True, raising=False)
        monkeypatch.setattr(launchkey.sys, "executable", r"C:\Program Files\r.exe")
        assert launchkey.launch_command().startswith('"')
        assert launchkey.launch_command().endswith('"')


@windows_only
class TestBinding:
    def test_nothing_is_bound_to_begin_with(self, scratch_key):
        assert launchkey.is_bound() is False

    def test_binding_round_trips(self, scratch_key):
        launchkey.bind()
        assert launchkey.is_bound() is True
        assert launchkey._read() == launchkey.launch_command()

    def test_binding_twice_is_the_same_as_binding_once(self, scratch_key):
        launchkey.bind()
        launchkey.bind()
        assert launchkey.is_bound() is True

    def test_unbinding_releases_the_key(self, scratch_key):
        launchkey.bind()
        launchkey.unbind()
        assert launchkey.is_bound() is False
        assert launchkey._read() is None

    def test_unbinding_without_a_binding_is_a_no_op(self, scratch_key):
        launchkey.unbind()  # must not raise on a key that does not exist
        assert launchkey.is_bound() is False

    def test_another_application_keeps_the_key(self, scratch_key):
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SCRATCH_KEY) as key:
            winreg.SetValueEx(key, "ShellExecute", 0, winreg.REG_SZ, "someone-else.exe")

        # Not ours, so we neither claim it nor delete it.
        assert launchkey.is_bound() is False
        launchkey.unbind()
        assert launchkey._read() == "someone-else.exe"

    def test_binding_takes_the_key_over_from_another_application(self, scratch_key):
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SCRATCH_KEY) as key:
            winreg.SetValueEx(key, "ShellExecute", 0, winreg.REG_SZ, "someone-else.exe")

        launchkey.bind()
        assert launchkey.is_bound() is True

    def test_a_non_string_value_is_not_read_as_a_binding(self, scratch_key):
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SCRATCH_KEY) as key:
            winreg.SetValueEx(key, "ShellExecute", 0, winreg.REG_DWORD, 1)

        assert launchkey._read() is None
        assert launchkey.is_bound() is False


class TestWithoutARegistry:
    """The Linux side of the port, which must stay silent rather than crash."""

    @pytest.fixture(autouse=True)
    def no_winreg(self, monkeypatch):
        monkeypatch.setattr(launchkey, "winreg", None)

    def test_it_reports_itself_unsupported(self):
        assert launchkey.supported() is False

    def test_nothing_reads_as_bound(self):
        assert launchkey.is_bound() is False
        assert launchkey._read() is None

    def test_releasing_the_key_is_a_no_op(self):
        launchkey.unbind()

    def test_binding_says_why_it_cannot(self):
        with pytest.raises(OSError, match="Windows"):
            launchkey.bind()


@windows_only
class TestThroughTheBackend:
    @pytest.fixture
    def backend(self, qt_app, clean_settings, scratch_key):
        from rpncalc.backend import Backend

        return Backend()

    def test_the_toggle_binds_and_releases(self, backend):
        assert backend.calculatorKeySupported is True
        assert backend.calculatorKeyBound is False

        backend.setCalculatorKeyBound(True)
        assert backend.calculatorKeyBound is True
        assert launchkey.is_bound() is True

        backend.setCalculatorKeyBound(False)
        assert backend.calculatorKeyBound is False

    def test_toggling_notifies_qml(self, backend):
        seen = []
        backend.calculatorKeyChanged.connect(lambda: seen.append(True))
        backend.setCalculatorKeyBound(True)
        assert seen

    def test_a_refused_write_is_reported_and_survived(
        self, backend, monkeypatch, capsys
    ):
        def refuse() -> None:
            raise OSError("access is denied")

        monkeypatch.setattr(launchkey, "bind", refuse)
        backend.setCalculatorKeyBound(True)  # must not propagate

        assert backend.calculatorKeyBound is False  # the tick springs back
        assert "could not rebind the calculator key" in capsys.readouterr().err

    def test_the_toggle_reflects_a_binding_made_outside_the_app(self, backend):
        launchkey.bind()
        assert backend.calculatorKeyBound is True
