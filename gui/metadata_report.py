"""
DotScramble — Metadata Save Report Dialog (PySide6 version)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before saving, shows every metadata field the photo carries, its real value, and what
the saved file will hold: kept, removed or replaced. Built from a MetadataPlan
(core/metadata_writer), so the report and the written file can't disagree.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.managers.localization_manager import get_locale_manager
from src.views.widgets import caption

# Text lives in the locale files under metadata.report.* / metadata.fields.*
_PROFILES = ("blend", "ghost", "troll", "artist")
# action → the pill colour the QSS already defines (keep = green, strip = red, spoof = amber)
_PILL_KIND = {"keep": "keep", "remove": "strip", "replace": "spoof"}
_MAX_VALUE = 30
# Rows whose value is just "it's there" (or, for XMP, "with face locations")
_PRESENCE_KEYS = ("thumbnail", "xmp", "iptc", "extra_images", "icc")
_ALWAYS_REMOVED = ("thumbnail", "xmp", "iptc", "text", "extra_images")


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


def describe_before(change) -> str:
    """The value a field has in the photo, as shown to the user."""
    if change.key == "xmp" and change.before == "face_regions":
        return _t("metadata.report.xmp_faces")
    if change.key in _PRESENCE_KEYS:
        return _t("metadata.report.thumbnail_found")
    return _short(change.before)


def _short(value: str | None) -> str:
    if not value:
        return "—"
    return value if len(value) <= _MAX_VALUE else value[:_MAX_VALUE - 1] + "…"


class MetadataReportDialog(QDialog):
    """Pre-save confirmation: what is in the photo, and what the saved file will carry."""

    def __init__(self, parent=None, *, plan, filename: str = ""):
        super().__init__(parent)
        self.confirmed = False
        self.setWindowTitle(_t("metadata.report.window_title"))
        self.setMinimumSize(620, 500)
        self.resize(680, 620)
        self._build(plan, filename)

    def _banner_text(self, plan) -> tuple[str, str, str]:
        """(title, description, colour kind) for the mode."""
        if not plan.supported:
            return _t("metadata.report.unsupported_title"), _t("metadata.report.unsupported_desc"), "strip"
        if plan.mode == "spoof":
            shown = plan.profile if plan.profile in _PROFILES else "troll"
            return (_t("metadata.report.spoof_title", profile=_t(f"metadata.report.profiles.{shown}.name")),
                    _t(f"metadata.report.profiles.{shown}.desc"), "spoof")
        kind = {"keep": "keep", "location": "keep", "strip": "strip", "custom": "spoof"}[plan.mode]
        return _t(f"metadata.report.{plan.mode}_title"), _t(f"metadata.report.{plan.mode}_desc"), kind

    def _build(self, plan, filename):
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
            hdr_layout.addWidget(caption(short), alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(hdr)

        # ── Mode banner ───────────────────────────────────────────────────────
        banner_text, banner_desc, banner_kind = self._banner_text(plan)
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

        # ── Field by field ────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail = QWidget()
        detail.setObjectName("ReportDetail")
        grid = QGridLayout(detail)
        grid.setContentsMargins(20, 14, 20, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        if not plan.changes:
            grid.addWidget(caption(_t("metadata.report.no_metadata")), 0, 0, 1, 3)
        else:
            for col, key in enumerate(("col_field", "col_before", "col_after")):
                grid.addWidget(caption(_t(f"metadata.report.{key}"), role="heading"), 0, col)
            for row, change in enumerate(plan.changes, start=1):
                grid.addWidget(self._field_label(change.key), row, 0)
                before_lbl = QLabel(describe_before(change))
                before_lbl.setProperty("role", "field-value")
                before_lbl.setToolTip(change.before or "")
                grid.addWidget(before_lbl, row, 1)
                grid.addWidget(self._after_pill(change), row, 2)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(2, 1)
            notes = [_t(f"metadata.report.{c.key}_note") for c in plan.changes
                     if c.key in ("thumbnail", "xmp", "extra_images", "text")]
            note = "\n".join(notes)
            if note:
                note_lbl = caption(note)
                note_lbl.setWordWrap(True)
                grid.addWidget(note_lbl, len(plan.changes) + 1, 0, 1, 3)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(detail)
        main_layout.addWidget(scroll, 1)

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

    @staticmethod
    def _field_label(key: str) -> QLabel:
        label = QLabel(_t(f"metadata.fields.{key}"))
        label.setProperty("role", "field-label")
        return label

    @staticmethod
    def _after_pill(change) -> QLabel:
        if change.action == "keep":
            # the value is already in the "In this photo" column
            text = _t("metadata.report.action.keep")
        elif change.action == "replace":
            # isolate the (left-to-right) value so an Arabic or Persian label can't reorder it
            text = f"{_t('metadata.report.action.replace')} → \u2066{_short(change.after)}\u2069"
        elif change.key in _ALWAYS_REMOVED:
            text = _t("metadata.report.action.remove_always")
        else:
            text = _t("metadata.report.action.remove")
        pill = QLabel(text)
        pill.setProperty("role", "action-pill")
        pill.setProperty("action", _PILL_KIND[change.action])
        pill.setToolTip(change.after or "")
        return pill

    def _confirm(self):
        self.confirmed = True
        self.accept()

    def _cancel(self):
        self.confirmed = False
        self.reject()
