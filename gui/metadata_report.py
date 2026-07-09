"""
DotScramble — Metadata Save Report Dialog (PySide6 version)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shows a quick summary of what metadata actions will be applied
before the user confirms the save operation.
"""
from __future__ import annotations

import sys
import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt

from src.config import COLORS

# ── Human-readable summaries ──────────────────────────────────────────────────
_PROFILE_SUMMARY = {
    "ghost":  ("👻 Ghost Profile",  "Nokia 3310 · Antarctica GPS · Year 2000 timestamp"),
    "troll":  ("🌊 Troll Profile",  "Random vintage camera · Random ocean GPS · Recent-ish date"),
    "artist": ("🎨 Artist Profile", "Hides GPS & camera device · Keeps copyright field"),
    "custom": ("⚙️ Custom Profile", "Per-field rules (see details below)"),
}

_ACTION_ICONS = {
    "keep":  ("✅", "#4CAF50", "Kept as-is"),
    "strip": ("🗑", "#F44336", "Stripped / removed"),
    "spoof": ("🎲", "#2196F3", "Replaced with fake data"),
}

_FIELD_LABELS = {
    "gps":       "📍 GPS Location",
    "make":      "📷 Camera Make",
    "model":     "📷 Camera Model",
    "software":  "💻 Software",
    "datetime":  "🕐 Date / Time",
    "copyright": "©️  Copyright",
    "exposure":  "🔆 Exposure Data",
}


def _describe_action(key: str, action, action_colors) -> tuple[str, str, str]:
    """Return (icon, color, description) for a field action."""
    if isinstance(action, dict):
        if key == "gps":
            lat = action.get("lat", "?")
            lon = action.get("lon", "?")
            return ("✏️", action_colors.get("custom", "#FF9800"), f"Custom GPS: {lat}, {lon}")
        val = action.get("value", "")
        return ("✏️", action_colors.get("custom", "#FF9800"), f"Custom value: '{val[:30]}'" if val else "Custom (empty → spoof)")
    icon, _, desc = _ACTION_ICONS.get(action, ("❓", "#888", action))
    return icon, action_colors.get(action, "#888888"), desc


