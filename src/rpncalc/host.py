"""Which host this process is running on.

Stdlib only: the same split `launchkey.py` already follows. The calculation
core does not care about the OS; the window, the theme, and the packaging do.

`sys.platform` is `"ios"` on Python 3.13+ (PEP 730). Older embeddings
(BeeWare, Python-Apple-support) still report `"darwin"` and have to be
recognised by the machine name or the iOS deployment target baked into the
interpreter.
"""

from __future__ import annotations

import platform
import sys
import sysconfig


def is_windows() -> bool:
    return sys.platform == "win32"


def is_ios() -> bool:
    if sys.platform in ("ios", "tvos", "watchos"):
        return True
    if sys.platform != "darwin":
        return False
    machine = platform.machine() or ""
    if machine.startswith(("iPhone", "iPad", "iPod")):
        return True
    return bool(sysconfig.get_config_var("IPHONEOS_DEPLOYMENT_TARGET"))


def is_macos() -> bool:
    return sys.platform == "darwin" and not is_ios()


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_mobile() -> bool:
    """A phone or tablet: no window chrome, no geometry to remember."""
    return is_ios() or sys.platform.startswith("android")


def remembers_window_geometry() -> bool:
    return not is_mobile()


def has_pointer_hover() -> bool:
    """Whether keycaps should react to the cursor sitting on them.

    Touch-only hosts still construct the MouseArea; they just never see a
    hover. This flag is for QML that wants to skip the affordance entirely.
    """
    return not is_mobile()
