#!/usr/bin/env python3
"""
Render the DotScramble app icon from its SVG sources into every PNG
the app and the Linux packaging use.

    python build_icons.py

Sources: assets/icons/dotscramble.svg (48px and up) and
assets/icons/dotscramble-small.svg (16–32px, simplified to stay legible).
"""
import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ICONS = Path(__file__).resolve().parent / "assets" / "icons"
SVG_FULL = ICONS / "dotscramble.svg"
SVG_SMALL = ICONS / "dotscramble-small.svg"
SMALL_MAX = 32

# Fixed-name files referenced by src/main.py, build.py and the snap metadata
NAMED = {
    ICONS / "Square150x150Logo.png": 150,
    ICONS / "Square44x44Logo.png": 44,
    ICONS / "StoreLogo.png": 50,
    ICONS / "icon.png": 1024,
    ICONS.parent.parent / "meta" / "gui" / "icon.png": 256,
}
# Multi-size set for the window/taskbar icon (QIcon picks the best fit)
PNG_SET = [16, 24, 32, 48, 64, 128, 256, 512]


def render(size: int) -> Image.Image:
    svg = SVG_SMALL if size <= SMALL_MAX else SVG_FULL
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(str(svg)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main():
    QGuiApplication(sys.argv)
    cache = {}

    def get(size):
        if size not in cache:
            cache[size] = render(size)
        return cache[size]

    for path, size in NAMED.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        get(size).save(path, optimize=True)
        print(f"  {path.relative_to(ICONS.parent.parent)}  {size}px")

    png_dir = ICONS / "png"
    png_dir.mkdir(exist_ok=True)
    for size in PNG_SET:
        get(size).save(png_dir / f"dotscramble-{size}.png", optimize=True)
    print(f"  assets/icons/png/dotscramble-{{{','.join(map(str, PNG_SET))}}}.png")


if __name__ == "__main__":
    main()
