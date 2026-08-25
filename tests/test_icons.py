"""The committed icon files, including the Apple containers."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "src" / "rpncalc" / "icons"


def test_icns_is_a_well_formed_icon_family():
    payload = (ICONS / "rpncalc.icns").read_bytes()
    assert payload[:4] == b"icns"
    declared = struct.unpack(">I", payload[4:8])[0]
    assert declared == len(payload)
    offset = 8
    types = []
    while offset < len(payload):
        ostype = payload[offset : offset + 4].decode("ascii")
        length = struct.unpack(">I", payload[offset + 4 : offset + 8])[0]
        assert length >= 8
        types.append(ostype)
        offset += length
    assert offset == len(payload)
    assert "ic08" in types  # 256px, what the Dock reaches for
    assert "ic10" in types  # 1024px, what a Retina Dock reaches for


def test_ios_app_icon_is_opaque_png():
    from PySide6.QtGui import QGuiApplication, QImage

    QGuiApplication.instance() or QGuiApplication([])
    image = QImage(str(ICONS / "rpncalc-1024.png"))
    assert not image.isNull()
    assert image.width() == image.height() == 1024
    # App Store icons must not carry an alpha hole. Every corner pixel is painted.
    for x, y in ((0, 0), (1023, 0), (0, 1023), (1023, 1023)):
        assert image.pixelColor(x, y).alpha() == 255


def test_build_icns_rejects_a_bad_type():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "make_icon", ROOT / "tools" / "make_icon.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="four characters"):
        module.build_icns({"too-long": b"not-a-png"})
