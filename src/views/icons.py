"""
Theme-aware line icons for DotScramble.

Icons are tiny inline SVGs (24×24 grid, 2px round strokes) rendered in the
active theme's colors. Call `IconProvider.instance().set_colors(colors)` when
the theme changes and every widget bound through `bind_icon()` refreshes itself.
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel

# Path data only; the <svg> wrapper and stroke color are added at render time.
_PATHS: dict[str, str] = {
    # ── Actions ──────────────────────────────────────────────────────────────
    "open": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    "save": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
    "detect": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/>'
              '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>'
              '<circle cx="12" cy="12" r="3.5"/>',
    "compare": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 2v20"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/><path d="M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/><path d="M8 11h6"/>',
    "fit": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/>'
           '<path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "live": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "apply": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>'
             '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "batch": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "clear": '<path d="M7 21 3.5 17.5a2 2 0 0 1 0-2.8L13.2 5a2 2 0 0 1 2.8 0l3.5 3.5a2 2 0 0 1 0 2.8L9.5 21"/>'
             '<path d="M9 21h12"/><path d="m8.5 9.5 6 6"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3l-5.5 2.9 1-6.2L3 9.6l6.2-.9z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "chevron_down": '<path d="m6 9 6 6 6-6"/>',
    "chevron_right": '<path d="m9 6 6 6-6 6"/>',
    "chevron_left": '<path d="m15 6-6 6 6 6"/>',
    "drop": '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"/>'
            '<path d="M16 5h6M19 2v6"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3-3a2 2 0 0 0-2.8 0L6 21"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "camera": '<path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/>'
              '<circle cx="12" cy="13" r="3.5"/>',
    # ── Places (image picker) ────────────────────────────────────────────────
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11h14V9"/><path d="M10 20v-6h4v6"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "music": '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    "drive": '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M5.5 13 8 5h8l2.5 8"/><path d="M17 16.5h.01"/>',
    # ── Effects ──────────────────────────────────────────────────────────────
    "blur": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
    "pixelation": '<path d="M4 4h4v4H4zM12 4h4v4h-4zM8 8h4v4H8zM16 8h4v4h-4zM4 12h4v4H4zM12 12h4v4h-4zM8 16h4v4H8zM16 16h4v4h-4z" fill="{c}" stroke="none"/>',
    "black_bar": '<circle cx="12" cy="12" r="9"/><rect x="2" y="9" width="20" height="5" rx="1" fill="{c}"/>',
    "gradient": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 15 15 3M3 21 21 3M9 21l12-12"/>',
    "mosaic": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/>'
              '<rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>',
    "glass": '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9 3.5 3 2 3-2M9 20.5l3-2 3 2"/>',
    "oil_paint": '<path d="M18.4 2.6a2 2 0 0 1 2.9 2.9L12 14.8 9.2 12z"/>'
                 '<path d="M9 12.5c-2 0-3.5 1.5-3.5 3.5 0 1.5-1 2.5-2.5 3 1.5 1.5 4 2 6 1.5s3-2 3-4"/>',
    "ai_evasion": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "ai_evasion_invisible": '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1"/>'
                            '<path d="M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    # ── Detection modes ──────────────────────────────────────────────────────
    "face": '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0"/><path d="M9 9.5h.01M15 9.5h.01"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "body": '<circle cx="12" cy="4.5" r="2"/><path d="M12 7.5v7M7 10.5h10M9 22l3-7.5 3 7.5"/>',
    "license_plate": '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><path d="M3 12h18"/>'
                     '<circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 17h6"/>',
    "text": '<path d="M4 7V5h16v2M12 5v14M9 19h6"/>',
    "target_text": '<path d="M4 6h12M4 12h6M4 18h5"/><circle cx="16" cy="15" r="3.5"/><path d="m21 20-2.5-2.5"/>',
    "manual": '<path d="M4 8V4h4M12 4h3M20 8v2M4 12v3M4 19v1h4"/><path d="m13 13 8 3-3.5 1.5L16 21z"/>',
    "full": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
}

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')

_DEFAULT_COLORS = {
    "text_primary": "#ffffff",
    "text_secondary": "#cccccc",
    "text_disabled": "#808080",
    "accent_cyan": "#00bcd4",
    "accent_orange": "#ff9800",
    "on_accent": "#111111",
}


def _readable_on(hex_color: str) -> str:
    """Black or white — whichever is readable on `hex_color` (matches {on:key} in the QSS)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)

    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * channel(h[0:2]) + 0.7152 * channel(h[2:4]) + 0.0722 * channel(h[4:6])
    return "#ffffff" if (1.05 / (lum + 0.05)) >= ((lum + 0.05) / 0.05) else "#111111"


def _render(name: str, color: str, size: int) -> QPixmap:
    """Render one icon to a HiDPI-ready pixmap."""
    ratio = 2.0
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    body = _PATHS.get(name, "").replace("{c}", color)
    QSvgRenderer(QByteArray(_SVG.format(c=color, body=body).encode())).render(
        painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


class IconProvider(QObject):
    """Holds the active theme colors and notifies bound widgets when they change."""

    changed = Signal()
    _instance: "IconProvider | None" = None

    def __init__(self):
        super().__init__()
        self._colors = dict(_DEFAULT_COLORS)

    @classmethod
    def instance(cls) -> "IconProvider":
        if cls._instance is None:
            cls._instance = IconProvider()
        return cls._instance

    def set_colors(self, colors: dict) -> None:
        self._colors = {**_DEFAULT_COLORS, **colors}
        self._colors["on_accent"] = _readable_on(self._colors["accent_cyan"])
        self.changed.emit()

    def color(self, key: str) -> str:
        return self._colors[key]

    def pixmap(self, name: str, size: int, color_key: str = "text_secondary") -> QPixmap:
        return _render(name, self._colors[color_key], size)

    def icon(self, name: str, size: int = 18, tone: str = "text_primary") -> QIcon:
        """
        Build a QIcon with normal / disabled / checked variants.
        `tone` is the theme color key used for the normal state.
        """
        icon = QIcon()
        icon.addPixmap(_render(name, self._colors[tone], size), QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(_render(name, self._colors["accent_cyan"], size), QIcon.Mode.Normal, QIcon.State.On)
        disabled = _render(name, self._colors["text_disabled"], size)
        icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.Off)
        icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.On)
        return icon


def bind_icon(widget, name: str, size: int = 18, tone: str = "text_primary") -> None:
    """
    Give a button (or label) an icon that follows the theme.
    Calling it again on the same widget simply swaps the icon.
    """
    provider = IconProvider.instance()
    widget.setProperty("_icon_spec", (name, size, tone))

    def apply(w):
        spec_name, spec_size, spec_tone = w.property("_icon_spec")
        if isinstance(w, QAbstractButton):
            w.setIcon(provider.icon(spec_name, spec_size, spec_tone))
            w.setIconSize(QSize(spec_size, spec_size))
        elif isinstance(w, QLabel):
            w.setPixmap(_render(spec_name, provider.color(spec_tone), spec_size))

    apply(widget)
    if not widget.property("_icon_bound"):
        widget.setProperty("_icon_bound", True)
        ref = weakref.ref(widget)

        def refresh():
            w = ref()
            if w is not None:
                try:
                    apply(w)
                except RuntimeError:  # C++ object already deleted
                    pass

        provider.changed.connect(refresh)
