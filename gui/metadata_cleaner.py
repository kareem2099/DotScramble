"""
DotScramble — Clean metadata only (PySide6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Removes metadata from photos without touching a pixel: JPEG data is copied as-is, other
formats are rewritten losslessly. Results go next to the originals as <name>_clean.<ext>;
an original is never overwritten. Free removes the location from a few photos a day.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout,
)

from core import metadata_writer
from src.managers.localization_manager import get_locale_manager
from src.views.widgets import caption

CLEANABLE = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")
CLEAN_MODES = ("location", "strip", "spoof")      # "spoof" uses the Blend-in decoys
PRO_CLEAN_MODES = {"strip", "spoof"}


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


def clean_target(path: str) -> str:
    """<name>_clean<ext> beside `path`, numbered when that name is taken."""
    stem, ext = os.path.splitext(path)
    target, n = f"{stem}_clean{ext}", 2
    while os.path.exists(target):
        target, n = f"{stem}_clean ({n}){ext}", n + 1
    return target


def clean_one(path: str, mode: str) -> tuple[str, str | None, bool]:
    """
    Clean one photo. Returns (status, output path or None, location_removed) where status is
    "done", "nothing" (no metadata to clean), "failed" or "unsupported".
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in CLEANABLE:
        return "unsupported", None, False
    original = metadata_writer.load_exif(path)
    extras = metadata_writer.inspect_extras(path)
    plan = metadata_writer.make_plan(original, mode, ext=ext, profile="blend", extras=extras,
                                     pixels_upright=False)
    if not any(c.action != "keep" for c in plan.changes):
        return "nothing", None, False
    target = clean_target(path)
    try:
        metadata_writer.clean_file(path, target, plan)
    except Exception:
        return "failed", None, False
    if metadata_writer.verify(target, plan, original):
        try:
            os.remove(target)
        except OSError:
            pass
        return "failed", None, False
    removed = metadata_writer.gps_of(original) is not None and metadata_writer.gps_of(plan.exif) is None
    return "done", target, removed


