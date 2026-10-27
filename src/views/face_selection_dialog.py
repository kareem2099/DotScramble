"""
FaceSelectionDialog — DotScramble PRO
======================================
Shown before AI Evasion when more than one face is detected.
Lets the user pick which faces to process and confirms with a
thumbnail grid so the choice is always visually clear.
"""
import cv2
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QCheckBox, QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from src.managers.localization_manager import get_locale_manager


_THUMB_W = 120
_THUMB_H = 120


def _t(key, **kwargs):
    return get_locale_manager().get(key, **kwargs)


def _crop_face_thumbnail(image: np.ndarray, points: list) -> np.ndarray:
    """
    Return a square BGR thumbnail for one face polygon.
    Uses the bounding rect + 20 % padding, resized to (_THUMB_W, _THUMB_H).
    """
    if image is None or len(points) < 3:
        return np.zeros((_THUMB_H, _THUMB_W, 3), dtype=np.uint8)

    pts = np.array(points, dtype=np.int32)
    x, y, w, h = cv2.boundingRect(pts)
    img_h, img_w = image.shape[:2]

    pad = int(0.20 * max(w, h))
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(img_w, x + w + pad)
    y1 = min(img_h, y + h + pad)

    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return np.zeros((_THUMB_H, _THUMB_W, 3), dtype=np.uint8)

    thumb = cv2.resize(crop, (_THUMB_W, _THUMB_H), interpolation=cv2.INTER_AREA)
    return thumb


def _ndarray_to_pixmap(bgr: np.ndarray) -> QPixmap:
    """Convert a BGR numpy uint8 array to a QPixmap."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class _FaceCard(QFrame):
    """
    A single face card in the selection grid.
    Contains: thumbnail image, face number label, and a checkbox.
    """

    def __init__(self, face_index: int, thumbnail_pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.face_index = face_index
        self.setObjectName("FaceCard")
        self.setFixedSize(_THUMB_W + 24, _THUMB_H + 56)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setPixmap(thumbnail_pixmap)
        thumb_label.setFixedSize(_THUMB_W, _THUMB_H)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumb_label)

        # Face number label
        num_label = QLabel(_t("ui.faces.face_n", n=face_index + 1))
        num_label.setProperty("role", "field-label")
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(num_label)

        # Checkbox — checked by default (all faces selected initially)
        self.checkbox = QCheckBox(_t("ui.faces.select"))
        self.checkbox.setChecked(True)
        self.checkbox.setObjectName("FaceCardCheckbox")
        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, value: bool):
        self.checkbox.setChecked(value)


class FaceSelectionDialog(QDialog):
    """
    Modal dialog shown when AI Evasion is triggered on a multi-face image.

    Usage
    -----
    dlg = FaceSelectionDialog(parent, image_bgr, polygon_regions)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        selected = dlg.get_selected_faces()   # list[dict] — subset of polygon_regions
    """

    def __init__(self, parent, image_bgr: np.ndarray, polygon_regions: list):
        super().__init__(parent)
        self._polygon_regions = polygon_regions
        self._cards: list[_FaceCard] = []

        self.setWindowTitle(_t("ui.faces.title"))
        self.setModal(True)
        self.setMinimumWidth(480)

        self._build_ui(image_bgr, polygon_regions)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self, image_bgr: np.ndarray, polygon_regions: list):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        n = len(polygon_regions)
        header = QLabel(_t("ui.faces.header", count=n))
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setWordWrap(True)
        root.addWidget(header)

        # Select-all / Deselect-all convenience row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)

        btn_all = QPushButton(_t("ui.faces.select_all"))
        btn_all.setProperty("variant", "ghost")
        btn_all.clicked.connect(lambda: self._set_all(True))
        sel_row.addWidget(btn_all)

        btn_none = QPushButton(_t("ui.faces.deselect_all"))
        btn_none.setProperty("variant", "ghost")
        btn_none.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(btn_none)

        sel_row.addStretch(1)
        root.addLayout(sel_row)

        # Scrollable grid of face cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(4, 4, 4, 4)
        grid_layout.setSpacing(10)

        cols = 3
        for i, det in enumerate(polygon_regions):
            thumb_bgr = _crop_face_thumbnail(image_bgr, det["points"])
            pixmap    = _ndarray_to_pixmap(thumb_bgr)
            card      = _FaceCard(i, pixmap)
            card.checkbox.stateChanged.connect(self._on_selection_changed)
            self._cards.append(card)
            grid_layout.addWidget(card, i // cols, i % cols)

        scroll.setWidget(grid_widget)
        root.addWidget(scroll, 1)

        # Informational note about Opacity
        note = QLabel(_t("ui.faces.note"))
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        note.setObjectName("FaceSelectionNote")
        root.addWidget(note)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        cancel_btn = QPushButton(_t("ui.ai.cancel"))
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._apply_btn = QPushButton(_t("ui.faces.apply"))
        self._apply_btn.setProperty("variant", "primary")
        self._apply_btn.setDefault(True)
        self._apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._apply_btn)

        root.addLayout(btn_row)

        # Set initial Apply button state
        self._on_selection_changed()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _set_all(self, value: bool):
        for card in self._cards:
            card.set_selected(value)

    def _on_selection_changed(self):
        any_selected = any(c.is_selected() for c in self._cards)
        self._apply_btn.setEnabled(any_selected)

    # ── Public API ───────────────────────────────────────────────────────────

    def get_selected_faces(self) -> list:
        """
        Returns the subset of the original polygon_regions list that the
        user selected. Each item is the original dict unchanged (type + points).
        """
        return [
            self._polygon_regions[i]
            for i, card in enumerate(self._cards)
            if card.is_selected()
        ]
