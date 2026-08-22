"""Render the application icon.

Draws a miniature of the calculator's own face - a stack with level 1 picked
out - so the taskbar icon says "RPN stack" at a glance rather than "generic
calculator". Run it only when the icon should change; the .ico it writes is
committed so a normal build needs no rendering step.

    python tools/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
)

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "src" / "rpncalc" / "fonts" / "iAWriterMonoS-Bold.ttf"
TARGET = ROOT / "packaging" / "rpncalc.ico"

# The dark palette from backend.py, so the icon and the app agree.
PAGE = QColor("#101010")
INK = QColor("#eeeeee")
ACCENT = QColor("#e08a2e")  # the right-shift orange, the face's one warm colour

# Sizes Windows actually asks for.
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int, family: str) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Rounded body.
    body = QPainterPath()
    inset = size * 0.04
    body.addRoundedRect(
        QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
        size * 0.22,
        size * 0.22,
    )
    painter.fillPath(body, QBrush(PAGE))
    painter.setPen(QColor(255, 255, 255, 28))
    painter.drawPath(body)

    # Three stack lines, the bottom one accented: level 1, where the answer is.
    rows = 3
    line_height = size * 0.085
    gap = size * 0.075
    block = rows * line_height + (rows - 1) * gap
    top = (size - block) / 2 + size * 0.03
    right = size - size * 0.22
    for row in range(rows):
        y = top + row * (line_height + gap)
        is_level_one = row == rows - 1
        width = size * (0.30 if row == 0 else 0.42 if row == 1 else 0.52)
        painter.setBrush(QBrush(ACCENT if is_level_one else INK))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(right - width, y, width, line_height),
            line_height / 2,
            line_height / 2,
        )
        # The level tick on the left, dropped at small sizes where it is mud.
        if size >= 32:
            tick = size * 0.055
            painter.setBrush(QBrush(INK if is_level_one else QColor(238, 238, 238, 120)))
            painter.drawEllipse(
                QRectF(size * 0.19, y + (line_height - tick) / 2, tick, tick)
            )

    painter.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - QImage/QPainter need one

    family = "iA Writer Mono S"
    if FONT.exists():
        font_id = QFontDatabase.addApplicationFont(str(FONT))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    QFont(family)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    images = [render(size, family) for size in SIZES]

    # QImage cannot write a multi-resolution .ico, so assemble the container by
    # hand from PNG-encoded frames, which every modern Windows reads.
    import struct
    from io import BytesIO

    from PySide6.QtCore import QBuffer, QByteArray

    frames = []
    for image in images:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QBuffer.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        frames.append(bytes(data))

    out = BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for size, payload in zip(SIZES, frames):
        dimension = 0 if size >= 256 else size
        out.write(
            struct.pack(
                "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset
            )
        )
        offset += len(payload)
    for payload in frames:
        out.write(payload)

    TARGET.write_bytes(out.getvalue())
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes, {len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
