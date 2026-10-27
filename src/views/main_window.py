"""
Main GUI Window for DotScramble (PySide6 version)

Layout
    ┌ Toolbar ── brand │ open save │ undo redo │ detect compare │ zoom ── live · tier ┐
    ├ Sidebar ─────────────┬ Canvas ─────────────────────────────────────────────────┤
    │ 1 What to hide       │                                                         │
    │ 2 How to hide it     │                    ImageCanvas                          │
    │ 3 Fine-tune          │                                                         │
    │ 4 Metadata on save   │                                                         │
    │ [ Apply effect ]     │                                                         │
    └ Status bar ──────────┴─────────────────────────────────────────────────────────┘

All styling lives in assets/themes/theme_template.qss; this module only sets
objectNames and `variant` / `role` properties.
"""
import os
import re
import sys
import logging
import webbrowser

import cv2
import numpy as np
from PIL import Image

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QRadioButton, QButtonGroup, QFrame, QScrollArea, QLineEdit, QStatusBar, QMessageBox,
    QFileDialog, QSplitter, QDialog, QProgressBar, QProgressDialog, QInputDialog, QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QEvent
from PySide6.QtGui import QImage, QPixmap, QActionGroup, QKeySequence, QShortcut, QCursor

logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import *
from src.models.image_processor import ImageProcessor
from src.models.detection_engine import DetectionEngine
from src.managers.theme_manager import ThemeManager
from src.managers.localization_manager import get_locale_manager
from src.managers.rtl_manager import get_rtl_manager

from core.batch_processor import BatchProcessor
from core.utils import HistoryManager, PresetManager, ImageUtils, ExportManager
from core.image_picker import ImagePicker
from gui.batch_window import BatchWindow
from core.text_detector import TextDetector
from core.auto_updater import AutoUpdater
from core.version_gate import VersionGate
from src.managers.auth_server import LocalAuthManager

from src.managers.database_manager import init_database_manager
from src.managers.license_manager import LicenseManager
from core.metadata_spoofer import (
    spoof as _spoof_metadata,
    spoof_custom as _spoof_custom,
    read_exif_fields,
)
from gui.metadata_dialog import MetadataCustomizerDialog
from gui.metadata_report import MetadataReportDialog
from src.views.face_selection_dialog import FaceSelectionDialog
from src.views.image_canvas import ImageCanvas
from src.views.icons import IconProvider, bind_icon
from src.views.widgets import (
    CollapsibleSection, OptionGrid, SegmentedControl, SliderRow, caption,
)


# ── Option catalogues (value, icon) ──────────────────────────────────────────

DETECTION_MODES = ["face", "eye", "body", "license_plate", "text", "target_text", "manual", "full"]
PRO_ONLY_MODES = {"body", "license_plate", "text", "target_text"}
PREVIEWABLE_MODES = {"face", "eye", "body", "license_plate", "text", "target_text"}

STANDARD_EFFECTS = ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint"]
AI_EFFECTS = ["ai_evasion", "ai_evasion_invisible"]
BLUR_STRENGTH_EFFECTS = {"blur", "glass", "ai_evasion"}

METADATA_MODES = ["keep", "strip", "spoof"]
SPOOF_PROFILE_KEYS = ["ghost", "troll", "artist", "custom"]

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp"}

# Leading emoji / symbols, a trailing "(PRO)" and trailing colons in legacy locale strings
_DECORATION_RE = re.compile(r"^[^\w(]+|\s*\((?:PRO|برو)\)\s*$|\s*[:：]\s*$")


def plain(text: str) -> str:
    """'🎭 Face' → 'Face'. Icons now come from icons.py, not from the strings."""
    return _DECORATION_RE.sub("", text).strip()


class AdversarialWorker(QThread):
    """
    Background QThread that runs adversarial_perturb() so the GUI stays
    responsive. Emits progress(int, int, float) each iteration and
    finished_result(np.ndarray, float) when done.
    """
    progress = Signal(int, int, float)      # (iter, total, score)
    finished_result = Signal(object, float)  # (result_image_or_None, final_score)

    ITERS_PER_FACE = 60

    def __init__(self, image, pro_regions, effect_type, effect_kwargs, parent=None):
        super().__init__(parent)
        self._image = image
        self._pro_regions = pro_regions
        self._effect_type = effect_type
        self._effect_kwargs = effect_kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from src.models.image_processor import ImageProcessor as _IP
            result = self._image.copy()
            scores = []
            iters_per_face = self.ITERS_PER_FACE
            face_idx = 0

            for det in self._pro_regions:
                if self._cancelled:
                    self.finished_result.emit(None, 1.0)
                    return
                if det["type"] != "polygon":
                    continue
                strength = self._effect_kwargs.get("strength", 21)
                opacity = self._effect_kwargs.get("opacity", 100)
                face_offset = face_idx * iters_per_face

                def _cb(i, total, score, off=face_offset):
                    self.progress.emit(off + i, total, score)

                # Set parameters based on the chosen evasion mode
                if self._effect_type == "ai_evasion_invisible":
                    hybrid_effect = "none"
                    max_eps_val = 40
                else:
                    hybrid_effect = "blur"
                    max_eps_val = 110

                result, score = _IP.apply_adversarial_hybrid(
                    result,
                    det["points"],
                    hybrid_effect,
                    max_eps=max_eps_val,
                    iters=iters_per_face,
                    block_size=32,
                    progress_callback=_cb,
                    should_cancel=lambda: self._cancelled,
                    strength=strength,
                    opacity=opacity,
                )
                scores.append(score)
                face_idx += 1

                if self._cancelled:
                    self.finished_result.emit(None, 1.0)
                    return

            worst_score = max(scores) if scores else 1.0
            self.finished_result.emit(result, worst_score)
        except Exception as e:
            logger.error(f"AdversarialWorker error: {e}")
            self.finished_result.emit(None, 1.0)


class Var:
    """A small observable value: set() notifies every listener."""
    def __init__(self, value=None):
        self._value = value
        self._listeners = []

    def get(self):
        return self._value

    def set(self, val):
        self._value = val
        for listener in self._listeners:
            try:
                listener(val)
            except Exception as e:
                logger.error(f"Error in Var listener: {e}")

    def add_listener(self, callback):
        self._listeners.append(callback)


