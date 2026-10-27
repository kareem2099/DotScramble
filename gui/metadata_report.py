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

from src.managers.localization_manager import get_locale_manager
from src.views.widgets import caption

# Text lives in the locale files under metadata.report.* / metadata.fields.*
_PROFILES = ("ghost", "troll", "artist", "custom")
_ACTION_ICONS = {"keep": "✅", "strip": "🗑", "spoof": "🎲"}
_STRIP_ITEMS = ("gps", "camera", "software", "timestamps", "copyright", "exposure", "fingerprint")


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


def _describe_action(key: str, action) -> tuple[str, str, str]:
    """Return (icon, action kind, description); the kind picks the pill color in the QSS."""
    if isinstance(action, dict):
        if key == "gps":
            return ("✏️", "custom", _t("metadata.report.custom_gps",
                                       lat=action.get("lat", "?"), lon=action.get("lon", "?")))
        val = action.get("value", "")
        desc = _t("metadata.report.custom_value", value=val[:30]) if val else _t("metadata.report.custom_empty")
        return ("✏️", "custom", desc)
    if action in _ACTION_ICONS:
        return _ACTION_ICONS[action], action, _t(f"metadata.report.action_desc.{action}")
    return "❓", action, action


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

        self.setWindowTitle(_t("metadata.report.window_title"))
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

        title_lbl = QLabel(_t("metadata.report.title"))
        title_lbl.setObjectName("DialogTitle")
        hdr_layout.addWidget(title_lbl)

        if filename:
            short = filename if len(filename) <= 32 else "…" + filename[-29:]
            fn_lbl = caption(short)
            hdr_layout.addWidget(fn_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(hdr)

        # ── Mode banner ───────────────────────────────────────────────────────
        if mode == "scrub":
            banner_text  = _t("metadata.report.strip_title")
            banner_kind  = "strip"
            banner_desc  = _t("metadata.report.strip_desc")
        elif mode == "restore":
            banner_text  = _t("metadata.report.keep_title")
            banner_kind  = "keep"
            banner_desc  = _t("metadata.report.keep_desc")
        else:   # spoof
            shown = profile or "ghost"
            if shown in _PROFILES:
                pname = _t(f"metadata.report.profiles.{shown}.name")
                pdesc = _t(f"metadata.report.profiles.{shown}.desc")
            else:
                pname, pdesc = _t("metadata.report.spoof_default"), ""
            banner_text  = _t("metadata.report.spoof_title", profile=pname)
            banner_kind  = "spoof"
            banner_desc  = pdesc

        banner = QFrame()
        banner.setObjectName("ReportBanner")
        banner.setProperty("action", banner_kind)
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(20, 10, 20, 10)
        banner_layout.setSpacing(4)

        b_title = QLabel(banner_text)
        b_title.setObjectName("ReportBannerTitle")
        banner_layout.addWidget(b_title)

        b_desc = QLabel(banner_desc)
        b_desc.setObjectName("ReportBannerText")
        b_desc.setWordWrap(True)
        banner_layout.addWidget(b_desc)

        banner_wrap = QVBoxLayout()
        banner_wrap.setContentsMargins(16, 14, 16, 0)
        banner_wrap.addWidget(banner)
        main_layout.addLayout(banner_wrap)

        # ── Detail area ───────────────────────────────────────────────────────
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(20, 15, 20, 15)

        if mode == "spoof" and field_actions:
            detail_layout.addWidget(caption(_t("metadata.report.field_actions"), role="heading"))

            for key, action in field_actions.items():
                label = _t(f"metadata.fields.{key}")
                icon, kind, desc = _describe_action(key, action)

                row = QFrame()
                row.setObjectName("card_frame")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 6, 10, 6)

                field_lbl = QLabel(label)
                field_lbl.setProperty("role", "field-label")
                row_layout.addWidget(field_lbl, 1)

                act_lbl = QLabel(f"{icon} {desc}")
                act_lbl.setProperty("role", "action-pill")
                act_lbl.setProperty("action", kind)
                row_layout.addWidget(act_lbl)

                detail_layout.addWidget(row)

        elif mode == "scrub":
            detail_layout.addWidget(caption(_t("metadata.report.strip_list_title"), role="heading"))

            for item in _STRIP_ITEMS:
                item_lbl = QLabel(f"  🗑  {_t(f'metadata.report.strip_items.{item}')}")
                item_lbl.setProperty("role", "danger-item")
                detail_layout.addWidget(item_lbl)
        else:
            # restore or simple spoof without custom fields
            if mode == "spoof" and profile in _PROFILES:
                detail_layout.addWidget(caption(_t(f"metadata.report.profiles.{profile}.desc")))
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

        cancel_btn = QPushButton(_t("metadata.cancel"))
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton(_t("metadata.report.save"))
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
