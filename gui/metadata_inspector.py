"""
DotScramble — "What's in this photo?" (PySide6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lists every metadata field and hidden part the opened photo carries, with its value.
Read-only, and free for everyone: knowing what a photo gives away comes before removing it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core import metadata_writer
from gui.metadata_report import describe_before
from src.managers.localization_manager import get_locale_manager
from src.views.widgets import caption

OSM_URL = "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


class MetadataInspectorDialog(QDialog):
    def __init__(self, parent=None, *, exif: dict | None, extras: dict | None, filename: str = ""):
        super().__init__(parent)
        self.setWindowTitle(_t("metadata.inspector.window_title"))
        self.setMinimumSize(560, 420)
        self.resize(600, 500)
        # "keep" with untouched pixels lists exactly what the file has today
        self._changes = metadata_writer.make_plan(exif, "keep", ext=".jpg", extras=extras,
                                                  pixels_upright=False).changes
        self._gps = metadata_writer.gps_of(exif)
        self._build(filename)

    def _build(self, filename):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)
        title = QLabel(_t("metadata.inspector.title"))
        title.setObjectName("DialogTitle")
        hdr_layout.addWidget(title)
        if filename:
            short = filename if len(filename) <= 32 else "…" + filename[-29:]
            hdr_layout.addWidget(caption(short), alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        if not self._changes:
            grid.addWidget(caption(_t("metadata.inspector.empty")), 0, 0, 1, 2)
        else:
            if self._gps:
                warn = QLabel(_t("metadata.inspector.has_location"))
                warn.setProperty("role", "danger-item")
                warn.setWordWrap(True)
                grid.addWidget(warn, 0, 0, 1, 2)
            for row, change in enumerate(self._changes, start=1):
                label = QLabel(_t(f"metadata.fields.{change.key}"))
                label.setProperty("role", "field-label")
                grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
                value = QLabel(change.before if change.key not in ("thumbnail", "xmp", "iptc", "extra_images", "icc")
                               else describe_before(change))
                value.setProperty("role", "field-value")
                value.setWordWrap(True)
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(value, row, 1)
            grid.setColumnStretch(1, 1)
            hint = caption(_t("metadata.inspector.hint"))
            hint.setWordWrap(True)
            grid.addWidget(hint, len(self._changes) + 1, 0, 1, 2)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QFrame()
        buttons.setObjectName("btn_frame")
        b_layout = QHBoxLayout(buttons)
        b_layout.setContentsMargins(20, 10, 20, 10)
        if self._gps:
            map_btn = QPushButton(_t("metadata.inspector.map"))
            map_btn.setProperty("variant", "ghost")
            map_btn.setToolTip(_t("metadata.inspector.map_tip"))
            map_btn.clicked.connect(self._open_map)
            b_layout.addWidget(map_btn)
        b_layout.addStretch(1)
        close = QPushButton(_t("metadata.inspector.close"))
        close.setObjectName("primary_action")
        close.clicked.connect(self.accept)
        b_layout.addWidget(close)
        layout.addWidget(buttons)

    def _open_map(self):
        lat, lon = self._gps
        QDesktopServices.openUrl(QUrl(OSM_URL.format(lat=f"{lat:.6f}", lon=f"{lon:.6f}")))
