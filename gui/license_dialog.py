"""
DotScramble — License & devices (PySide6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shows this computer's name and Machine ID (what support asks for), whether Pro is active here,
and which of the account's device slots are in use, read live from DotSuite.
"""
from __future__ import annotations

import threading
import webbrowser
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from src.managers.localization_manager import get_locale_manager
from src.views.widgets import caption

DEVICES_URL = "https://dotsuite.dev/{lang}/dashboard/dotscramble"
SITE_LANGS = ("en", "ar", "de", "fr", "ru")


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


def _ltr(text: str) -> str:
    """Isolate left-to-right values (dates, IDs, host names) so Arabic or Persian text can't reorder them."""
    return f"\u2066{text}\u2069"


def _date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16]


class _Result(QObject):
    done = Signal(bool, object)


class LicenseDialog(QDialog):
    def __init__(self, parent=None, *, license_manager, on_deactivate=None):
        super().__init__(parent)
        self.lm, self.on_deactivate = license_manager, on_deactivate
        self.machine_id = license_manager.generate_machine_id()
        self._own_ids = {self.machine_id, license_manager.legacy_machine_id()}
        self.setWindowTitle(_t("ui.license.title"))
        self.setMinimumSize(560, 440)
        self._result = _Result(self)
        self._result.done.connect(self._show_devices)
        self._build()
        if license_manager.is_max_activated:
            self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)
        title = QLabel(_t("ui.license.title"))
        title.setObjectName("DialogTitle")
        hdr_layout.addWidget(title)
        layout.addWidget(hdr)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(10)

        # ── this computer ────────────────────────────────────────────────
        body.addWidget(caption(_t("ui.license.this_computer"), role="heading"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for row, (label, value) in enumerate(((_t("ui.license.name"), self.lm.device_name()),
                                              (_t("ui.license.machine_id"), self.machine_id))):
            key = QLabel(label)
            key.setProperty("role", "field-label")
            grid.addWidget(key, row, 0)
            val = QLabel(_ltr(value))
            val.setProperty("role", "field-value")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(val, row, 1)
        self.copy_btn = QPushButton(_t("ui.license.copy"))
        self.copy_btn.setProperty("variant", "ghost")
        self.copy_btn.clicked.connect(self._copy)
        grid.addWidget(self.copy_btn, 1, 2)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)

        active = self.lm.is_max_activated
        status = QLabel(_t("ui.license.status_pro" if active else "ui.license.status_free"))
        status.setProperty("role", "field-value")
        status.setWordWrap(True)
        body.addWidget(status)

        # ── devices on the account ───────────────────────────────────────
        if active:
            heading = QHBoxLayout()
            heading.addWidget(caption(_t("ui.license.devices_title"), role="heading"))
            heading.addStretch(1)
            self.count_label = caption()
            heading.addWidget(self.count_label)
            body.addLayout(heading)
            self.devices_box = QVBoxLayout()
            self.devices_box.setSpacing(6)
            holder = QWidget()
            holder.setLayout(self.devices_box)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(holder)
            body.addWidget(scroll, 1)
            self.status_label = caption(_t("ui.license.loading"))
            self.status_label.setWordWrap(True)
            self.devices_box.addWidget(self.status_label)
        else:
            hint = caption(_t("ui.license.free_hint"))
            hint.setWordWrap(True)
            body.addWidget(hint)
            body.addStretch(1)
        layout.addLayout(body, 1)

        buttons = QFrame()
        buttons.setObjectName("btn_frame")
        b_layout = QHBoxLayout(buttons)
        b_layout.setContentsMargins(20, 10, 20, 10)
        manage = QPushButton(_t("ui.license.manage"))
        manage.setProperty("variant", "ghost")
        manage.clicked.connect(self._open_dashboard)
        b_layout.addWidget(manage)
        if active and self.on_deactivate:
            deactivate = QPushButton(_t("ui.activation.deactivate_menu"))
            deactivate.setProperty("variant", "ghost")
            deactivate.clicked.connect(self._deactivate)
            b_layout.addWidget(deactivate)
        b_layout.addStretch(1)
        close = QPushButton(_t("ui.license.close"))
        close.setObjectName("primary_action")
        close.clicked.connect(self.accept)
        b_layout.addWidget(close)
        layout.addWidget(buttons)

    # ── actions ──────────────────────────────────────────────────────────
    def _copy(self):
        QApplication.clipboard().setText(self.machine_id)
        self.copy_btn.setText(_t("ui.license.copied"))

    def _open_dashboard(self):
        lang = get_locale_manager().current_language
        webbrowser.open(DEVICES_URL.format(lang=lang if lang in SITE_LANGS else "en"))

    def _deactivate(self):
        self.accept()
        self.on_deactivate()

    def _load(self):
        # The server answers in a second or two; never block the window on it
        threading.Thread(target=lambda: self._result.done.emit(*self.lm.devices()),
                         daemon=True, name="license-devices").start()

    def _show_devices(self, ok, data):
        if not ok:
            self.status_label.setText(_t("ui.license.offline", error=data))
            return
        self.status_label.hide()
        devices = data["devices"]
        self.count_label.setText(_t("ui.license.devices_used", count=len(devices), limit=data["limit"]))
        for device in devices:
            ours = device.get("machine_id") in self._own_ids
            name = device.get("name") or _t("ui.license.unnamed")
            line = QLabel(_ltr(name) + (f"  ({_t('ui.license.this_one')})" if ours else ""))
            line.setProperty("role", "field-label" if ours else "field-value")
            self.devices_box.addWidget(line)
            detail = caption(_t("ui.license.device_detail", id=_ltr((device.get("machine_id") or "")[:8]),
                                activated=_ltr(_date(device.get("activated_at"))),
                                seen=_ltr(_date(device.get("last_seen_at")))))
            self.devices_box.addWidget(detail)
        left = data.get("self_removals_left")
        if left is not None:
            text = (_t("ui.license.removals_left", count=left) if left > 0 else
                    _t("ui.license.removals_none", date=_ltr(_date(data.get("self_removals_reset_at")))))
            note = caption(text)
            note.setWordWrap(True)
            self.devices_box.addWidget(note)
        self.devices_box.addStretch(1)