class MetadataReportDialog(QDialog):
    """
    Pre-save confirmation dialog.
    """

    def __init__(
        self,
        parent=None,
        *,
        mode: str,                        # "scrub" | "spoof" | "restore"
        profile: str | None = None,       # ghost / troll / artist / custom
        field_actions: dict | None = None,
        filename: str = "",
    ):
        super().__init__(parent)
        self.confirmed = False

        # Get active colors from parent or default
        if parent and hasattr(parent, 'colors'):
            self.colors = parent.colors
        else:
            self.colors = COLORS

        self.action_colors = {
            "keep":   self.colors.get('accent_green', '#4CAF50'),
            "strip":  self.colors.get('accent_red', '#F44336'),
            "spoof":  self.colors.get('accent_cyan', '#2196F3'),
            "custom": self.colors.get('accent_orange', '#FF9800'),
        }
        
        self.setWindowTitle("DotScramble — Confirm Save")
        self.setMinimumSize(520, 460)
        self.resize(520, 460)

        self._build(mode, profile, field_actions, filename)

    def _build(self, mode, profile, field_actions, filename):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)

        title_lbl = QLabel("📋  Metadata Summary")
        title_lbl.setObjectName("DialogTitle")
        title_lbl_font = title_lbl.font()
        title_lbl_font.setPointSize(14)
        title_lbl_font.setBold(True)
        title_lbl.setFont(title_lbl_font)
        hdr_layout.addWidget(title_lbl)

        if filename:
            short = filename if len(filename) <= 32 else "…" + filename[-29:]
            fn_lbl = QLabel(short)
            fn_lbl.setObjectName("preset_lbl")
            fn_lbl_font = fn_lbl.font()
            fn_lbl_font.setPointSize(10)
            fn_lbl_font.setItalic(True)
            fn_lbl.setFont(fn_lbl_font)
            hdr_layout.addWidget(fn_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(hdr)

        # ── Mode banner ───────────────────────────────────────────────────────
        if mode == "scrub":
            banner_text  = "🗑  All metadata will be STRIPPED"
            banner_color = self.action_colors["strip"]
            banner_desc  = "GPS, camera model, timestamps and all other EXIF data will be permanently removed."
        elif mode == "restore":
            banner_text  = "✅  Original metadata will be PRESERVED"
            banner_color = self.action_colors["keep"]
            banner_desc  = "The image's original EXIF data will be restored exactly as it was."
        else:   # spoof
            pname, pdesc = _PROFILE_SUMMARY.get(profile or "ghost", ("🎲 Spoof", ""))
            banner_text  = f"🎭  Metadata will be SPOOFED  ({pname})"
            banner_color = self.action_colors["spoof"]
            banner_desc  = pdesc

        banner = QFrame()
        banner.setStyleSheet(f"background-color: {banner_color}; border-radius: 6px; border: none; margin: 10px;")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(20, 10, 20, 10)
        banner_layout.setSpacing(4)

        b_title = QLabel(banner_text)
        b_title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        banner_layout.addWidget(b_title)

        b_desc = QLabel(banner_desc)
        b_desc.setStyleSheet("color: white; font-style: italic; font-size: 11px;")
        b_desc.setWordWrap(True)
        banner_layout.addWidget(b_desc)

        main_layout.addWidget(banner)

        # ── Detail area ───────────────────────────────────────────────────────
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(20, 15, 20, 15)

        if mode == "spoof" and field_actions:
            lbl = QLabel("Field-by-field actions:")
            lbl.setObjectName("preset_lbl")
            lbl_font = lbl.font()
            lbl_font.setBold(True)
            lbl_font.setPointSize(11)
            lbl.setFont(lbl_font)
            detail_layout.addWidget(lbl)

            for key, action in field_actions.items():
                label = _FIELD_LABELS.get(key, key)
                icon, color, desc = _describe_action(key, action, self.action_colors)

                row = QFrame()
                row.setObjectName("card_frame")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 6, 10, 6)

                field_lbl = QLabel(label)
                field_lbl_font = field_lbl.font()
                field_lbl_font.setBold(True)
                field_lbl.setFont(field_lbl_font)
                row_layout.addWidget(field_lbl, 1)

                act_lbl = QLabel(f"{icon} {desc}")
                act_lbl.setStyleSheet(f"background-color: {color}; color: white; border-radius: 3px; padding: 2px 8px; font-size: 11px;")
                row_layout.addWidget(act_lbl)

                detail_layout.addWidget(row)

        elif mode == "scrub":
            lbl = QLabel("The following data will be permanently removed:")
            lbl.setObjectName("preset_lbl")
            lbl_font = lbl.font()
            lbl_font.setBold(True)
            lbl_font.setPointSize(11)
            lbl.setFont(lbl_font)
            detail_layout.addWidget(lbl)

            items = ["📍 GPS coordinates", "📷 Camera make & model",
                     "💻 Software identifier", "🕐 Timestamps",
                     "©️  Copyright", "🔆 Exposure data", "🔒 Device fingerprint"]
            for item in items:
                item_lbl = QLabel(f"  🗑  {item}")
                item_lbl.setStyleSheet(f"color: {self.colors.get('accent_red', '#ef9a9a')}; font-weight: bold; font-size: 12px; padding: 2px 0;")
                detail_layout.addWidget(item_lbl)
        else:
            # restore or simple spoof without custom fields
            if mode == "spoof" and profile in _PROFILE_SUMMARY:
                _, pdesc = _PROFILE_SUMMARY[profile]
                desc_lbl = QLabel(pdesc)
                desc_lbl.setObjectName("preset_lbl")
                desc_lbl_font = desc_lbl.font()
                desc_lbl_font.setItalic(True)
                desc_lbl_font.setPointSize(11)
                desc_lbl.setFont(desc_lbl_font)
                desc_lbl.setWordWrap(True)
                detail_layout.addWidget(desc_lbl)
            else:
                detail_layout.addStretch(1)

        detail_layout.addStretch(1)
        main_layout.addWidget(detail_widget, 1)

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_frame = QFrame()
        btn_frame.setObjectName("btn_frame")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 10, 20, 10)

        btn_layout.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("💾  Save")
        save_btn.setObjectName("primary_action")
        save_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(btn_frame)

    def _confirm(self):
        self.confirmed = True
        self.accept()

    def _cancel(self):
        self.confirmed = False
        self.reject()
