r"""Bind the keyboard's dedicated calculator key to this calculator.

A keyboard's calculator key is not a hotkey the application can grab: Windows
delivers it to Explorer as `VK_LAUNCH_APP2`, and Explorer resolves it through
`HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18`. A
`ShellExecute` value there overrides the built-in mapping to the Calculator
app, and removing the value hands the key straight back. HKLM carries the same
subkey with empty values, so the per-user override has nothing to outrank.

The binding names the build that wrote it - the frozen executable, or the
interpreter plus `-m rpncalc` from a source checkout - so a checkout and an
installed copy each recognise only their own binding. Turning the toggle on
from either one re-points the key at that build.

Stdlib only, no Qt, and inert on platforms without a registry: keeping the
Windows integration out of `backend.py` is the same split `systemtheme.py`
already follows.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows platforms
    winreg = None  # type: ignore[assignment]

# AppKey 18 is VK_LAUNCH_APP2, the usage a calculator key emits over plain HID.
APP_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18"
_SHELL_EXECUTE = "ShellExecute"


def launch_command() -> str:
    """The command line that starts this build.

    Explorer passes the value to `ShellExecuteEx`, which honours arguments, so
    a source checkout can register itself without a launcher script.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    # A console interpreter would flash a window on every press; pythonw sits
    # beside it in the same environment and has the same packages.
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    if windowless.is_file():
        interpreter = windowless
    return f'"{interpreter}" -m rpncalc'


def supported() -> bool:
    """Whether the calculator key can be rebound on this platform."""
    return winreg is not None


def is_bound() -> bool:
    """Whether the calculator key currently starts this build."""
    return _read() == launch_command()


def bind() -> None:
    """Point the calculator key at this build.

    Raises `OSError` if the registry refuses the write - the caller decides
    whether that is worth taking the application down for.
    """
    if winreg is None:
        raise OSError("the calculator key can only be rebound on Windows")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_KEY_PATH) as key:
        winreg.SetValueEx(key, _SHELL_EXECUTE, 0, winreg.REG_SZ, launch_command())


def unbind() -> None:
    """Hand the calculator key back to Windows.

    A value pointing somewhere else belongs to another application and is left
    untouched; releasing a key this build does not hold is not this build's
    business.
    """
    if winreg is None or not is_bound():
        return
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, APP_KEY_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.DeleteValue(key, _SHELL_EXECUTE)


def _read() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, _SHELL_EXECUTE)
    except OSError:
        return None
    return value if isinstance(value, str) else None