class AdvancedPrivacyStudioPro(QMainWindow):
    """DotScramble main window."""

    auth_success_signal = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_success_signal.connect(self._handle_auth_callback)
        self.colors = COLORS.copy()

        # Managers
        self.locale_manager = get_locale_manager()
        self.theme_manager = ThemeManager(self)
        self.rtl_manager = get_rtl_manager(self)
        self.db_manager = init_database_manager()
        self.license_manager = LicenseManager(self.db_manager)

        # Core components
        self.image_processor = ImageProcessor()
        self.detection_engine = DetectionEngine()
        self.text_detector = TextDetector()
        self.batch_processor = BatchProcessor(self.image_processor, self.detection_engine)
        self.history_manager = HistoryManager(MAX_HISTORY)
        self.preset_manager = PresetManager()
        self.image_utils = ImageUtils()
        self.auto_updater = AutoUpdater(self)
        self.auto_updater.updateReady.connect(self.on_update_ready)
        self.version_gate = VersionGate(self, APP_VERSION)  # blocks retired versions

        # Image state
        self.original_image = None
        self.processed_image = None
        self.image_path = None
        self.original_exif_bytes = None
        self.drawing_regions = []
        self._original_pixmap = None
        self._detection_preview = None   # {"mode", "rects", "pro"} while Detect is on
        self._live_applied = False       # last change came from live preview (replace, don't stack)
        self._adv_worker = None

        # Settings state
        self.target_word_var = Var("")
        self.detection_mode = Var("face")
        self.effect_type = Var("blur")
        self.blur_strength = Var(BLUR_RANGE['default'])
        self.pixel_size = Var(PIXEL_RANGE['default'])
        self.opacity = Var(OPACITY_RANGE['default'])
        self.real_time_preview = Var(False)
        self.language_var = Var("en")
        self.scrub_exif = Var(False)
        self.spoof_metadata = Var(False)
        self.spoof_profile = Var("troll")
        self.custom_field_actions = None

        self.resize(1400, 900)
        # Small enough to tile to half of a 1366px laptop screen
        self.setMinimumSize(640, 480)

        self._build_ui()
        self._bind_state()
        self.update_ui_text()
        self._update_action_states()

        self.db_manager.increment_stat('app_launches')

        QTimer.singleShot(1000, self.version_gate.start)
        if UPDATE_CONFIG['auto_check']:
            QTimer.singleShot(3000, self.auto_updater.check_for_updates_silently)

        # Enable snap layouts on Windows 11
        if sys.platform == 'win32':
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 38, ctypes.byref(ctypes.c_int(1)), 4
                )
            except Exception:
                pass

    def _t(self, key, **kwargs):
        return self.locale_manager.get(key, **kwargs)

    # ═════════════════════════════════════════════════════════════════════════
    # UI construction
    # ═════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_sidebar())

        self.canvas = ImageCanvas()
        self.canvas.fileDropped.connect(self.handle_dropped_file)
        self.canvas.regionDrawn.connect(self._on_region_drawn)
        self.canvas.detectionsChanged.connect(self._on_detections_changed)
        self.canvas.zoomChanged.connect(self._on_zoom_changed)
        self.splitter.addWidget(self.canvas)

        self.splitter.setSizes([340, 1060])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        root.addWidget(self.splitter, 1)

        self._build_status_bar()

    # ── Toolbar ──────────────────────────────────────────────────────────────

    def _tool_button(self, icon, slot=None, checkable=False, text_beside=True):
        button = QToolButton()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text_beside else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        button.setCheckable(checkable)
        bind_icon(button, icon, 18)
        if slot is not None:
            (button.toggled if checkable else button.clicked).connect(slot)
        return button

    @staticmethod
    def _toolbar_separator():
        line = QFrame()
        line.setObjectName("ToolbarSeparator")
        line.setFrameShape(QFrame.Shape.VLine)
        return line

    def _build_toolbar(self):
        self.toolbar = QFrame()
        self.toolbar.setObjectName("Toolbar")
        layout = QHBoxLayout(self.toolbar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        self.brand_label = QLabel()
        self.brand_label.setObjectName("BrandLabel")
        layout.addWidget(self.brand_label)
        layout.addWidget(self._toolbar_separator())

        self.open_btn = self._tool_button("open", self.load_image)
        self.save_btn = self._tool_button("save", self.save_image)
        layout.addWidget(self.open_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self._toolbar_separator())

        self.undo_btn = self._tool_button("undo", self.undo, text_beside=False)
        self.redo_btn = self._tool_button("redo", self.redo, text_beside=False)
        layout.addWidget(self.undo_btn)
        layout.addWidget(self.redo_btn)
        layout.addWidget(self._toolbar_separator())

        self.detect_btn = self._tool_button("detect", self._on_detect_toggled, checkable=True)
        self.detect_btn.setShortcut(QKeySequence("Ctrl+F"))
        self.compare_btn = self._tool_button("compare", self._on_compare_toggled, checkable=True)
        self.compare_btn.setShortcut(QKeySequence("Ctrl+Shift+C"))
        layout.addWidget(self.detect_btn)
        layout.addWidget(self.compare_btn)
        layout.addWidget(self._toolbar_separator())

        self.zoom_out_btn = self._tool_button("zoom_out", lambda: self.canvas.zoom_out(), text_beside=False)
        self.zoom_label = QToolButton()
        self.zoom_label.setObjectName("ZoomLabel")
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.clicked.connect(self._toggle_fit_actual)
        self.zoom_in_btn = self._tool_button("zoom_in", lambda: self.canvas.zoom_in(), text_beside=False)
        self.fit_btn = self._tool_button("fit", lambda: self.canvas.zoom_to_fit(), text_beside=False)
        for widget in (self.zoom_out_btn, self.zoom_label, self.zoom_in_btn, self.fit_btn):
            layout.addWidget(widget)

        layout.addStretch(1)

        self.live_btn = self._tool_button(
            "live", lambda on: self.real_time_preview.get() != on and self.real_time_preview.set(on), checkable=True)
        layout.addWidget(self.live_btn)

        self.upgrade_btn = QPushButton()
        self.upgrade_btn.setProperty("variant", "upgrade")
        self.upgrade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upgrade_btn.clicked.connect(self.show_activation_dialog)
        bind_icon(self.upgrade_btn, "star", 14, "accent_orange")
        self.pro_pill = QLabel()
        self.pro_pill.setObjectName("ProPill")
        layout.addSpacing(6)
        layout.addWidget(self.upgrade_btn)
        layout.addWidget(self.pro_pill)

        # Keyboard-only shortcuts (the menu already owns Ctrl+O/S/Z/Y/D/B)
        for sequence, slot in (
            (QKeySequence.StandardKey.ZoomIn, self.canvas_zoom_in),
            ("Ctrl+=", self.canvas_zoom_in),
            (QKeySequence.StandardKey.ZoomOut, self.canvas_zoom_out),
            ("Ctrl+0", self.canvas_zoom_fit),
            ("Ctrl+1", self.canvas_zoom_actual),
            ("Ctrl+Return", self.process_image),
            ("Ctrl+Enter", self.process_image),
        ):
            QShortcut(QKeySequence(sequence), self, activated=slot)

        # The toolbar must never dictate the window's minimum width — that is what stops
        # the desktop from snapping the window to half the screen. When it runs out of
        # room it drops to icon-only buttons instead (labels stay as tooltips).
        self._labelled_tools = [self.open_btn, self.save_btn, self.detect_btn, self.compare_btn, self.live_btn]
        self._toolbar_compact = False
        self._toolbar_full_width = 0
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.toolbar.installEventFilter(self)
        return self.toolbar

    def _measure_toolbar(self):
        """Remember how wide the labelled toolbar is; call whenever its texts change."""
        self._set_toolbar_compact(False)
        self.toolbar.layout().invalidate()
        self._toolbar_full_width = self.toolbar.layout().sizeHint().width()
        self._update_toolbar_mode()

    def _update_toolbar_mode(self):
        self._set_toolbar_compact(self.toolbar.width() < self._toolbar_full_width)

    def _set_toolbar_compact(self, compact):
        if compact == self._toolbar_compact:
            return
        self._toolbar_compact = compact
        style = Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        for button in self._labelled_tools:
            button.setToolButtonStyle(style)
        self.brand_label.setVisible(not compact)
        self.upgrade_btn.setText("" if compact else self._t("ui.toolbar.upgrade"))

    def eventFilter(self, obj, event):
        if obj is self.toolbar and event.type() == QEvent.Type.Resize:
            self._update_toolbar_mode()
        return super().eventFilter(obj, event)

    # Wrappers so shortcuts can be created before the canvas exists
    def canvas_zoom_in(self):
        self.canvas.zoom_in()

    def canvas_zoom_out(self):
        self.canvas.zoom_out()

    def canvas_zoom_fit(self):
        self.canvas.zoom_to_fit()

    def canvas_zoom_actual(self):
        self.canvas.zoom_actual()

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(300)
        self.sidebar.setMaximumWidth(440)
        outer = QVBoxLayout(self.sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("SidebarContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 6, 14, 12)
        layout.setSpacing(0)

        layout.addWidget(self._build_detection_section())
        layout.addWidget(self._build_effect_section())
        layout.addWidget(self._build_settings_section())
        layout.addWidget(self._build_metadata_section())
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._build_sidebar_footer())
        return self.sidebar

    def _build_detection_section(self):
        self.detect_section = CollapsibleSection(1)
        body = self.detect_section.body_layout

        self.detection_grid = OptionGrid(columns=2, variant="chip")
        for mode in DETECTION_MODES:
            self.detection_grid.add_option(mode, mode)
        self.detection_grid.valueChanged.connect(self._on_detection_selected)
        self.detection_grid.lockedClicked.connect(self._prompt_upgrade)
        body.addWidget(self.detection_grid)

        self.word_entry = QLineEdit()
        self.word_entry.setClearButtonEnabled(True)
        self.word_entry.textChanged.connect(self.target_word_var.set)
        body.addWidget(self.word_entry)

        self.manual_hint = caption(role="hint")
        self.ai_face_hint = caption(role="hint")
        self.tier_hint = caption()
        body.addWidget(self.manual_hint)
        body.addWidget(self.ai_face_hint)
        body.addWidget(self.tier_hint)
        return self.detect_section

    def _build_effect_section(self):
        self.effect_section = CollapsibleSection(2)
        self.effect_grid = OptionGrid(columns=3, variant="tile")
        for effect in STANDARD_EFFECTS:
            self.effect_grid.add_option(effect, effect)
        self.ai_heading = self.effect_grid.add_heading()
        for effect in AI_EFFECTS:
            self.effect_grid.add_option(effect, effect, wide=True)
        self.effect_grid.valueChanged.connect(self._on_effect_selected)
        self.effect_grid.lockedClicked.connect(self._prompt_upgrade)
        self.effect_section.body_layout.addWidget(self.effect_grid)
        return self.effect_section

    def _build_settings_section(self):
        self.settings_section = CollapsibleSection(3)
        body = self.settings_section.body_layout

        self.blur_row = SliderRow(BLUR_RANGE['min'], BLUR_RANGE['max'], self.blur_strength.get(), step=2)
        self.pixel_row = SliderRow(PIXEL_RANGE['min'], PIXEL_RANGE['max'], self.pixel_size.get(), suffix=" px")
        self.opacity_row = SliderRow(OPACITY_RANGE['min'], OPACITY_RANGE['max'], self.opacity.get(), suffix="%")
        self.blur_row.valueChanged.connect(self.blur_strength.set)
        self.pixel_row.valueChanged.connect(self.pixel_size.set)
        self.opacity_row.valueChanged.connect(self.opacity.set)
        for row in (self.blur_row, self.pixel_row, self.opacity_row):
            row.valueChanged.connect(lambda _value: self.on_parameter_change())
            body.addWidget(row)
        return self.settings_section

    def _build_metadata_section(self):
        self.metadata_section = CollapsibleSection(4)
        body = self.metadata_section.body_layout

        self.metadata_mode = SegmentedControl(METADATA_MODES)
        self.metadata_mode.valueChanged.connect(self._on_metadata_mode_selected)
        body.addWidget(self.metadata_mode)

        self.metadata_desc = caption()
        body.addWidget(self.metadata_desc)

        self.spoof_profile_frame = QWidget()
        profile_layout = QVBoxLayout(self.spoof_profile_frame)
        profile_layout.setContentsMargins(2, 0, 0, 0)
        profile_layout.setSpacing(6)
        self.profile_group = QButtonGroup(self)
        self.profile_radios = {}
        for key in SPOOF_PROFILE_KEYS:
            radio = QRadioButton()
            radio.toggled.connect(lambda checked, k=key: checked and self.spoof_profile.set(k))
            self.profile_group.addButton(radio)
            profile_layout.addWidget(radio)
            self.profile_radios[key] = radio

        self.customize_btn = QPushButton()
        self.customize_btn.setProperty("variant", "link")
        self.customize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.customize_btn.clicked.connect(self._open_metadata_customizer)
        profile_layout.addWidget(self.customize_btn)
        body.addWidget(self.spoof_profile_frame)

        self.metadata_locked_btn = QPushButton()
        self.metadata_locked_btn.setProperty("variant", "link")
        self.metadata_locked_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.metadata_locked_btn.clicked.connect(self.show_activation_dialog)
        bind_icon(self.metadata_locked_btn, "lock", 14, "accent_cyan")
        body.addWidget(self.metadata_locked_btn)
        return self.metadata_section

    def _build_sidebar_footer(self):
        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.process_btn = QPushButton()
        self.process_btn.setProperty("variant", "primary")
        self.process_btn.setProperty("size", "large")
        self.process_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.process_btn.clicked.connect(self.process_image)
        bind_icon(self.process_btn, "apply", 18, "on_accent")
        layout.addWidget(self.process_btn)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.clear_btn = QPushButton()
        self.clear_btn.setProperty("variant", "ghost")
        self.clear_btn.clicked.connect(self.clear_regions)
        bind_icon(self.clear_btn, "clear", 16, "text_secondary")
        self.batch_btn = QPushButton()
        self.batch_btn.setProperty("variant", "ghost")
        self.batch_btn.clicked.connect(self.open_batch_window)
        bind_icon(self.batch_btn, "batch", 16, "text_secondary")
        row.addWidget(self.clear_btn, 1)
        row.addWidget(self.batch_btn, 1)
        layout.addLayout(row)
        return footer

    # ── Status bar & menus ───────────────────────────────────────────────────

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label, 1)

        self.update_btn = QPushButton()
        self.update_btn.setObjectName("update_btn")
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self.apply_update)
        self.status_bar.addPermanentWidget(self.update_btn)

        self.info_label = QLabel()
        self.status_bar.addPermanentWidget(self.info_label)

    def create_menu_bar(self):
        menubar = self.menuBar()
        menubar.clear()
        _ = self._t

        # File
        file_menu = menubar.addMenu(_("menu.file"))
        file_menu.addAction(_("menu.file_items.open_image"), self.load_image).setShortcut("Ctrl+O")

        recent_menu = file_menu.addMenu(_("menu.file_items.open_recent"))
        recent_files = self.db_manager.get_recent_files(5)
        if recent_files:
            for file_info in recent_files:
                path = file_info['path']
                recent_menu.addAction(os.path.basename(path),
                                      lambda checked=False, p=path: self.load_image_from_path(p))
            recent_menu.addSeparator()
            recent_menu.addAction(_("menu.file_items.clear_history"), self.clear_recent_history)
        else:
            recent_menu.addAction(_("menu.file_items.no_recent")).setEnabled(False)

        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.save_result"), self.save_image).setShortcut("Ctrl+S")
        file_menu.addAction(_("menu.file_items.save_comparison"), self.save_comparison)
        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.open_exports"), self.open_exports_folder)
        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.batch_process"), self.open_batch_window).setShortcut("Ctrl+B")
        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.exit"), self.close)

        # Edit
        edit_menu = menubar.addMenu(_("menu.edit"))
        edit_menu.addAction(_("menu.edit_items.undo"), self.undo).setShortcut("Ctrl+Z")
        edit_menu.addAction(_("menu.edit_items.redo"), self.redo).setShortcut("Ctrl+Y")
        edit_menu.addSeparator()
        edit_menu.addAction(_("menu.edit_items.clear_selections"), self.clear_regions).setShortcut("Ctrl+D")
        edit_menu.addAction(_("menu.edit_items.reset_image"), self.reset_image)

        # Presets
        presets_menu = menubar.addMenu(_("menu.presets"))
        presets_menu.addAction(_("menu.presets_items.save_settings"), self.save_preset)
        presets_menu.addAction(_("menu.presets_items.load_preset"), self.load_preset)
        presets_menu.addAction(_("menu.presets_items.manage_presets"), self.manage_presets)

        # View
        view_menu = menubar.addMenu(_("menu.view"))
        theme_menu = view_menu.addMenu(_("menu.view_items.themes"))
        theme_group = QActionGroup(self)
        current_theme = self.theme_manager.get_current_theme_key()
        for theme_name, theme_key in self.theme_manager.get_theme_names():
            action = theme_menu.addAction(theme_name, lambda checked=False, k=theme_key: self.change_theme(k))
            action.setCheckable(True)
            action.setChecked(theme_key == current_theme)
            theme_group.addAction(action)

        lang_menu = view_menu.addMenu(_("menu.view_items.language"))
        lang_group = QActionGroup(self)
        for lang in self.locale_manager.get_language_list():
            action = lang_menu.addAction(f"{lang['name']} ({lang['native_name']})")
            action.setCheckable(True)
            action.setChecked(lang['code'] == self.language_var.get())
            action.triggered.connect(lambda checked=False, code=lang['code']: self.change_language(code))
            lang_group.addAction(action)

        # Help
        help_menu = menubar.addMenu(_("menu.help"))
        if self.license_manager.is_max_activated:
            help_menu.addAction(_("ui.tier.pro_activated_menu")).setEnabled(False)
        else:
            help_menu.addAction(_("ui.tier.upgrade_menu"), self.show_activation_dialog)
        help_menu.addSeparator()
        help_menu.addAction(_("menu.help_items.check_updates"), self.check_for_updates)
        help_menu.addSeparator()
        help_menu.addAction(_("menu.help_items.open_app_data"), self.open_app_data_folder)
        help_menu.addSeparator()
        help_menu.addAction(_("menu.help_items.donate"), self.show_donate)
        help_menu.addAction(_("menu.help_items.about"), self.show_about)
        help_menu.addAction(_("menu.help_items.shortcuts"), self.show_shortcuts)

    # ═════════════════════════════════════════════════════════════════════════
    # Text (called on start-up and whenever the language changes)
    # ═════════════════════════════════════════════════════════════════════════

    def update_ui_text(self):
        _ = self._t
        self.update_window_title()

        # Toolbar
        self.brand_label.setText(plain(_("ui.header.title")))
        for button, text_key, tip_key in (
            (self.open_btn, "ui.toolbar.open", "ui.toolbar.open_tip"),
            (self.save_btn, "ui.toolbar.save", "ui.toolbar.save_tip"),
            (self.undo_btn, None, "ui.toolbar.undo_tip"),
            (self.redo_btn, None, "ui.toolbar.redo_tip"),
            (self.detect_btn, "ui.toolbar.detect", "ui.toolbar.detect_tip"),
            (self.compare_btn, "ui.toolbar.compare", "ui.toolbar.compare_tip"),
            (self.zoom_out_btn, None, "ui.toolbar.zoom_out_tip"),
            (self.zoom_label, None, "ui.toolbar.zoom_label_tip"),
            (self.zoom_in_btn, None, "ui.toolbar.zoom_in_tip"),
            (self.fit_btn, None, "ui.toolbar.fit_tip"),
            (self.live_btn, "ui.toolbar.live", "ui.toolbar.live_tip"),
            (self.upgrade_btn, "ui.toolbar.upgrade", "ui.toolbar.upgrade_tip"),
        ):
            if text_key:
                button.setText(_(text_key))
            button.setToolTip(_(tip_key))
        self.pro_pill.setText(_("ui.toolbar.pro"))

        # Section 1 — detection
        self.detect_section.set_title(_("ui.sidebar.detect_title"))
        for mode in DETECTION_MODES:
            self.detection_grid.set_text(mode, plain(_(f"detection.{mode}")))
        self.word_entry.setPlaceholderText(_("ui.sidebar.word_placeholder"))
        self.manual_hint.setText(_("ui.sidebar.manual_hint"))
        self.ai_face_hint.setText(_("ui.sidebar.ai_face_only"))

        # Section 2 — effect
        self.effect_section.set_title(_("ui.sidebar.effect_title"))
        for effect in STANDARD_EFFECTS:
            self.effect_grid.set_text(effect, plain(_(f"effects.{effect}")))
        self.ai_heading.setText(_("ui.sidebar.ai_heading").upper())
        self.effect_grid.set_text("ai_evasion", _("ui.sidebar.ai_hybrid"))
        self.effect_grid.set_tooltip("ai_evasion", _("ui.sidebar.ai_hybrid_tip"))
        self.effect_grid.set_text("ai_evasion_invisible", _("ui.sidebar.ai_invisible"))
        self.effect_grid.set_tooltip("ai_evasion_invisible", _("ui.sidebar.ai_invisible_tip"))

        # Section 3 — fine-tune
        self.settings_section.set_title(_("ui.sidebar.settings_title"))
        self.blur_row.set_label(_("ui.controls.blur_strength"))
        self.pixel_row.set_label(_("ui.controls.pixel_size"))
        self.opacity_row.set_label(plain(_("ui.controls.opacity").replace("(%)", "")))

        # Section 4 — metadata
        self.metadata_section.set_title(_("ui.sidebar.metadata_title"))
        for mode in METADATA_MODES:
            self.metadata_mode.set_text(mode, _(f"ui.metadata.{mode}"))
        for key, radio in self.profile_radios.items():
            radio.setText(_(f"ui.metadata.profiles.{key}"))
        self.customize_btn.setText(_("ui.metadata.editor"))
        self.metadata_locked_btn.setText(_("ui.metadata.locked"))

        # Footer & status bar
        self.process_btn.setText(_("ui.sidebar.apply"))
        self.process_btn.setToolTip(_("ui.sidebar.apply_tip"))
        self.clear_btn.setText(_("ui.sidebar.clear"))
        self.batch_btn.setText(_("ui.sidebar.batch"))
        self.update_btn.setText(_("ui.status.restart_to_update"))
        if self.original_image is None:
            self.status_label.setText(_("ui.status.ready"))
        else:
            self._show_image_status()

        # Canvas
        self.canvas.set_placeholder(_("ui.canvas.placeholder_title"), _("ui.canvas.placeholder_subtitle"))
        self.canvas.set_compare_labels(_("ui.canvas.before"), _("ui.canvas.after"))

        self.word_entry.setAlignment(Qt.AlignmentFlag.AlignRight if self.is_rtl else Qt.AlignmentFlag.AlignLeft)
        self._refresh_tier_ui()
        self._sync_controls()
        self.create_menu_bar()
        self._measure_toolbar()

    def update_window_title(self):
        title = self._t("app.title")
        if self.license_manager.is_max_activated:
            title += " (PRO)"
        self.setWindowTitle(title)

    # ═════════════════════════════════════════════════════════════════════════
    # State → controls
    # ═════════════════════════════════════════════════════════════════════════

    def _bind_state(self):
        """Every settings Var refreshes the controls, so presets / restore just set Vars."""
        for var in (self.detection_mode, self.effect_type, self.scrub_exif,
                    self.spoof_metadata, self.spoof_profile):
            var.add_listener(lambda _value: self._sync_controls())
        self.blur_strength.add_listener(self.blur_row.set_value)
        self.pixel_size.add_listener(self.pixel_row.set_value)
        self.opacity.add_listener(self.opacity_row.set_value)
        self.real_time_preview.add_listener(self._on_live_preview_changed)
        self.target_word_var.add_listener(
            lambda text: self.word_entry.text() != text and self.word_entry.setText(text))

    def _sync_controls(self):
        """Bring every sidebar control in line with the current settings."""
        _ = self._t
        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        is_ai = effect in AI_EFFECTS

        # Section 1
        self.detection_grid.set_value(mode)
        self.detection_grid.set_allowed({"face"} if is_ai else None)
        self.word_entry.setVisible(mode == "target_text")
        self.manual_hint.setVisible(mode == "manual")
        self.ai_face_hint.setVisible(is_ai)
        self.canvas.set_drawing_enabled(mode == "manual")
        self.detect_section.set_summary(plain(_(f"detection.{mode}")))

        # Section 2
        self.effect_grid.set_value(effect)
        if is_ai:
            effect_name = _("ui.sidebar.ai_hybrid" if effect == "ai_evasion" else "ui.sidebar.ai_invisible")
            effect_name = effect_name.split("—")[0].strip()
        else:
            effect_name = plain(_(f"effects.{effect}"))
        self.effect_section.set_summary(effect_name)

        # Section 3
        self.blur_row.setVisible(effect in BLUR_STRENGTH_EFFECTS)
        self.pixel_row.setVisible(effect == "pixelation")
        self.settings_section.set_summary(f"{self.opacity.get()}%")

        # Section 4
        meta_mode = "strip" if self.scrub_exif.get() else "spoof" if self.spoof_metadata.get() else "keep"
        self.metadata_mode.set_value(meta_mode)
        self.metadata_desc.setText(_(f"ui.metadata.{meta_mode}_desc"))
        self.metadata_section.set_summary(_(f"ui.metadata.{meta_mode}"))
        self.spoof_profile_frame.setVisible(meta_mode == "spoof")
        profile = self.spoof_profile.get()
        if profile in self.profile_radios and not self.profile_radios[profile].isChecked():
            self.profile_radios[profile].setChecked(True)
        self.customize_btn.setVisible(profile == "custom")

    def _refresh_tier_ui(self):
        """Lock / unlock Pro features everywhere."""
        is_pro = self.license_manager.is_max_activated
        for mode in PRO_ONLY_MODES:
            self.detection_grid.set_locked(mode, not is_pro)
        for effect in AI_EFFECTS:
            self.effect_grid.set_locked(effect, not is_pro)
        # Settings restored from an earlier Pro session must not keep a locked option selected
        if not is_pro and self.effect_type.get() in AI_EFFECTS:
            self.effect_type.set("blur")
        if not is_pro and self.detection_mode.get() in PRO_ONLY_MODES:
            self.detection_mode.set("face")

        self.tier_hint.setText(self._t("ui.sidebar.pro_hint" if is_pro else "ui.sidebar.free_hint"))
        self.upgrade_btn.setVisible(not is_pro)
        self.pro_pill.setVisible(is_pro)
        self.metadata_mode.setEnabled(is_pro)
        self.spoof_profile_frame.setEnabled(is_pro)
        self.metadata_locked_btn.setVisible(not is_pro)

    def refresh_exif_and_tier_badge(self):
        self._refresh_tier_ui()
        self._sync_controls()

    def _update_action_states(self):
        has_image = self.original_image is not None
        self.process_btn.setEnabled(has_image)
        self.save_btn.setEnabled(self.processed_image is not None)
        self.clear_btn.setEnabled(has_image)
        self.undo_btn.setEnabled(self.history_manager.can_undo())
        self.redo_btn.setEnabled(self.history_manager.can_redo())
        for widget in (self.detect_btn, self.compare_btn, self.zoom_out_btn,
                       self.zoom_label, self.zoom_in_btn, self.fit_btn):
            widget.setEnabled(has_image)
        if not has_image:
            self.zoom_label.setText("—")

    # Kept for callers that still use the old names
    update_buttons = _update_action_states
    restore_button_states = _update_action_states

    # ═════════════════════════════════════════════════════════════════════════
    # Sidebar events
    # ═════════════════════════════════════════════════════════════════════════

    def _on_detection_selected(self, mode):
        self.detection_mode.set(mode)
        previewing = self.detect_btn.isChecked()
        self._reset_detection_preview()

        if mode in ("face", "eye") and self.license_manager.is_max_activated:
            from src.models.detection_engine import is_model_downloaded
            if not is_model_downloaded():
                self.prompt_download_ai_model()

        if previewing and mode in PREVIEWABLE_MODES:
            self.detect_btn.setChecked(True)  # re-run the overlay for the new mode
        self.on_parameter_change()

    def _on_effect_selected(self, effect):
        self.effect_type.set(effect)
        if effect in AI_EFFECTS and self.detection_mode.get() != "face":
            self.detection_mode.set("face")
            self._reset_detection_preview()
        self.on_parameter_change()

    def _on_metadata_mode_selected(self, mode):
        self.scrub_exif.set(mode == "strip")
        self.spoof_metadata.set(mode == "spoof")

    def _prompt_upgrade(self, value):
        if value in AI_EFFECTS:
            name = self._t("ui.sidebar.ai_heading")
        else:
            name = plain(self._t(f"detection.{value}"))
        answer = QMessageBox.question(
            self, self._t("ui.sidebar.locked_title"), self._t("ui.sidebar.locked_msg", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.show_activation_dialog()

    def on_parameter_change(self):
        self._sync_controls()
        self.save_current_effect_settings()
        if self.real_time_preview.get() and self.original_image is not None:
            self._apply_live_preview()

    def _on_live_preview_changed(self, enabled):
        if self.live_btn.isChecked() != enabled:
            self.live_btn.setChecked(enabled)
        self.toggle_preview()

    def toggle_preview(self):
        enabled = self.real_time_preview.get()
        try:
            self.db_manager.save_real_time_preview_enabled(enabled)
        except Exception as e:
            logger.warning(f"Could not save preview preference: {e}")

        if enabled:
            self.status_label.setText(self._t("ui.status.preview_enabled"))
            if self.original_image is not None:
                self._apply_live_preview()
        else:
            self._live_applied = False
            self.status_label.setText(self._t("ui.status.preview_disabled"))

    def _apply_live_preview(self):
        """Re-apply with new settings, replacing (not stacking on) the previous live result."""
        if self.effect_type.get() in AI_EFFECTS:
            return  # far too slow to run on every slider tick
        reverted = self._live_applied and self.history_manager.can_undo()
        if reverted:
            self.processed_image = self.history_manager.undo()
        self._live_applied = self._apply_effect(quiet=True)
        if reverted and not self._live_applied:
            self.display_image(self.processed_image)
            self._update_action_states()

    def _open_metadata_customizer(self):
        current_exif = {}
        if self.image_path:
            try:
                current_exif = read_exif_fields(self.image_path)
            except Exception:
                pass
        dlg = MetadataCustomizerDialog(self, current_exif=current_exif)
        dlg.exec()
        if dlg.result is not None:
            self.custom_field_actions = dlg.result
            self.status_label.setText(self._t("ui.metadata.custom_saved"))

    # ═════════════════════════════════════════════════════════════════════════
    # Loading & display
    # ═════════════════════════════════════════════════════════════════════════

    def load_image(self):
        file_path = ImagePicker(self).open()
        if file_path:
            self.load_image_from_path(file_path)

    def load_image_from_path(self, file_path):
        _ = self._t
        if not file_path or not os.path.exists(file_path):
            QMessageBox.critical(self, _("ui.messages.title_error"), _("ui.messages.file_not_found"))
            return

        try:
            # imdecode supports unicode file paths
            loaded_image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if loaded_image is None or loaded_image.size == 0:
                QMessageBox.critical(self, _("ui.messages.title_error"),
                                     _("dialogs.error.image_corrupted", filename=os.path.basename(file_path)))
                return

            self.image_path = file_path
            self.db_manager.add_recent_file(file_path)

            self.original_exif_bytes = None
            try:
                pil_img = Image.open(file_path)
                self.original_exif_bytes = pil_img.info.get('exif')
            except Exception:
                pass

            self.original_image = loaded_image
            self.processed_image = loaded_image.copy()
            self._original_pixmap = self._to_pixmap(loaded_image)
            self.drawing_regions = []
            self.history_manager.clear()
            self._live_applied = False

            self.canvas.set_regions([])
            self.compare_btn.setChecked(False)
            self._reset_detection_preview()
            self.canvas.set_image(self._original_pixmap)
            self.canvas.zoom_to_fit()

            self._show_image_status()
            self._update_action_states()
            self.create_menu_bar()  # refresh "Open Recent"
        except Exception as e:
            QMessageBox.critical(self, _("ui.messages.title_error"), _("dialogs.error.loading_image", error=str(e)))
            self.status_label.setText(_("ui.status.failed_load"))

    def _show_image_status(self):
        info = self.image_utils.get_image_info(self.original_image)
        self.status_label.setText(self._t("ui.status.loaded", filename=os.path.basename(self.image_path)))
        self.info_label.setText(self._t("ui.info.image_info", width=info['width'],
                                        height=info['height'], size_kb=info['size_kb']))

    def handle_dropped_file(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTS:
            QMessageBox.warning(self, self._t("ui.messages.unsupported_title"),
                                self._t("ui.messages.unsupported_drop", ext=ext or "(none)"))
            return
        self.load_image_from_path(file_path)

    @staticmethod
    def _to_pixmap(cv_image):
        rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888))

    def display_image(self, cv_image):
        if cv_image is None or cv_image.size == 0:
            return
        try:
            self.canvas.set_image(self._to_pixmap(cv_image))
        except cv2.error as e:
            QMessageBox.critical(self, self._t("ui.messages.title_error"),
                                 self._t("ui.messages.display_error", error=str(e)))

    # ═════════════════════════════════════════════════════════════════════════
    # Canvas tools: zoom, compare, detection preview, manual regions
    # ═════════════════════════════════════════════════════════════════════════

    def _on_zoom_changed(self, scale):
        self.zoom_label.setText(f"{round(scale * 100)}%")

    def _toggle_fit_actual(self):
        if self.canvas.is_fit():
            self.canvas.zoom_actual()
        else:
            self.canvas.zoom_to_fit()

    def _on_compare_toggled(self, enabled):
        if enabled and self._original_pixmap is not None:
            self.canvas.set_compare_image(self._original_pixmap)
            self.status_label.setText(self._t("ui.status.compare_on"))
        else:
            self.canvas.set_compare_image(None)

    def _on_detect_toggled(self, enabled):
        if not enabled:
            self._detection_preview = None
            self.canvas.clear_detections()
            return
        if self.processed_image is None:
            self.detect_btn.setChecked(False)
            return

        mode = self.detection_mode.get()
        if mode not in PREVIEWABLE_MODES:
            self.status_label.setText(self._t("ui.status.detect_unavailable"))
            self.detect_btn.setChecked(False)
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            detected = self._detect(mode)
        finally:
            QApplication.restoreOverrideCursor()
        if detected is None:
            self.detect_btn.setChecked(False)
            return

        rects, pro = detected
        self._detection_preview = {"mode": mode, "rects": rects, "pro": pro}
        self.canvas.set_detections([self._outline(d) for d in list(rects) + list(pro)])
        self._on_detections_changed()

    def _on_detections_changed(self):
        if not self._detection_preview:
            return
        total = len(self._detection_preview["rects"]) + len(self._detection_preview["pro"])
        if total == 0:
            self.status_label.setText(self._t("ui.status.detected_none"))
            return
        active = total - len(self.canvas.skipped_detections())
        # The noun agrees with the total ("1 of 3 regions"), so the total drives the plural
        self.status_label.setText(self._t("ui.status.detected", shown=active, count=total))

    def _reset_detection_preview(self):
        if self.detect_btn.isChecked():
            self.detect_btn.setChecked(False)  # toggled(False) clears the overlay
        self._detection_preview = None
        self.canvas.clear_detections()

    @staticmethod
    def _outline(det):
        """Polygon (image coords) for any detection format."""
        if isinstance(det, dict):
            if det["type"] == "polygon":
                return det["points"]
            if det["type"] == "rotated_rect":
                return cv2.boxPoints((det["center"], det["size"], det["angle"])).tolist()
        x, y, w, h = det
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def _on_region_drawn(self, rect):
        self.drawing_regions.append((rect.x(), rect.y(), rect.width(), rect.height()))
        self.canvas.set_regions(self.drawing_regions)
        self.status_label.setText(self._t("ui.status.region_added", count=len(self.drawing_regions)))
        if self.real_time_preview.get():
            self._apply_live_preview()

    def clear_regions(self):
        self.drawing_regions = []
        self.canvas.set_regions([])
        self._reset_detection_preview()
        self.status_label.setText(self._t("ui.status.cleared"))

    # ═════════════════════════════════════════════════════════════════════════
    # Detection & processing
    # ═════════════════════════════════════════════════════════════════════════

    def _detect(self, mode, quiet=False):
        """
        Find the regions for `mode` on the current image.
        Returns (rects, pro_regions), or None when the user has to act first
        (a message has been shown unless `quiet`, as during live preview).
        """
        _ = self._t

        def tell(show, text, title_key="ui.messages.title_info"):
            if not quiet:
                show(self, _(title_key), text)

        image = self.processed_image
        engine = self.detection_engine
        is_pro = self.license_manager.is_max_activated

        def cascades_ready():
            # Haar detectors return [] when their files are missing — never treat that as "no faces"
            missing = engine.missing_cascades(mode)
            if missing:
                self.status_label.setText(_("ui.status.detection_unavailable"))
                tell(QMessageBox.critical, _("ui.messages.cascades_missing", files=", ".join(missing)),
                     "ui.messages.title_error")
            return not missing

        if mode in ("face", "eye"):
            pro = []
            if is_pro:
                pro = engine.detect_faces_pro(image) if mode == "face" else engine.detect_eyes_pro(image)
            if pro:
                return [], pro
            if not cascades_ready():
                return None
            return (engine.detect_faces(image) if mode == "face" else engine.detect_eyes(image)), []
        if mode == "body":
            if not cascades_ready():
                return None
            return engine.detect_full_body(image), []
        if mode == "license_plate":
            return engine.detect_license_plates(image), []
        if mode == "text":
            return engine.detect_text(image), []
        if mode == "target_text":
            word = self.target_word_var.get()
            if not word:
                tell(QMessageBox.warning, _("dialogs.error.no_word"))
                return None
            rects = self.text_detector.detect_specific_word(image, word)
            if not rects:
                tell(QMessageBox.information, _("dialogs.error.word_not_found", word=word))
                return None
            return rects, []
        if mode == "manual":
            if not self.drawing_regions:
                tell(QMessageBox.information, _("dialogs.error.no_selections"))
                return None
            return list(self.drawing_regions), []
        if mode == "full":
            h, w = image.shape[:2]
            return [(0, 0, w, h)], []
        return None

    def _previewed_regions(self):
        """The Detect overlay's results minus the ones the user clicked to skip."""
        skipped = self.canvas.skipped_detections()
        rects = self._detection_preview["rects"]
        pro = self._detection_preview["pro"]
        kept_rects = [r for i, r in enumerate(rects) if i not in skipped]
        kept_pro = [p for i, p in enumerate(pro) if i + len(rects) not in skipped]
        return kept_rects, kept_pro

    def process_image(self):
        """Apply button / Ctrl+Enter."""
        if self._live_applied:
            # Live preview already shows the result — Apply just keeps it.
            self._live_applied = False
            self.status_label.setText(self._t("ui.status.applied"))
            return
        self._apply_effect()

    def _apply_effect(self, quiet=False):
        """Detect + apply. Returns True when the image changed synchronously."""
        if self.original_image is None:
            return False

        _ = self._t
        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        from_preview = bool(self._detection_preview and self._detection_preview["mode"] == mode)

        try:
            if from_preview:
                regions, pro_regions = self._previewed_regions()
            else:
                detected = self._detect(mode, quiet=quiet)
                if detected is None:
                    return False
                regions, pro_regions = detected

            effect_kwargs = dict(
                strength=self.blur_strength.get(),
                pixel_size=self.pixel_size.get(),
                opacity=self.opacity.get(),
            )

            # ── AI Evasion — async path ────────────────────────────────────────
            if effect in AI_EFFECTS and pro_regions:
                polygon_regions = [d for d in pro_regions if d["type"] == "polygon"]
                if not polygon_regions:
                    QMessageBox.warning(self, _("ui.sidebar.ai_heading"), _("ui.ai.no_oval"))
                    return False

                # Faces picked on the canvas already; otherwise ask when there are several.
                if len(polygon_regions) > 1 and not from_preview:
                    dlg = FaceSelectionDialog(self, self.processed_image, polygon_regions)
                    if dlg.exec() != QDialog.DialogCode.Accepted:
                        return False
                    polygon_regions = dlg.get_selected_faces()
                    if not polygon_regions:
                        return False

                self._run_adversarial_async(self.processed_image.copy(), polygon_regions, effect, effect_kwargs)
                return False  # Result delivered via signal when the worker finishes

            # ── Standard path ──────────────────────────────────────────────────
            self.history_manager.save_state(self.processed_image)
            result = self.processed_image.copy()
            for (x, y, w, h) in regions:
                try:
                    result = ImageProcessor.apply_effect_to_region(
                        result, x, y, w, h, effect_type=effect, **effect_kwargs)
                except Exception as e:
                    logger.error(f"Error applying effect to region: {e}")
            for det in pro_regions:
                if det["type"] == "polygon":
                    result = self.image_processor.apply_effect_to_polygon(
                        result, det["points"], effect, **effect_kwargs)
                elif det["type"] == "rotated_rect":
                    result = self.image_processor.apply_effect_rotated(
                        result, det["center"], det["size"], det["angle"], effect, **effect_kwargs)
            self.processed_image = result

            total = len(regions) + len(pro_regions)
            badge = " · 🛡️ Anti-AI" if pro_regions else ""
            self._reset_detection_preview()
            self.display_image(self.processed_image)
            self.status_label.setText(_("ui.status.processed", count=total) + badge)
            self._update_action_states()
            return True
        except Exception as e:
            QMessageBox.critical(self, _("ui.messages.title_error"), _("dialogs.error.processing", error=str(e)))
            return False

    def _set_busy(self, busy):
        """Lock the UI while the AI Evasion worker owns MediaPipe and the image."""
        for widget in (self.sidebar, self.toolbar, self.menuBar()):
            widget.setEnabled(not busy)
        if not busy:
            self._update_action_states()

    def _run_adversarial_async(self, image, pro_regions, effect, effect_kwargs):
        """Launch AdversarialWorker in a background QThread with a progress dialog."""
        _ = self._t
        n_faces = len(pro_regions)
        iters = AdversarialWorker.ITERS_PER_FACE

        progress_dlg = QProgressDialog(_("ui.ai.progress_start"), _("ui.ai.cancel"), 0, iters * n_faces, self)
        progress_dlg.setWindowTitle(_("ui.ai.progress_title"))
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setValue(0)

        self._set_busy(True)
        self._adv_worker = AdversarialWorker(image, pro_regions, effect, effect_kwargs, self)

        def on_progress(abs_i, total_per_face, score):
            progress_dlg.setValue(abs_i)
            face_num = ((abs_i - 1) // total_per_face) + 1 if total_per_face > 0 else 1
            iter_in_face = ((abs_i - 1) % total_per_face) + 1 if total_per_face > 0 else abs_i
            progress_dlg.setLabelText(_("ui.ai.progress_step", face=face_num, faces=n_faces,
                                        iter=iter_in_face, iters=total_per_face, score=f"{score:.2f}"))
            if progress_dlg.wasCanceled():
                self._adv_worker.cancel()

        def on_finished(result_image, final_score):
            progress_dlg.close()
            self._set_busy(False)

            if result_image is None:
                self.status_label.setText(_("ui.status.ai_cancelled"))
                return
            self.history_manager.save_state(self.processed_image)
            self.processed_image = result_image
            self._reset_detection_preview()
            self.display_image(self.processed_image)

            # Three distinct outcomes — never mislead the user
            if final_score == 0.0:
                msg = _("ui.status.ai_success")
            elif final_score < 1.0:
                msg = _("ui.status.ai_partial", percent=int((1.0 - final_score) * 100))
            else:
                # score==1.0: adversarial step crashed; base blur was preserved (fail-closed)
                msg = _("ui.status.ai_failed")
            self.status_label.setText(msg)
            self._update_action_states()

        self._adv_worker.progress.connect(on_progress)
        self._adv_worker.finished_result.connect(on_finished)
        progress_dlg.canceled.connect(self._adv_worker.cancel)
        self._adv_worker.start()

    # ═════════════════════════════════════════════════════════════════════════
    # Saving
    # ═════════════════════════════════════════════════════════════════════════

    def save_image(self):
        if self.processed_image is None:
            return
        _ = self._t

        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            _("ui.messages.save_dialog_title"),
            os.path.expanduser("~"),
            "JPEG Images (*.jpg *.jpeg);;PNG Images (*.png);;BMP Images (*.bmp);;TIFF Images (*.tiff);;All Files (*)"
        )
        if not file_path:
            return

        is_max = self.license_manager.is_max_activated
        should_scrub = is_max and self.scrub_exif.get()
        should_spoof = is_max and self.spoof_metadata.get() and not should_scrub

        # Metadata confirmation report
        report_mode = "restore"
        report_profile = None
        report_actions = None

        if should_scrub:
            report_mode = "scrub"
        elif should_spoof:
            report_mode = "spoof"
            report_profile = self.spoof_profile.get()
            if report_profile == "custom":
                report_actions = self.custom_field_actions or {}

        report_dlg = MetadataReportDialog(
            self,
            mode=report_mode,
            profile=report_profile,
            field_actions=report_actions,
            filename=os.path.basename(file_path)
        )
        report_dlg.exec()

        if not report_dlg.confirmed:
            return

        # Write processed image with multi-tier fallback against imencode extension errors
        ext = os.path.splitext(file_path)[1].lower()
        if not ext:
            ext = ".jpg"
            file_path += ext

        saved = False
        try:
            is_success, im_buf_arr = cv2.imencode(ext, self.processed_image)
            if is_success:
                im_buf_arr.tofile(file_path)
                saved = True
        except Exception as e:
            logger.warning(f"cv2.imencode failed for extension '{ext}': {e}")

        if not saved:
            try:
                cv2.imwrite(file_path, self.processed_image)
                saved = True
            except Exception as e:
                logger.warning(f"cv2.imwrite failed: {e}")

        if not saved:
            try:
                pil_img = Image.fromarray(cv2.cvtColor(self.processed_image, cv2.COLOR_BGR2RGB))
                pil_img.save(file_path)
                saved = True
            except Exception as e:
                logger.error(f"PIL save fallback failed: {e}")

        if should_scrub:
            pass
        elif should_spoof:
            ext = os.path.splitext(file_path)[1].lower()
            profile = self.spoof_profile.get()

            if profile == "custom" and self.custom_field_actions:
                if ext in ('.jpg', '.jpeg', '.png'):
                    try:
                        _spoof_custom(file_path, file_path, field_actions=self.custom_field_actions)
                    except Exception as e:
                        logger.error(f"Metadata custom warning: {e}")
                else:
                    self._restore_original_exif(file_path)
            elif ext in ('.jpg', '.jpeg', '.png'):
                try:
                    _spoof_metadata(file_path, file_path, profile=profile)
                except Exception as e:
                    logger.error(f"Metadata spoof warning: {e}")
            else:
                self._restore_original_exif(file_path)
        else:
            self._restore_original_exif(file_path)

        QMessageBox.information(self, _("ui.messages.title_success"), _("dialogs.info.saved"))
        self.status_label.setText(_("ui.status.saved", filename=os.path.basename(file_path)))

    def _restore_original_exif(self, file_path):
        if not self.original_exif_bytes:
            return
        try:
            pil_img = Image.open(file_path)
            pil_img.save(file_path, exif=self.original_exif_bytes)
        except Exception as e:
            logger.error(f"EXIF restore warning: {e}")

    def save_comparison(self):
        if self.original_image is None or self.processed_image is None:
            return
        file_path, _filter = QFileDialog.getSaveFileName(
            self,
            self._t("ui.messages.comparison_dialog_title"),
            os.path.expanduser("~"),
            "JPEG Images (*.jpg);;PNG Images (*.png)"
        )
        if file_path:
            ExportManager.export_comparison(self.original_image, self.processed_image, file_path)
            QMessageBox.information(self, self._t("ui.messages.title_success"), self._t("dialogs.info.comparison_saved"))

    # ═════════════════════════════════════════════════════════════════════════
    # History
    # ═════════════════════════════════════════════════════════════════════════

    def undo(self):
        prev_image = self.history_manager.undo()
        if prev_image is not None:
            self.history_manager.add_to_redo(self.processed_image)
            self.processed_image = prev_image
            self._live_applied = False
            self.display_image(self.processed_image)
            self.status_label.setText(self._t("ui.status.undo_done"))
            self._update_action_states()

    def redo(self):
        next_image = self.history_manager.redo()
        if next_image is not None:
            self.history_manager.save_state(self.processed_image, clear_redo=False)
            self.processed_image = next_image
            self._live_applied = False
            self.display_image(self.processed_image)
            self.status_label.setText(self._t("ui.status.redo_done"))
            self._update_action_states()

    def reset_image(self):
        if self.original_image is not None:
            self.processed_image = self.original_image.copy()
            self.drawing_regions = []
            self.canvas.set_regions([])
            self.history_manager.clear()
            self._live_applied = False
            self.display_image(self.processed_image)
            self.status_label.setText(self._t("ui.status.reset"))
            self._update_action_states()

    # ═════════════════════════════════════════════════════════════════════════
    # Presets & batch
    # ═════════════════════════════════════════════════════════════════════════

    def _current_settings(self):
        return {
            'effect_type': self.effect_type.get(),
            'detection_mode': self.detection_mode.get(),
            'blur_strength': self.blur_strength.get(),
            'pixel_size': self.pixel_size.get(),
            'opacity': self.opacity.get(),
        }

    def _apply_settings(self, settings):
        self.effect_type.set(settings.get('effect_type', 'blur'))
        self.detection_mode.set(settings.get('detection_mode', 'face'))
        self.blur_strength.set(settings.get('blur_strength', BLUR_RANGE['default']))
        self.pixel_size.set(settings.get('pixel_size', PIXEL_RANGE['default']))
        self.opacity.set(settings.get('opacity', OPACITY_RANGE['default']))

    def save_preset(self):
        _ = self._t
        name, ok = QInputDialog.getText(self, _("presets.save"), _("presets.save_prompt"))
        if ok and name:
            self.preset_manager.add_preset(name, self._current_settings())
            QMessageBox.information(self, _("ui.messages.title_success"), _("dialogs.info.preset_saved", name=name))

    def load_preset(self):
        _ = self._t
        presets = self.preset_manager.get_all_presets()
        if not presets:
            QMessageBox.information(self, _("ui.messages.title_info"), _("presets.no_presets"))
            return
        name, ok = QInputDialog.getItem(self, _("presets.load"), _("ui.messages.select_preset_prompt"),
                                        list(presets.keys()), 0, False)
        if ok and name:
            self._apply_settings(presets[name])
            QMessageBox.information(self, _("ui.messages.title_success"), _("ui.messages.preset_loaded", name=name))

    def manage_presets(self):
        _ = self._t
        presets = self.preset_manager.get_all_presets()
        if not presets:
            QMessageBox.information(self, _("ui.messages.title_info"), _("presets.no_presets"))
            return
        name, ok = QInputDialog.getItem(self, _("ui.messages.delete_preset_title"),
                                        _("ui.messages.delete_preset_prompt"), list(presets.keys()), 0, False)
        if ok and name:
            self.preset_manager.delete_preset(name)
            QMessageBox.information(self, _("ui.messages.title_success"), _("ui.messages.preset_deleted", name=name))

    def open_batch_window(self):
        BatchWindow(self, self.batch_processor, self.license_manager).exec()

    def save_current_effect_settings(self):
        try:
            self.db_manager.save_last_effect_settings(self._current_settings())
        except Exception as e:
            logger.warning(f"Could not save effect settings: {e}")

    # ═════════════════════════════════════════════════════════════════════════
    # Pro activation
    # ═════════════════════════════════════════════════════════════════════════

    def show_activation_dialog(self):
        """Start local browser-based authentication flow."""
        _ = self._t
        dialog = QDialog(self)
        dialog.setWindowTitle(_("ui.activation.title"))
        dialog.setFixedSize(420, 220)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel(_("ui.activation.waiting"))
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = caption(_("ui.activation.desc"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(progress)

        def fallback_to_manual():
            if getattr(self, 'auth_manager', None):
                self.auth_manager.stop()
            dialog.reject()
            self._show_manual_activation_dialog()

        manual_btn = QPushButton(_("ui.activation.manual_btn"))
        manual_btn.setProperty("variant", "ghost")
        manual_btn.clicked.connect(fallback_to_manual)
        layout.addWidget(manual_btn)

        def on_auth_success(key):
            self.auth_success_signal.emit(dialog, key)

        self.auth_manager = LocalAuthManager(callback=on_auth_success)
        try:
            port, state = self.auth_manager.start()
            dialog.finished.connect(lambda result: self.auth_manager.stop())

            auth_url = f"{AUTH_BASE_URL}/en/dashboard/dotscramble/auth?port={port}&state={state}"
            webbrowser.open(auth_url)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to start local auth server: {e}")
            fallback_to_manual()

    def _handle_auth_callback(self, dialog, key):
        dialog.accept()
        self._activate(key)

    def _show_manual_activation_dialog(self):
        key, ok = QInputDialog.getText(self, self._t("ui.activation.manual_title"), self._t("ui.activation.manual_prompt"))
        if ok and key:
            self._activate(key.strip())

    def _activate(self, key):
        _ = self._t
        self.status_label.setText(_("ui.status.activating"))
        QApplication.processEvents()

        success, message = self.license_manager.verify_and_activate(key)
        if success:
            QMessageBox.information(self, _("ui.messages.title_success"), message)
            self.update_window_title()
            self.create_menu_bar()
            self.refresh_exif_and_tier_badge()
            self.status_label.setText(_("ui.status.activated"))
        else:
            QMessageBox.critical(self, _("ui.activation.failed_title"), message)
            self.status_label.setText(_("ui.status.activation_failed"))

    def prompt_download_ai_model(self):
        _ = self._t
        if QMessageBox.question(self, _("ui.model.title"), _("ui.model.prompt"),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return

        dl_win = QDialog(self)
        dl_win.setWindowTitle(_("ui.model.downloading_title"))
        dl_win.setFixedSize(320, 120)

        layout = QVBoxLayout(dl_win)
        label = QLabel(_("ui.model.downloading"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        progress = QProgressBar()
        progress.setRange(0, 100)
        layout.addWidget(progress)

        import threading

        def download_thread():
            from src.models.detection_engine import download_model_file

            def update_progress(percentage):
                QTimer.singleShot(0, lambda: progress.setValue(int(percentage)))

            success = download_model_file(update_progress)

            def on_finish():
                dl_win.accept()
                if success:
                    QMessageBox.information(self, _("ui.messages.title_success"), _("ui.model.success"))
                    if self.real_time_preview.get() and self.original_image is not None:
                        self._apply_live_preview()
                else:
                    QMessageBox.critical(self, _("ui.model.failed_title"), _("ui.model.failed"))
            QTimer.singleShot(0, on_finish)

        threading.Thread(target=download_thread, daemon=True).start()
        dl_win.exec()

    # ═════════════════════════════════════════════════════════════════════════
    # Help, updates & folders
    # ═════════════════════════════════════════════════════════════════════════

    def show_donate(self):
        _ = self._t
        dialog = QDialog(self)
        dialog.setWindowTitle(_("dialogs.info.donate"))
        dialog.setFixedSize(400, 340)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel(_("dialogs.info.donate"))
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = caption(_("dialogs.info.donate_text"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        for object_name, text_key, url in (
            ("btn_paypal", "donate.paypal", "https://paypal.me/freerave1"),
            ("btn_coffee", "donate.buy_coffee", "https://buymeacoffee.com/freerave"),
            ("btn_kofi", "donate.kofi", "https://ko-fi.com/freerave"),
            ("btn_github", "donate.github", "https://github.com/sponsors/kareem2099"),
        ):
            button = QPushButton(_(text_key))
            button.setObjectName(object_name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, u=url: self.open_url(u))
            layout.addWidget(button)

        close_btn = QPushButton(_("ui.messages.close"))
        close_btn.setProperty("variant", "ghost")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception:
            QMessageBox.critical(self, self._t("ui.messages.title_error"), self._t("donate.url_error", url=url))

    def show_about(self):
        QMessageBox.information(self, self._t("menu.help_items.about"),
                                self._t("dialogs.info.about", version=APP_VERSION))

    def show_shortcuts(self):
        _ = self._t
        rows = [
            ("Ctrl+O", _("menu.file_items.open_image")),
            ("Ctrl+S", _("menu.file_items.save_result")),
            ("Ctrl+Enter", _("ui.sidebar.apply")),
            ("Ctrl+Z", _("menu.edit_items.undo")),
            ("Ctrl+Y", _("menu.edit_items.redo")),
            ("Ctrl+D", _("menu.edit_items.clear_selections")),
            ("Ctrl+F", _("ui.toolbar.detect")),
            ("Ctrl+Shift+C", _("ui.toolbar.compare")),
            ("Ctrl+ +  /  Ctrl+ −", _("ui.messages.zoom")),
            ("Ctrl+0  /  Ctrl+1", _("ui.messages.zoom_fit_actual")),
            ("Ctrl+B", _("menu.file_items.batch_process")),
        ]
        QMessageBox.information(self, _("dialogs.info.shortcuts"),
                                "\n".join(f"{keys}    {label}" for keys, label in rows))

    def check_for_updates(self):
        self.auto_updater.check_for_updates(silent=False)

    def _open_folder(self, path):
        try:
            webbrowser.open(str(path))
        except Exception as e:
            QMessageBox.critical(self, self._t("ui.messages.title_error"),
                                 self._t("ui.messages.open_folder_error", error=str(e)))

    def open_exports_folder(self):
        self._open_folder(DIRS['exports'])

    def open_app_data_folder(self):
        self._open_folder(SYSTEM_DIR)

    def on_update_ready(self, silent):
        self.update_btn.setVisible(True)
        if silent:
            QMessageBox.information(self, self._t("ui.messages.update_ready_title"), self._t("dialogs.info.update_ready"))
        else:
            self.apply_update()

    def apply_update(self):
        if QMessageBox.question(self, self._t("ui.messages.restart_title"), self._t("dialogs.info.restart_required"),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) == QMessageBox.StandardButton.Yes:
            self.auto_updater.apply_pending_update()

    def clear_recent_history(self):
        if QMessageBox.question(self, self._t("ui.messages.clear_history_title"),
                                self._t("dialogs.warning.clear_history"),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) == QMessageBox.StandardButton.Yes:
            self.db_manager.clear_recent_files()
            self.create_menu_bar()

    # ═════════════════════════════════════════════════════════════════════════
    # Theme, language & window state
    # ═════════════════════════════════════════════════════════════════════════

    def change_theme(self, theme_key):
        self.theme_manager.apply_theme(theme_key, self)
        self.create_menu_bar()

    def on_theme_changed(self, colors):
        self.colors = colors.copy()
        IconProvider.instance().set_colors(colors)

    @property
    def is_rtl(self):
        return bool(getattr(self, 'rtl_manager', None) and self.rtl_manager.is_rtl)

    def apply_rtl_layout(self, language_code):
        if self.locale_manager.set_language(language_code):
            self.rtl_manager.set_rtl_state(self.locale_manager.is_rtl())

    def change_language(self, language_code):
        if self.locale_manager.set_language(language_code):
            self.language_var.set(language_code)
            self.db_manager.save_last_used_language(language_code)
            self.apply_rtl_layout(language_code)
            self.update_ui_text()

    def restore_window_state(self):
        try:
            state = self.db_manager.get_setting('window_state')
            if state and isinstance(state, dict) and state.get('maximized'):
                self.showMaximized()
            else:
                w = state.get('width', 1400) if state else 1400
                h = state.get('height', 900) if state else 900
                x = state.get('x') if state else None
                y = state.get('y') if state else None
                self.resize(w, h)
                if x is not None and y is not None:
                    self.move(x, y)

            splitter_hex = self.db_manager.get_setting('splitter_state')
            if splitter_hex:
                from PySide6.QtCore import QByteArray
                self.splitter.restoreState(QByteArray.fromHex(splitter_hex.encode()))
        except Exception as e:
            logger.warning(f"Could not restore window state: {e}")

    def restore_user_settings(self):
        try:
            last_language = self.db_manager.get_last_used_language()
            self.language_var.set(last_language)
            if self.locale_manager.set_language(last_language):
                self.apply_rtl_layout(last_language)

            if not self.theme_manager.apply_theme(self.db_manager.get_last_used_theme(), self):
                self.theme_manager.apply_theme(self.theme_manager.get_current_theme_key(), self)
            self._apply_settings(self.db_manager.get_last_effect_settings())
            self.real_time_preview.set(self.db_manager.get_real_time_preview_enabled())

            self.update_ui_text()
            logger.info("User settings restored from database")
        except Exception as e:
            logger.warning(f"Could not restore user settings: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_state_restored'):
            self._state_restored = True
            self.restore_window_state()
            self.restore_user_settings()

    def closeEvent(self, event):
        self.on_close()
        event.accept()

    def on_close(self):
        try:
            if self.isMaximized():
                self.db_manager.save_setting('window_state', {'maximized': True}, 'window')
            else:
                geom = self.geometry()
                self.db_manager.save_window_state(geom.width(), geom.height(), geom.x(), geom.y(), False)
            self.db_manager.save_setting('splitter_state', self.splitter.saveState().toHex().data().decode(), 'window')
            logger.info("Application state saved before closing")
        except Exception as e:
            logger.warning(f"Error saving application state: {e}")

        try:
            self.db_manager.close()
        except Exception:
            pass
