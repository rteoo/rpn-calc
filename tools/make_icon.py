"""Render the application icon.

Draws the calculator's own display: four stack levels, values right-aligned
against their level markers, with level 1 - the answer - picked out in the
faceplate's one warm colour. A calculator screen reads as a calculator at any
size; the bare stack lines the icon used to be read as a list.

The .ico it writes is committed, so a normal build needs no rendering step.
Run it only when the icon should change:

    python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "src" / "rpncalc" / "icons"
ICO_TARGET = ICONS / "rpncalc.ico"
PNG_TARGET = ICONS / "rpncalc.png"

# The right-shift orange from keymap.py, so the icon and the faceplate agree.
ACCENT = QColor("#e08a2e")
INK = QColor(242, 242, 242)

# The levels above the answer: width as a fraction of the screen, and how
# bright they are.  Irregular widths so they read as numbers rather than as a
# menu; brightness climbs towards level 1, the way attention does.
LEVELS = ((0.30, 95), (0.55, 140), (0.41, 185))
# Below 32px four rows turn to mud, so the small sizes show a shallower stack.
LEVELS_SMALL = ((0.44, 120), (0.62, 190))

# The sizes Windows actually asks for.  16/32/48 double as the favicon frames.
SIZES = (16, 24, 32, 48, 64, 128, 256)

PNG_SIZE = 256


def render(size: int) -> QImage:
    # Detail that survives at 32px and up; below that it is noise.
    detail = size >= 32
    glow = size >= 64

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # The body: a rounded slab, lit from above.
    inset = size * 0.035
    body = QPainterPath()
    body.addRoundedRect(
        QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
        size * 0.22,
        size * 0.22,
    )
    slab = QLinearGradient(0, inset, 0, size - inset)
    slab.setColorAt(0.0, QColor("#33333a"))
    slab.setColorAt(0.45, QColor("#17171a"))
    slab.setColorAt(1.0, QColor("#0b0b0d"))
    painter.fillPath(body, QBrush(slab))

    if detail:
        painter.save()
        painter.setClipPath(body)
        sheen = QLinearGradient(0, inset, 0, size * 0.42)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(0, 0, size, size * 0.42), QBrush(sheen))
        painter.restore()

    painter.setPen(QPen(QColor(255, 255, 255, 38), max(1.0, size * 0.008)))
    painter.drawPath(body)

    # The screen, inset into the body.
    margin = size * 0.145
    screen = QRectF(margin, size * 0.175, size - 2 * margin, size * 0.65)
    screen_path = QPainterPath()
    screen_path.addRoundedRect(screen, size * 0.05, size * 0.05)
    face = QLinearGradient(0, screen.top(), 0, screen.bottom())
    face.setColorAt(0.0, QColor("#08080a"))
    face.setColorAt(1.0, QColor("#151519"))
    painter.fillPath(screen_path, QBrush(face))
    if detail:
        painter.setPen(QPen(QColor(0, 0, 0, 160), max(1.0, size * 0.007)))
        painter.drawPath(screen_path)

    painter.setPen(Qt.NoPen)
    levels = LEVELS if detail else LEVELS_SMALL
    pad = screen.width() * 0.085

    # Fit the rows to the screen rather than to fixed pixel sizes, so the
    # shallower small-size stack fills the same space as the full one.
    rows = len(levels) + 1
    gap_ratio = 0.70 if detail else 0.62
    height = screen.height() * 0.78 / (rows + (rows - 1) * gap_ratio)
    gap = height * gap_ratio
    top = screen.center().y() - (rows * height + (rows - 1) * gap) / 2

    def pill(y: float, width: float, thickness: float, color: QColor) -> None:
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(
            QRectF(screen.right() - pad - width, y, width, thickness),
            thickness / 2,
            thickness / 2,
        )

    def marker(y: float, thickness: float, color: QColor) -> None:
        """The level label, abstracted to a dot. Dropped where it would blur."""
        if not detail:
            return
        diameter = thickness * 0.60
        painter.setBrush(QBrush(color))
        painter.drawEllipse(
            QRectF(screen.left() + pad, y + (thickness - diameter) / 2, diameter, diameter)
        )

    for index, (width, alpha) in enumerate(levels):
        y = top + index * (height + gap)
        pill(y, screen.width() * width, height, QColor(INK.red(), INK.green(), INK.blue(), alpha))
        marker(y, height, QColor(INK.red(), INK.green(), INK.blue(), 70))

    # Level 1: thicker and warm, so the eye lands on the answer first.
    answer_height = height * 1.20
    answer_y = top + len(levels) * (height + gap) - (answer_height - height) / 2
    answer_width = screen.width() * 0.68

    if glow:
        # The lit-segment halo, clipped to the screen: a radial brush fills its
        # whole bounding rect, which would otherwise spill past the corners.
        painter.save()
        painter.setClipPath(screen_path)
        halo = QRadialGradient(
            QPointF(screen.right() - pad - answer_width / 2, answer_y + answer_height / 2),
            answer_width * 0.55,
        )
        halo.setColorAt(0.0, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 34))
        halo.setColorAt(1.0, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 0))
        painter.fillRect(screen, QBrush(halo))
        painter.restore()

    pill(answer_y, answer_width, answer_height, ACCENT)
    marker(answer_y, answer_height, ACCENT)

    painter.end()
    return image


def encode_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def build_ico(frames: dict[int, bytes]) -> bytes:
    """Assemble a multi-resolution .ico from PNG-encoded frames.

    QImage cannot write one, so the container is built by hand. PNG frames are
    what every Windows since Vista reads, and what keeps 256px affordable.
    """
    out = BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for size, payload in frames.items():
        # 256 is stored as 0: the field is one byte wide.
        dimension = 0 if size >= 256 else size
        out.write(
            struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset)
        )
        offset += len(payload)
    for payload in frames.values():
        out.write(payload)
    return out.getvalue()


def main() -> int:
    QGuiApplication(sys.argv)  # QImage and QPainter need one

    ICONS.mkdir(parents=True, exist_ok=True)

    frames = {size: encode_png(render(size)) for size in SIZES}
    ICO_TARGET.write_bytes(build_ico(frames))
    print(f"wrote {ICO_TARGET} ({ICO_TARGET.stat().st_size} bytes, {len(SIZES)} sizes)")

    # The PNG is what a .desktop entry and the web want; .ico is Windows-only.
    PNG_TARGET.write_bytes(frames[PNG_SIZE] if PNG_SIZE in frames else encode_png(render(PNG_SIZE)))
    print(f"wrote {PNG_TARGET} ({PNG_TARGET.stat().st_size} bytes, {PNG_SIZE}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