class MetadataCleanerDialog(QDialog):
    def __init__(self, parent=None, *, is_pro: bool, quota, on_upgrade=None, usage=None):
        super().__init__(parent)
        self.is_pro, self.quota, self.on_upgrade, self.usage = is_pro, quota, on_upgrade, usage
        self.files: list[str] = []
        self.setWindowTitle(_t("metadata.cleaner.window_title"))
        self.setMinimumSize(620, 520)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)
        title = QLabel(_t("metadata.cleaner.title"))
        title.setObjectName("DialogTitle")
        hdr_layout.addWidget(title)
        layout.addWidget(hdr)

        body = QVBoxLayout()
        body.setContentsMargins(20, 14, 20, 14)
        body.setSpacing(10)
        intro = caption(_t("metadata.cleaner.intro"))
        intro.setWordWrap(True)
        body.addWidget(intro)

        self.list = QListWidget()
        body.addWidget(self.list, 1)
        row = QHBoxLayout()
        for key, slot in (("add_files", self._add_files), ("add_folder", self._add_folder), ("clear", self._clear)):
            btn = QPushButton(_t(f"metadata.cleaner.{key}"))
            btn.setProperty("variant", "ghost")
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        self.count_label = caption()
        row.addWidget(self.count_label)
        body.addLayout(row)

        body.addWidget(caption(_t("metadata.cleaner.what"), role="heading"))
        self.modes = QButtonGroup(self)
        for mode in CLEAN_MODES:
            radio = QRadioButton(_t(f"metadata.cleaner.mode.{mode}"))
            radio.setProperty("mode", mode)
            locked = mode in PRO_CLEAN_MODES and not self.is_pro
            radio.setEnabled(not locked)
            if locked:
                radio.setText(radio.text() + "  " + _t("metadata.cleaner.pro_only"))
            self.modes.addButton(radio)
            body.addWidget(radio)
            if mode == "location":
                radio.setChecked(True)
        if not self.is_pro:
            self.quota_label = caption(_t("ui.metadata.free_quota", count=self.quota.remaining(), limit=self.quota.limit))
            body.addWidget(self.quota_label)

        self.summary = caption()
        self.summary.setWordWrap(True)
        body.addWidget(self.summary)
        layout.addLayout(body, 1)

        buttons = QFrame()
        buttons.setObjectName("btn_frame")
        b_layout = QHBoxLayout(buttons)
        b_layout.setContentsMargins(20, 10, 20, 10)
        b_layout.addStretch(1)
        close = QPushButton(_t("metadata.inspector.close"))
        close.setProperty("variant", "ghost")
        close.clicked.connect(self.reject)
        b_layout.addWidget(close)
        self.start_btn = QPushButton(_t("metadata.cleaner.start"))
        self.start_btn.setObjectName("primary_action")
        self.start_btn.clicked.connect(self.run)
        b_layout.addWidget(self.start_btn)
        layout.addWidget(buttons)
        self._refresh()

    # ── files ────────────────────────────────────────────────────────────────
    def add_paths(self, paths):
        for path in paths:
            if os.path.splitext(path)[1].lower() in CLEANABLE and path not in self.files:
                self.files.append(path)
                self.list.addItem(QListWidgetItem(os.path.basename(path)))
        self._refresh()

    def _add_files(self):
        paths, _f = QFileDialog.getOpenFileNames(self, _t("metadata.cleaner.add_files"), os.path.expanduser("~"),
                                                 "Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff)")
        self.add_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _t("metadata.cleaner.add_folder"), os.path.expanduser("~"))
        if folder:
            self.add_paths(sorted(os.path.join(folder, n) for n in os.listdir(folder)
                                  if not os.path.splitext(n)[0].endswith("_clean")))

    def _clear(self):
        self.files.clear()
        self.list.clear()
        self.summary.clear()
        self._refresh()

    def _refresh(self):
        self.count_label.setText(_t("batch.files_count", count=len(self.files)))
        self.start_btn.setEnabled(bool(self.files))

    # ── running ──────────────────────────────────────────────────────────────
    def selected_mode(self) -> str:
        button = self.modes.checkedButton()
        return button.property("mode") if button else "location"

    def run(self):
        mode = self.selected_mode()
        if mode in PRO_CLEAN_MODES and not self.is_pro:
            return
        counts = {"done": 0, "nothing": 0, "failed": 0, "skipped": 0}
        self.start_btn.setEnabled(False)
        for i, path in enumerate(self.files):
            item = self.list.item(i)
            limited = not self.is_pro and mode == "location"
            if limited and self.quota.remaining() == 0 and metadata_writer.gps_of(metadata_writer.load_exif(path)):
                status, target, removed = "skipped", None, False
            else:
                status, target, removed = clean_one(path, mode)
                if limited and removed:
                    self.quota.consume()
                if status == "done" and mode in PRO_CLEAN_MODES and self.usage:
                    self.usage.add("metadata_cleaned")
            counts["failed" if status == "unsupported" else status] += 1
            label = _t(f"metadata.cleaner.status.{status}")
            item.setText(f"{os.path.basename(path)}  —  {label}" + (f"  →  {os.path.basename(target)}" if target else ""))
            item.setData(Qt.ItemDataRole.UserRole, status)
            QApplication.processEvents()
        if not self.is_pro:
            self.quota_label.setText(_t("ui.metadata.free_quota", count=self.quota.remaining(), limit=self.quota.limit))
        text = _t("metadata.cleaner.summary", done=counts["done"], nothing=counts["nothing"], failed=counts["failed"])
        if counts["skipped"]:
            text += "\n" + _t("metadata.cleaner.skipped_free", count=counts["skipped"], limit=self.quota.limit)
        self.summary.setText(text)
        self.start_btn.setEnabled(True)
        self.last_counts = counts
