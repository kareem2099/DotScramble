"""
Main GUI Window for Advanced Privacy Studio Pro (PySide6 version)
"""
import cv2
import numpy as np
import os
import logging
from PIL import Image
import sys
import webbrowser

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFrame, QScrollArea, QSlider,
    QCheckBox, QLineEdit, QStatusBar, QMessageBox, QFileDialog, QSplitter,
    QMenuBar, QMenu, QDialog, QProgressBar, QProgressDialog, QInputDialog, QApplication
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QIcon, QImage, QPixmap, QPainter, QPen, QColor, QFont, QActionGroup

logger = logging.getLogger(__name__)

# Import custom modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import *
from src.models.image_processor import ImageProcessor
from src.models.detection_engine import DetectionEngine
from src.managers.theme_manager import ThemeManager
from src.managers.localization_manager import get_locale_manager
from src.managers.rtl_manager import get_rtl_manager

from core.batch_processor import BatchProcessor
from core.utils import HistoryManager, PresetManager, ImageUtils, ExportManager, format_timestamp
from core.image_picker import ImagePicker
from gui.batch_window import BatchWindow
from core.text_detector import TextDetector
from core.auto_updater import AutoUpdater
from src.managers.auth_server import LocalAuthManager

from src.managers.database_manager import init_database_manager, get_db_manager
from src.managers.license_manager import LicenseManager
from core.metadata_spoofer import (
    spoof as _spoof_metadata,
    spoof_custom as _spoof_custom,
    read_exif_fields,
    PROFILES as SPOOF_PROFILES,
)
from gui.metadata_dialog import MetadataCustomizerDialog
from gui.metadata_report import MetadataReportDialog


class AdversarialWorker(QThread):
    """
    Background QThread that runs adversarial_perturb() so the GUI stays
    responsive. Emits progress(int, int, float) each iteration and
    finished_result(np.ndarray, float) when done.
    """
    progress = Signal(int, int, float)      # (iter, total, score)
    finished_result = Signal(object, float)  # (result_image_or_None, final_score)

    def __init__(self, image, pro_regions, effect_kwargs, parent=None):
        super().__init__(parent)
        self._image = image
        self._pro_regions = pro_regions
        self._effect_kwargs = effect_kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from src.models.image_processor import ImageProcessor as _IP
            result = self._image.copy()
            scores = []
            iters_per_face = 40
            face_idx = 0

            for det in self._pro_regions:
                if self._cancelled:
                    self.finished_result.emit(None, 1.0)
                    return
                if det["type"] != "polygon":
                    continue
                strength = self._effect_kwargs.get("strength", 21)
                face_offset = face_idx * iters_per_face

                def _cb(i, total, score, off=face_offset):
                    self.progress.emit(off + i, total, score)

                # Primary visual effect applied under adversarial noise. "blur" is the recommended architecture baseline.
                hybrid_effect = "blur"

                result, score = _IP.apply_adversarial_hybrid(
                    result,
                    det["points"],
                    hybrid_effect,
                    max_eps=110,
                    iters=iters_per_face,
                    block_size=32,
                    progress_callback=_cb,
                    should_cancel=lambda: self._cancelled,
                    strength=strength,
                )
                scores.append(score)
                face_idx += 1

                if self._cancelled:
                    self.finished_result.emit(None, 1.0)
                    return

            worst_score = max(scores) if scores else 1.0
            self.finished_result.emit(result, worst_score)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"AdversarialWorker error: {e}")
            self.finished_result.emit(None, 1.0)


class Var:
    """A helper class to emulate Tkinter variables with setter/getter and listeners."""
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


class ImageCanvas(QWidget):
    """Custom canvas widget for drawing image, selection rects, and handling drag & drop."""
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.pixmap = None
        self.image_pos = (0, 0)
        self.drag_start = None
        self.drag_end = None
        self.drawing = False
        self._drag_active = False

    def set_image(self, pixmap, x, y):
        self.pixmap = pixmap
        self.image_pos = (x, y)
        self.update()

    def clear_canvas(self):
        self.pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        colors = getattr(self.main_window, 'colors', COLORS)

        # Fill background
        bg_color = QColor(colors.get('canvas_bg', '#121212'))
        painter.fillRect(self.rect(), bg_color)

        # Draw border
        if self._drag_active:
            border_color = QColor(colors.get('accent_green', '#26a69a'))
            pen = QPen(border_color, 4)
        else:
            border_color = QColor(colors.get('accent_cyan', '#00fff5'))
            pen = QPen(border_color, 2)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        if self.pixmap:
            # Draw the image
            painter.drawPixmap(self.image_pos[0], self.image_pos[1], self.pixmap)

            # Draw saved drawing regions
            pen_region = QPen(QColor(colors.get('accent_cyan', '#00fff5')), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen_region)
            for (rx, ry, rw, rh) in self.main_window.drawing_regions:
                cx = int(rx * self.main_window.display_scale) + self.image_pos[0]
                cy = int(ry * self.main_window.display_scale) + self.image_pos[1]
                cw = int(rw * self.main_window.display_scale)
                ch = int(rh * self.main_window.display_scale)
                painter.drawRect(cx, cy, cw, ch)

            # Draw currently drawing rectangle
            if self.drawing and self.drag_start and self.drag_end:
                pen_current = QPen(QColor(colors.get('accent_cyan', '#00fff5')), 3)
                painter.setPen(pen_current)
                x = min(self.drag_start.x(), self.drag_end.x())
                y = min(self.drag_start.y(), self.drag_end.y())
                w = abs(self.drag_start.x() - self.drag_end.x())
                h = abs(self.drag_start.y() - self.drag_end.y())
                painter.drawRect(x, y, w, h)
        else:
            # Draw placeholder
            self.draw_placeholder(painter, colors)

    def draw_placeholder(self, painter, colors):
        w = self.width()
        h = self.height()
        if w <= 1 or h <= 1:
            w = 900
            h = 700

        # Draw dashed rectangle
        pen = QPen(QColor(colors.get('bg_light', '#1a2332')), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(30, 30, w - 60, h - 60)

        # Draw text & icon
        font_icon = QFont("Helvetica", 48)
        painter.setFont(font_icon)
        painter.setPen(QColor(colors.get('accent_cyan', '#00fff5')))
        painter.drawText(self.rect().adjusted(0, -40, 0, -40), Qt.AlignmentFlag.AlignCenter, "📥")

        # Load strings with fallbacks
        locale_manager = self.main_window.locale_manager
        title_text = locale_manager.get("ui.canvas.placeholder_title")
        if title_text == "ui.canvas.placeholder_title":
            title_text = "Drag & Drop Image Here"

        sub_text = locale_manager.get("ui.canvas.placeholder_subtitle")
        if sub_text == "ui.canvas.placeholder_subtitle":
            sub_text = "or click 'Load Image' to start"

        font_title = QFont("Helvetica", 16, QFont.Weight.Bold)
        painter.setFont(font_title)
        painter.drawText(self.rect().adjusted(0, 50, 0, 50), Qt.AlignmentFlag.AlignCenter, title_text)

        font_sub = QFont("Helvetica", 11)
        painter.setFont(font_sub)
        painter.setPen(QColor(colors.get('text_gray', '#888888')))
        painter.drawText(self.rect().adjusted(0, 120, 0, 120), Qt.AlignmentFlag.AlignCenter, sub_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            mode = self.main_window.detection_mode.get()
            if mode == "manual" and self.main_window.original_image is not None:
                self.drawing = True
                self.drag_start = event.position().toPoint()
                self.drag_end = event.position().toPoint()
                self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.drag_end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            self.drag_end = event.position().toPoint()

            x1 = int((self.drag_start.x() - self.image_pos[0]) / self.main_window.display_scale)
            y1 = int((self.drag_start.y() - self.image_pos[1]) / self.main_window.display_scale)
            x2 = int((self.drag_end.x() - self.image_pos[0]) / self.main_window.display_scale)
            y2 = int((self.drag_end.y() - self.image_pos[1]) / self.main_window.display_scale)

            x, w = (x1, x2 - x1) if x2 > x1 else (x2, x1 - x2)
            y, h = (y1, y2 - y1) if y2 > y1 else (y2, y1 - y2)

            if self.main_window.original_image is not None:
                img_h, img_w = self.main_window.original_image.shape[:2]
                x = max(0, min(x, img_w - 1))
                y = max(0, min(y, img_h - 1))
                w = min(w, img_w - x)
                h = min(h, img_h - y)

            if w > 10 and h > 10:
                self.main_window.drawing_regions.append((x, y, w, h))
                self.main_window.status_label.setText(
                    f"Added region ({len(self.main_window.drawing_regions)} total)"
                )
            self.drag_start = None
            self.drag_end = None
            self.update()

    def wheelEvent(self, event):
        if self.main_window.original_image is None:
            return
        delta = event.angleDelta().y()
        scale_multiplier = 1.0
        if delta > 0:
            scale_multiplier = 1.1
        elif delta < 0:
            scale_multiplier = 0.9

        new_scale = self.main_window.display_scale * scale_multiplier
        if 0.1 < new_scale < 5.0:
            self.main_window.display_scale = new_scale
            if self.main_window.processed_image is not None:
                self.main_window.display_image(self.main_window.processed_image)
            else:
                self.main_window.display_image(self.main_window.original_image)
            self.main_window.status_label.setText(f"Zoom: {int(self.main_window.display_scale * 100)}%")

    def resizeEvent(self, event):
        self.main_window.on_canvas_resize()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_active = True
            self.update()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self.update()

    def dropEvent(self, event):
        self._drag_active = False
        self.update()
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    self.main_window.handle_dropped_file(file_path)


class AdvancedPrivacyStudioPro(QMainWindow):
    """Main window class for the PyQt6 version of DotScramble."""
    
    auth_success_signal = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_success_signal.connect(self._handle_auth_callback)
        self.colors = COLORS.copy()

        # Initialize Managers
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

        # Variables
        self.original_image = None
        self.processed_image = None
        self.preview_image = None
        self.image_path = None
        self.original_exif_bytes = None

        # State Variables
        self.target_word_var = Var(value="")
        self.detection_mode = Var(value="face")
        self.effect_type = Var(value="blur")
        self.blur_strength = Var(value=BLUR_RANGE['default'])
        self.pixel_size = Var(value=PIXEL_RANGE['default'])
        self.opacity = Var(value=OPACITY_RANGE['default'])
        self.edge_blur = Var(value=EDGE_BLUR_RANGE['default'])
        self.real_time_preview = Var(value=False)
        self.language_var = Var(value="en")
        self.scrub_exif = Var(value=False)
        self.spoof_metadata = Var(value=False)
        self.spoof_profile = Var(value="troll")
        self.custom_field_actions = None

        self.init_ui_strings()

        # Drawing variables
        self.drawing_regions = []
        self.display_scale = 1.0
        self.display_offset = (0, 0)

        # Debounce timer for canvas resize
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_canvas_resize)

        # Auto-updater
        self.auto_updater = AutoUpdater(self)

        # Setup main UI structure
        self.update_window_title()
        self.resize(1400, 900)
        self.setMinimumSize(800, 600)

        self.create_widgets()
        self.create_menu_bar()

        # Bind settings changed variables to sync layout controls
        self.real_time_preview.add_listener(lambda val: self.preview_check.setChecked(val))
        self.scrub_exif.add_listener(lambda val: self.cb_scrub.setChecked(val))
        self.spoof_metadata.add_listener(lambda val: self.cb_spoof.setChecked(val))
        self.detection_mode.add_listener(self._update_detection_mode_radios)
        self.effect_type.add_listener(self._update_effect_type_radios)
        self.spoof_profile.add_listener(self._update_spoof_profile_radios)
        self.target_word_var.add_listener(lambda val: self.word_entry.setText(val) if hasattr(self, 'word_entry') else None)

        self.db_manager.increment_stat('app_launches')

        # Silent update check
        if UPDATE_CONFIG['auto_check']:
            QTimer.singleShot(3000, lambda: self.auto_updater.check_for_updates_silently(self.on_update_ready))

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

    def update_window_title(self):
        title = self.locale_manager.get("app.title")
        if self.license_manager.is_max_activated:
            title += " (PRO)"
        self.setWindowTitle(title)

    def init_ui_strings(self):
        _ = self.locale_manager.get
        self.ui_strings = {
            "ui.header.title": Var(value=_("ui.header.title")),
            "ui.header.preview": Var(value=_("ui.header.preview")),
            "ui.controls.title": Var(value=_("ui.controls.title")),
            "ui.controls.load_image": Var(value=_("ui.controls.load_image")),
            "ui.controls.effect_type": Var(value=_("ui.controls.effect_type")),
            "ui.controls.detection_mode": Var(value=_("ui.controls.detection_mode")),
            "ui.controls.target_text": Var(value=_("ui.controls.target_text")),
            "ui.controls.blur_strength": Var(value=_("ui.controls.blur_strength")),
            "ui.controls.pixel_size": Var(value=_("ui.controls.pixel_size")),
            "ui.controls.opacity": Var(value=_("ui.controls.opacity")),
            "ui.controls.apply_effect": Var(value=_("ui.controls.apply_effect")),
            "ui.controls.undo": Var(value=_("ui.controls.undo")),
            "ui.controls.redo": Var(value=_("ui.controls.redo")),
            "ui.controls.clear_selections": Var(value=_("ui.controls.clear_selections")),
            "ui.controls.save_result": Var(value=_("ui.controls.save_result")),
            "ui.controls.batch_process": Var(value=_("ui.controls.batch_process")),
            "ui.controls.tip": Var(value=_("ui.controls.tip")),
            "ui.buttons.load": Var(value=_("ui.buttons.load")),
            "ui.buttons.apply": Var(value=_("ui.buttons.apply")),
            "ui.buttons.save": Var(value=_("ui.buttons.save")),
            "ui.buttons.reset": Var(value=_("ui.buttons.reset"))
        }

        self.effect_keys = [
            "effects.blur", "effects.pixelation", "effects.black_bar",
            "effects.gradient", "effects.mosaic", "effects.glass", "effects.oil_paint",
            "effects.ai_evasion"
        ]
        self.effect_strings = [Var(value=_(k)) for k in self.effect_keys]

        self.detection_keys = [
            "detection.face", "detection.eye", "detection.body",
            "detection.license_plate", "detection.text", "detection.manual", "detection.full"
        ]
        self.detection_strings = [Var(value=_(k)) for k in self.detection_keys]

    def create_menu_bar(self):
        menubar = self.menuBar()
        menubar.clear()

        _ = self.locale_manager.get

        # File Menu
        file_menu = menubar.addMenu(_("menu.file"))
        open_action = file_menu.addAction(_("menu.file_items.open_image"), self.load_image)
        open_action.setShortcut("Ctrl+O")

        recent_menu = file_menu.addMenu(_("menu.file_items.open_recent"))
        recent_files = self.db_manager.get_recent_files(5)
        if recent_files:
            for file_info in recent_files:
                file_path = file_info['path']
                file_name = os.path.basename(file_path)
                recent_menu.addAction(file_name, lambda checked=False, p=file_path: self.load_image_from_path(p))
            recent_menu.addSeparator()
            recent_menu.addAction(_("menu.file_items.clear_history"), self.clear_recent_history)
        else:
            no_recent_action = recent_menu.addAction(_("menu.file_items.no_recent"))
            no_recent_action.setEnabled(False)

        file_menu.addSeparator()
        save_action = file_menu.addAction(_("menu.file_items.save_result"), self.save_image)
        save_action.setShortcut("Ctrl+S")
        file_menu.addAction(_("menu.file_items.save_comparison"), self.save_comparison)

        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.open_exports"), self.open_exports_folder)

        file_menu.addSeparator()
        batch_action = file_menu.addAction(_("menu.file_items.batch_process"), self.open_batch_window)
        batch_action.setShortcut("Ctrl+B")

        file_menu.addSeparator()
        file_menu.addAction(_("menu.file_items.exit"), self.close)

        # Edit Menu
        edit_menu = menubar.addMenu(_("menu.edit"))
        undo_action = edit_menu.addAction(_("menu.edit_items.undo"), self.undo)
        undo_action.setShortcut("Ctrl+Z")
        redo_action = edit_menu.addAction(_("menu.edit_items.redo"), self.redo)
        redo_action.setShortcut("Ctrl+Y")

        edit_menu.addSeparator()
        clear_action = edit_menu.addAction(_("menu.edit_items.clear_selections"), self.clear_regions)
        clear_action.setShortcut("Ctrl+D")
        edit_menu.addAction(_("menu.edit_items.reset_image"), self.reset_image)

        # Presets Menu
        presets_menu = menubar.addMenu(_("menu.presets"))
        presets_menu.addAction(_("menu.presets_items.save_settings"), self.save_preset)
        presets_menu.addAction(_("menu.presets_items.load_preset"), self.load_preset)
        presets_menu.addAction(_("menu.presets_items.manage_presets"), self.manage_presets)

        # View Menu
        view_menu = menubar.addMenu(_("menu.view"))
        theme_menu = view_menu.addMenu(_("menu.view_items.themes"))
        for theme_name, theme_key in self.theme_manager.get_theme_names():
            theme_menu.addAction(theme_name, lambda checked=False, k=theme_key: self.change_theme(k))

        lang_menu = view_menu.addMenu(_("menu.view_items.language"))
        languages = self.locale_manager.get_language_list()
        lang_group = QActionGroup(self)
        for lang in languages:
            lang_code = lang['code']
            display_name = f"{lang['name']} ({lang['native_name']})"
            action = lang_menu.addAction(display_name)
            action.setCheckable(True)
            if lang_code == self.language_var.get():
                action.setChecked(True)
            action.triggered.connect(lambda checked=False, code=lang_code: self.change_language(code))
            lang_group.addAction(action)

        # Help Menu
        help_menu = menubar.addMenu(_("menu.help"))
        if self.license_manager.is_max_activated:
            pro_act = help_menu.addAction(_("ui.tier.pro_activated_menu"))
            pro_act.setEnabled(False)
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

    def create_widgets(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(10)

        # Header Frame
        self.header_frame = QFrame()
        self.header_frame.setObjectName("HeaderFrame")
        self.header_frame.setFixedHeight(70)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(20, 10, 20, 10)

        self.title_label = QLabel(self.ui_strings["ui.header.title"].get())
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setFont(QFont("Helvetica", 20, QFont.Weight.Bold))
        header_layout.addWidget(self.title_label)

        header_layout.addStretch(1)

        self.preview_check = QCheckBox(self.ui_strings["ui.header.preview"].get())
        self.preview_check.setFont(QFont("Helvetica", 11))
        self.preview_check.stateChanged.connect(lambda state: self.real_time_preview.set(state == 2))
        header_layout.addWidget(self.preview_check)

        main_layout.addWidget(self.header_frame)

        # Main splitter (separates Sidebar and Canvas Area)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter, 1)

        # Sidebar Left Panel Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setMinimumWidth(260)
        self.scroll_area.setMaximumWidth(400)

        scroll_content = QWidget()
        scroll_content.setObjectName("SidebarContainer")
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(20, 15, 20, 15)
        self.scroll_layout.setSpacing(12)

        self.add_controls_to_panel(scroll_content)

        self.scroll_area.setWidget(scroll_content)
        self.splitter.addWidget(self.scroll_area)

        # Right Panel (Toolbar + Canvas)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Toolbar Frame
        self.toolbar_frame = QFrame()
        self.toolbar_frame.setObjectName("ToolbarFrame")
        self.toolbar_frame.setMinimumHeight(55)
        toolbar_layout = QHBoxLayout(self.toolbar_frame)
        toolbar_layout.setContentsMargins(12, 6, 12, 6)
        toolbar_layout.setSpacing(10)

        # Load Image Button
        self.toolbar_load_btn = QPushButton("📂 Load Image")
        self.toolbar_load_btn.clicked.connect(self.load_image)
        toolbar_layout.addWidget(self.toolbar_load_btn)

        # Apply Effect Button
        self.toolbar_process_btn = QPushButton("🌫️ Apply Effect")
        self.toolbar_process_btn.clicked.connect(self.process_image)
        self.toolbar_process_btn.setEnabled(False)
        toolbar_layout.addWidget(self.toolbar_process_btn)

        # Save Result Button
        self.toolbar_save_btn = QPushButton("💾 Save Result")
        self.toolbar_save_btn.clicked.connect(self.save_image)
        self.toolbar_save_btn.setEnabled(False)
        toolbar_layout.addWidget(self.toolbar_save_btn)

        # Clear All Button
        self.toolbar_clear_btn = QPushButton("🧹 Clear All")
        self.toolbar_clear_btn.clicked.connect(self.clear_regions)
        toolbar_layout.addWidget(self.toolbar_clear_btn)

        # Vertical Divider Line
        v_line = QFrame()
        v_line.setObjectName("ToolbarSeparator")
        v_line.setFrameShape(QFrame.Shape.VLine)
        toolbar_layout.addWidget(v_line)

        # Undo Button
        self.toolbar_undo_btn = QPushButton("↩️ Undo")
        self.toolbar_undo_btn.clicked.connect(self.undo)
        self.toolbar_undo_btn.setEnabled(False)
        toolbar_layout.addWidget(self.toolbar_undo_btn)

        # Redo Button
        self.toolbar_redo_btn = QPushButton("↪️ Redo")
        self.toolbar_redo_btn.clicked.connect(self.redo)
        self.toolbar_redo_btn.setEnabled(False)
        toolbar_layout.addWidget(self.toolbar_redo_btn)

        toolbar_layout.addStretch(1)
        right_layout.addWidget(self.toolbar_frame)

        # Custom Image Canvas
        self.canvas = ImageCanvas(self)
        right_layout.addWidget(self.canvas, 1)

        self.splitter.addWidget(self.right_panel)

        # Initial sizes and stretch factors for splitter
        self.splitter.setSizes([350, 1050])
        self.splitter.setStretchFactor(0, 0)  # sidebar - do not grow automatically
        self.splitter.setStretchFactor(1, 1)  # canvas - grow with window

        # Status Bar
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("StatusBar")
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel(self.locale_manager.get("ui.status.ready"))
        self.status_label.setFont(QFont("Helvetica", 10))
        self.status_bar.addWidget(self.status_label, 1)

        self.update_btn = QPushButton("🔄 Restart to Update")
        self.update_btn.setObjectName("update_btn")
        self.update_btn.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self.apply_update)
        self.status_bar.addPermanentWidget(self.update_btn)

        self.info_label = QLabel("")
        self.info_label.setFont(QFont("Helvetica", 9))
        self.status_bar.addPermanentWidget(self.info_label)

    def add_controls_to_panel(self, parent):
        # Panel Title
        self.controls_title_label = QLabel(self.ui_strings["ui.controls.title"].get())
        self.controls_title_label.setObjectName("TitleLabel")
        self.controls_title_label.setFont(QFont("Helvetica", 18, QFont.Weight.Bold))
        self.controls_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_layout.addWidget(self.controls_title_label)

        # Tier Badge
        self.create_tier_badge(self.scroll_layout)

        # Load Image Button
        self.load_btn = QPushButton(self.ui_strings["ui.controls.load_image"].get())
        self.load_btn.setObjectName("primary_action")
        self.load_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        self.load_btn.clicked.connect(self.load_image)
        self.scroll_layout.addWidget(self.load_btn)

        self.add_separator(self.scroll_layout)

        # Effect Section
        self.create_effect_section(self.scroll_layout)

        self.add_separator(self.scroll_layout)

        # Detection Section
        self.create_detection_section(self.scroll_layout)

        self.add_separator(self.scroll_layout)

        # Parameters Section
        self.create_parameters_section(self.scroll_layout)

        self.add_separator(self.scroll_layout)

        # Action Buttons
        self.create_action_buttons(self.scroll_layout)

        self.add_separator(self.scroll_layout)

        # EXIF section
        self.create_exif_section(self.scroll_layout)

        # Tip label
        self.tip_label = QLabel(self.ui_strings["ui.controls.tip"].get())
        self.tip_label.setObjectName("tip_label")
        _f = QFont("Helvetica", 9)
        _f.setItalic(True)
        self.tip_label.setFont(_f)
        self.tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tip_label.setWordWrap(True)
        self.scroll_layout.addWidget(self.tip_label)

    def create_tier_badge(self, parent_layout):
        self.tier_badge_container = QFrame()
        self.tier_badge_layout = QVBoxLayout(self.tier_badge_container)
        self.tier_badge_layout.setContentsMargins(12, 10, 12, 10)
        self.tier_badge_layout.setSpacing(4)

        self.tier_icon_label = QLabel()
        self.tier_icon_label.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        self.tier_badge_layout.addWidget(self.tier_icon_label)

        self.tier_desc_label = QLabel()
        self.tier_desc_label.setFont(QFont("Helvetica", 8))
        self.tier_badge_layout.addWidget(self.tier_desc_label)

        self.tier_upgrade_btn = QPushButton("")
        self.tier_upgrade_btn.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.tier_upgrade_btn.clicked.connect(self.show_activation_dialog)
        self.tier_badge_layout.addWidget(self.tier_upgrade_btn)

        parent_layout.addWidget(self.tier_badge_container)
        self.update_tier_badge_ui()

    def update_tier_badge_ui(self):
        is_pro = self.license_manager.is_max_activated
        _ = self.locale_manager.get

        if is_pro:
            icon_text = _("ui.tier.pro_badge")
            desc_text = _("ui.tier.pro_desc")
            self.tier_upgrade_btn.setVisible(False)
            self.tier_badge_container.setObjectName("tier_badge_pro")
            self.tier_icon_label.setObjectName("tier_icon_pro")
            self.tier_desc_label.setObjectName("tier_desc_pro")
        else:
            icon_text = _("ui.tier.free_badge")
            desc_text = _("ui.tier.free_desc")
            self.tier_upgrade_btn.setVisible(True)
            self.tier_upgrade_btn.setObjectName("tier_upgrade_btn")
            self.tier_badge_container.setObjectName("tier_badge_free")
            self.tier_icon_label.setObjectName("tier_icon_free")
            self.tier_desc_label.setObjectName("tier_desc_free")

        self.tier_upgrade_btn.setText(_("ui.tier.upgrade_btn"))
        self.tier_icon_label.setText(icon_text)
        self.tier_desc_label.setText(desc_text)

        for widget in (self.tier_badge_container, self.tier_icon_label, self.tier_desc_label, self.tier_upgrade_btn):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def create_effect_section(self, parent_layout):
        self.effect_section_label = QLabel(self.ui_strings["ui.controls.effect_type"].get())
        self.effect_section_label.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
        parent_layout.addWidget(self.effect_section_label)

        effect_container = QFrame()
        effect_layout = QVBoxLayout(effect_container)
        effect_layout.setContentsMargins(0, 0, 0, 0)
        effect_layout.setSpacing(5)

        self.effect_radios = []
        self.effect_button_group = QButtonGroup(self)

        effect_values = ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint", "ai_evasion"]
        is_pro = self.license_manager.is_max_activated
        for idx, (key, val) in enumerate(zip(self.effect_keys, effect_values)):
            rb = QRadioButton(self.effect_strings[idx].get())
            rb.setFont(QFont("Helvetica", 10))
            rb.toggled.connect(lambda checked, v=val: self._on_effect_rb_toggled(checked, v))
            self.effect_button_group.addButton(rb, idx)
            effect_layout.addWidget(rb)
            self.effect_radios.append(rb)
            # AI Evasion is PRO-only and only meaningful for face detection mode
            if val == "ai_evasion":
                rb.setEnabled(is_pro)
                rb.setToolTip("🛡️ PRO — Hides face from AI detectors (face mode only, ~30-90 sec)")
            if val == "blur":
                rb.setChecked(True)

        parent_layout.addWidget(effect_container)

    def _on_effect_rb_toggled(self, checked, value):
        if checked:
            self.effect_type.set(value)
            self.on_effect_change()

    def create_detection_section(self, parent_layout):
        self.detection_section_label = QLabel(self.ui_strings["ui.controls.detection_mode"].get())
        self.detection_section_label.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
        parent_layout.addWidget(self.detection_section_label)

        self.detection_container = QFrame()
        self.detection_layout = QVBoxLayout(self.detection_container)
        self.detection_layout.setContentsMargins(0, 0, 0, 0)
        self.detection_layout.setSpacing(5)

        parent_layout.addWidget(self.detection_container)

        self.detection_button_group = QButtonGroup(self)
        self.detection_button_group.setExclusive(True)

        # target_text row
        self.target_text_row = QWidget()
        tt_layout = QHBoxLayout(self.target_text_row)
        tt_layout.setContentsMargins(0, 0, 0, 0)

        self.target_text_rb = QRadioButton(self.ui_strings["ui.controls.target_text"].get())
        self.target_text_rb.setFont(QFont("Helvetica", 10))
        self.target_text_rb.toggled.connect(lambda checked: self._on_detection_rb_toggled(checked, "target_text"))
        self.detection_button_group.addButton(self.target_text_rb, 7)
        tt_layout.addWidget(self.target_text_rb)

        self.target_text_badge = QPushButton()
        self.target_text_badge.setFont(QFont("Helvetica", 7, QFont.Weight.Bold))
        self.target_text_badge.setFlat(True)
        self.target_text_badge.clicked.connect(self.show_activation_dialog)
        tt_layout.addWidget(self.target_text_badge)
        tt_layout.addStretch(1)
        self.detection_layout.addWidget(self.target_text_row)

        # Target Text Input Field
        self.text_input_frame = QFrame()
        tif_layout = QVBoxLayout(self.text_input_frame)
        tif_layout.setContentsMargins(10, 5, 10, 5)

        self.target_text_label = QLabel(self.ui_strings["ui.controls.target_text"].get())
        self.target_text_label.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        tif_layout.addWidget(self.target_text_label)

        self.word_entry = QLineEdit()
        self.word_entry.textChanged.connect(self.target_word_var.set)
        tif_layout.addWidget(self.word_entry)
        self.text_input_frame.setVisible(False)
        self.detection_layout.addWidget(self.text_input_frame)

        # Other detection modes
        self.detection_radios = []
        self.detection_rows = []
        self.detection_badges = []

        self.detection_modes_list = [
            ("face", 0), ("eye", 1), ("body", 2),
            ("license_plate", 3), ("text", 4), ("manual", 5), ("full", 6)
        ]

        for value, idx in self.detection_modes_list:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            rb = QRadioButton(self.detection_strings[idx].get())
            rb.setFont(QFont("Helvetica", 10))
            rb.toggled.connect(lambda checked, val=value: self._on_detection_rb_toggled(checked, val))
            self.detection_button_group.addButton(rb, idx)
            row_layout.addWidget(rb)
            self.detection_radios.append(rb)

            badge = QPushButton()
            badge.setFont(QFont("Helvetica", 7, QFont.Weight.Bold))
            badge.setFlat(True)
            badge.clicked.connect(self.show_activation_dialog)
            row_layout.addWidget(badge)
            self.detection_badges.append((value, badge))

            row_layout.addStretch(1)
            self.detection_layout.addWidget(row_widget)
            self.detection_rows.append((value, row_widget))
            if value == "face":
                rb.setChecked(True)

        self.update_detection_section_ui()

    def _on_detection_rb_toggled(self, checked, value):
        if checked:
            self.detection_mode.set(value)
            self.on_detection_change()

    def update_detection_section_ui(self):
        is_pro = self.license_manager.is_max_activated
        colors = getattr(self, 'colors', COLORS)

        effect = self.effect_type.get()
        is_ai_evasion = (effect == "ai_evasion")

        # Disable target text if AI evasion is active
        if hasattr(self, 'target_text_rb'):
            self.target_text_rb.setEnabled(not is_ai_evasion)

        # Update other radios
        if hasattr(self, 'detection_radios'):
            for rb, (value, idx) in zip(self.detection_radios, self.detection_modes_list):
                if is_ai_evasion:
                    rb.setEnabled(value == "face")
                else:
                    rb.setEnabled(True)

        kind = "pro" if not is_pro else "ai_active"
        self._style_badge(self.target_text_badge, kind, colors)

        pro_only = {"body", "license_plate", "text"}
        ai_upgrade = {"face", "eye"}

        for value, badge in self.detection_badges:
            if value in pro_only and not is_pro:
                self._style_badge(badge, "pro", colors)
            elif value in ai_upgrade and is_pro:
                self._style_badge(badge, "ai_active", colors)
            elif value in ai_upgrade and not is_pro:
                self._style_badge(badge, "ai_upgrade", colors)
            else:
                badge.setVisible(False)

    def _style_badge(self, badge, kind, colors=None):
        if kind == "pro":
            text = "⭐ PRO"
            badge.setObjectName("badge_pro")
            badge.setEnabled(True)
            badge.setVisible(True)
        elif kind == "ai_active":
            text = "🛡️ Anti-AI"
            badge.setObjectName("badge_ai_active")
            badge.setEnabled(False)
            badge.setVisible(True)
        elif kind == "ai_upgrade":
            text = "🔓→🛡️"
            badge.setObjectName("badge_ai_upgrade")
            badge.setEnabled(True)
            badge.setVisible(True)
        else:
            badge.setVisible(False)
            return

        badge.setText(text)
        badge.style().unpolish(badge)
        badge.style().polish(badge)

    def create_slider(self, parent_layout, label_text, variable, min_val, max_val, value_label_object_name=None, resolution=1):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Store label widget reference for updates
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        value_lbl = QLabel(str(variable.get()))
        value_lbl.setFont(QFont("Helvetica", 10))
        if value_label_object_name:
            value_lbl.setObjectName(value_label_object_name)
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setSingleStep(resolution)
        slider.setValue(variable.get())
        slider.valueChanged.connect(lambda val: self._on_slider_changed(val, variable, value_lbl))
        layout.addWidget(slider)

        parent_layout.addWidget(frame)

        # Save references for layout and label updates
        frame.label_widget = lbl
        return frame

    def _on_slider_changed(self, val, variable, value_lbl):
        variable.set(val)
        value_lbl.setText(str(val))
        self.on_parameter_change()

    def create_parameters_section(self, parent_layout):
        self.params_frame = QFrame()
        params_layout = QVBoxLayout(self.params_frame)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(10)

        self.blur_param = self.create_slider(params_layout, self.ui_strings["ui.controls.blur_strength"].get(),
                                             self.blur_strength,
                                             BLUR_RANGE['min'], BLUR_RANGE['max'],
                                             value_label_object_name="blur_value_label", resolution=2)
        # Fetch reference for updating texts
        self.blur_param_label = self.blur_param.label_widget

        self.pixel_param = self.create_slider(params_layout, self.ui_strings["ui.controls.pixel_size"].get(),
                                              self.pixel_size,
                                              PIXEL_RANGE['min'], PIXEL_RANGE['max'],
                                              value_label_object_name="pixel_value_label", resolution=1)
        self.pixel_param_label = self.pixel_param.label_widget

        self.opacity_param = self.create_slider(params_layout, self.ui_strings["ui.controls.opacity"].get(),
                                                self.opacity,
                                                OPACITY_RANGE['min'], OPACITY_RANGE['max'],
                                                value_label_object_name="opacity_value_label", resolution=1)
        self.opacity_param_label = self.opacity_param.label_widget

        parent_layout.addWidget(self.params_frame)
        self.update_parameter_visibility()

    def create_action_buttons(self, parent_layout):
        self.process_btn = QPushButton(self.ui_strings["ui.controls.apply_effect"].get())
        self.process_btn.setObjectName("process_btn")
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self.process_image)
        parent_layout.addWidget(self.process_btn)

        undo_frame = QWidget()
        undo_layout = QHBoxLayout(undo_frame)
        undo_layout.setContentsMargins(0, 0, 0, 0)

        self.undo_btn = QPushButton(self.ui_strings["ui.controls.undo"].get())
        self.undo_btn.setObjectName("undo_btn")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo)
        undo_layout.addWidget(self.undo_btn)

        self.redo_btn = QPushButton(self.ui_strings["ui.controls.redo"].get())
        self.redo_btn.setObjectName("redo_btn")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo)
        undo_layout.addWidget(self.redo_btn)
        parent_layout.addWidget(undo_frame)

        self.clear_btn = QPushButton(self.ui_strings["ui.controls.clear_selections"].get())
        self.clear_btn.setObjectName("clear_btn")
        self.clear_btn.clicked.connect(self.clear_regions)
        parent_layout.addWidget(self.clear_btn)

        self.save_btn = QPushButton(self.ui_strings["ui.controls.save_result"].get())
        self.save_btn.setObjectName("save_btn")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_image)
        parent_layout.addWidget(self.save_btn)

        self.batch_btn = QPushButton(self.ui_strings["ui.controls.batch_process"].get())
        self.batch_btn.clicked.connect(self.open_batch_window)
        parent_layout.addWidget(self.batch_btn)

    def create_exif_section(self, parent_layout):
        self.exif_section_frame = QFrame()
        self.exif_layout = QVBoxLayout(self.exif_section_frame)
        self.exif_layout.setContentsMargins(0, 0, 0, 0)
        self.exif_layout.setSpacing(8)

        parent_layout.addWidget(self.exif_section_frame)

        self.exif_title_label = QLabel()
        self.exif_title_label.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        self.exif_layout.addWidget(self.exif_title_label)

        # Scrub EXIF
        self.scrub_row = QWidget()
        sr_layout = QHBoxLayout(self.scrub_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)

        self.cb_scrub = QCheckBox("Strip all EXIF on save")
        self.cb_scrub.setFont(QFont("Helvetica", 10))
        self.cb_scrub.stateChanged.connect(self._on_scrub_state_changed)
        sr_layout.addWidget(self.cb_scrub)

        self.scrub_max_badge = QPushButton("⭐ Max")
        self.scrub_max_badge.setObjectName("scrub_max_badge")
        _f_scrub_badge = QFont("Helvetica", 9)
        _f_scrub_badge.setItalic(True)
        self.scrub_max_badge.setFont(_f_scrub_badge)
        self.scrub_max_badge.clicked.connect(self.show_activation_dialog)
        sr_layout.addWidget(self.scrub_max_badge)
        sr_layout.addStretch(1)
        self.exif_layout.addWidget(self.scrub_row)

        self.scrub_desc = QLabel("Permanently removes GPS, camera & device tags.")
        self.scrub_desc.setObjectName("scrub_desc")
        _f_scrub_desc = QFont("Helvetica", 8)
        _f_scrub_desc.setItalic(True)
        self.scrub_desc.setFont(_f_scrub_desc)
        self.scrub_desc.setWordWrap(True)
        self.exif_layout.addWidget(self.scrub_desc)

        # Divider
        self.exif_divider = QFrame()
        self.exif_divider.setObjectName("exif_divider")
        self.exif_divider.setFrameShape(QFrame.Shape.HLine)
        self.exif_layout.addWidget(self.exif_divider)

        # Spoof Metadata
        self.spoof_row = QWidget()
        s_layout = QHBoxLayout(self.spoof_row)
        s_layout.setContentsMargins(0, 0, 0, 0)

        self.cb_spoof = QCheckBox("Inject fake metadata on save")
        self.cb_spoof.setFont(QFont("Helvetica", 10))
        self.cb_spoof.stateChanged.connect(self._on_spoof_state_changed)
        s_layout.addWidget(self.cb_spoof)

        self.spoof_max_badge = QPushButton("⭐ Max")
        self.spoof_max_badge.setObjectName("spoof_max_badge")
        _f_spoof_badge = QFont("Helvetica", 9)
        _f_spoof_badge.setItalic(True)
        self.spoof_max_badge.setFont(_f_spoof_badge)
        self.spoof_max_badge.clicked.connect(self.show_activation_dialog)
        s_layout.addWidget(self.spoof_max_badge)
        s_layout.addStretch(1)
        self.exif_layout.addWidget(self.spoof_row)

        # Spoof profiles container
        self.spoof_profile_frame = QFrame()
        self.spf_layout = QVBoxLayout(self.spoof_profile_frame)
        self.spf_layout.setContentsMargins(15, 0, 0, 0)
        self.spf_layout.setSpacing(3)

        self.profile_radios = []
        self.profile_labels = {
            "ghost":  "👻 Ghost  — Nokia in Antarctica, year 2000",
            "troll":  "🌊 Troll  — Random ocean, vintage camera",
            "artist": "🎨 Artist — Hides GPS, keeps copyright",
            "custom": "⚙️  Custom  — per-field control"
        }

        self.profile_button_group = QButtonGroup(self)
        for idx, (val, text) in enumerate(self.profile_labels.items()):
            rb = QRadioButton(text)
            rb.setFont(QFont("Helvetica", 9))
            rb.toggled.connect(lambda checked, v=val: self._on_profile_rb_toggled(checked, v))
            self.profile_button_group.addButton(rb, idx)
            self.spf_layout.addWidget(rb)
            self.profile_radios.append((val, rb))

        self.customize_btn = QPushButton("⚙️  Open Metadata Editor…")
        self.customize_btn.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.customize_btn.clicked.connect(self._open_metadata_customizer)
        self.spf_layout.addWidget(self.customize_btn)
        self.customize_btn.setVisible(False)

        for val, rb in self.profile_radios:
            if val == "troll":
                rb.setChecked(True)

        self.exif_layout.addWidget(self.spoof_profile_frame)
        self.spoof_profile_frame.setVisible(False)

        self.spoof_desc = QLabel("Replaces real metadata with plausible decoys.")
        self.spoof_desc.setObjectName("spoof_desc")
        _f_spoof_desc = QFont("Helvetica", 8)
        _f_spoof_desc.setItalic(True)
        self.spoof_desc.setFont(_f_spoof_desc)
        self.spoof_desc.setWordWrap(True)
        self.exif_layout.addWidget(self.spoof_desc)

        self.update_exif_section_ui()

    def _on_profile_rb_toggled(self, checked, value):
        if checked:
            self.spoof_profile.set(value)
            self._on_profile_radio_changed()

    def update_exif_section_ui(self):
        is_max = self.license_manager.is_max_activated

        icon = "🛡️" if is_max else "🔒"
        self.exif_title_label.setText(f"{icon} Privacy — Metadata")
        self.exif_title_label.setObjectName("exif_title_pro" if is_max else "exif_title_free")
        self.exif_title_label.style().unpolish(self.exif_title_label)
        self.exif_title_label.style().polish(self.exif_title_label)

        self.cb_scrub.setEnabled(is_max)
        self.cb_spoof.setEnabled(is_max)
        self.scrub_max_badge.setVisible(not is_max)
        self.spoof_max_badge.setVisible(not is_max)

        for val, rb in self.profile_radios:
            rb.setEnabled(is_max)
        self.customize_btn.setEnabled(is_max)

    def update_effect_section_ui(self):
        is_pro = self.license_manager.is_max_activated
        if hasattr(self, 'effect_radios'):
            effect_values = ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint", "ai_evasion"]
            for rb, val in zip(self.effect_radios, effect_values):
                if val == "ai_evasion":
                    rb.setEnabled(is_pro)

    def _on_scrub_state_changed(self, state):
        val = (state == 2)
        if self.scrub_exif.get() != val:
            self.scrub_exif.set(val)
            self._on_scrub_toggled()

    def _on_spoof_state_changed(self, state):
        val = (state == 2)
        if self.spoof_metadata.get() != val:
            self.spoof_metadata.set(val)
            self._on_spoof_toggled()

    def _on_scrub_toggled(self):
        if self.scrub_exif.get():
            self.spoof_metadata.set(False)
            self.cb_spoof.setChecked(False)
            self.spoof_profile_frame.setVisible(False)

    def _on_spoof_toggled(self):
        if self.spoof_metadata.get():
            self.scrub_exif.set(False)
            self.cb_scrub.setChecked(False)
            self.spoof_profile_frame.setVisible(True)
            self._show_spoof_profile_frame()
        else:
            self.spoof_profile_frame.setVisible(False)
            self._hide_spoof_profile_frame()

    def _show_spoof_profile_frame(self):
        self.spoof_profile_frame.setVisible(True)
        if self.spoof_profile.get() == "custom":
            self.customize_btn.setVisible(True)
        else:
            self.customize_btn.setVisible(False)

    def _hide_spoof_profile_frame(self):
        self.spoof_profile_frame.setVisible(False)

    def _on_profile_radio_changed(self):
        if self.spoof_profile.get() == "custom":
            self.customize_btn.setVisible(True)
        else:
            self.customize_btn.setVisible(False)

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
            self.status_label.setText("Custom metadata rules saved.")

    def add_separator(self, parent_layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("separator")
        parent_layout.addWidget(line)

    def load_image(self):
        picker = ImagePicker(self)
        file_path = picker.open()
        if not file_path:
            return
        self.load_image_from_path(file_path)

    def load_image_from_path(self, file_path):
        if not file_path or not os.path.exists(file_path):
            QMessageBox.critical(self, "Error", "File not found!")
            return

        try:
            self.image_path = file_path
            self.db_manager.add_recent_file(file_path)

            # imdecode supports unicode file paths
            loaded_image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if loaded_image is None or loaded_image.size == 0:
                QMessageBox.critical(self, "Error", "Could not load image! File might be empty or unsupported.")
                self.original_image = None
                self.processed_image = None
                return

            self.original_exif_bytes = None
            try:
                pil_img = Image.open(file_path)
                if 'exif' in pil_img.info:
                    self.original_exif_bytes = pil_img.info['exif']
            except Exception:
                self.original_exif_bytes = None

            self.original_image = loaded_image
            self.processed_image = self.original_image.copy()
            self.drawing_regions = []
            self.history_manager.clear()

            self.display_image(self.original_image)
            self.process_btn.setEnabled(True)
            self.toolbar_process_btn.setEnabled(True)

            info = self.image_utils.get_image_info(self.original_image)
            self.status_label.setText(f"Loaded: {os.path.basename(file_path)}")
            self.info_label.setText(f"{info['width']}x{info['height']} | {info['size_kb']} KB")
            self.restore_button_states()

            # Refresh recent files menu
            self.create_menu_bar()
        except Exception as e:
            QMessageBox.critical(self, "Loading Error", f"Failed to load image:\n{str(e)}")
            self.original_image = None
            self.processed_image = None
            self.status_label.setText("Failed to load image")

    def display_image(self, cv_image):
        if cv_image is None or cv_image.size == 0:
            return

        try:
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        except cv2.error as e:
            QMessageBox.critical(self, "Display Error", f"Could not convert image: {e}")
            return

        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 900
            canvas_height = 700

        try:
            resized, scale = self.image_utils.resize_for_display(
                rgb_image, canvas_width, canvas_height
            )
        except Exception as e:
            QMessageBox.critical(self, "Display Error", f"Could not resize: {e}")
            return

        h, w, ch = resized.shape
        bytes_per_line = ch * w
        qimage = QImage(resized.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        qpixmap = QPixmap.fromImage(qimage)

        # Center position
        x = (canvas_width - w) // 2
        y = (canvas_height - h) // 2
        x = max(0, x)
        y = max(0, y)

        self.display_scale = scale
        self.display_offset = (x, y)
        self.canvas.set_image(qpixmap, x, y)

    def process_image(self):
        if self.original_image is None:
            return

        if self.processed_image is not None:
            self.history_manager.save_state(self.processed_image)

        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        self.processed_image = self.processed_image.copy()

        try:
            is_pro = self.license_manager.is_max_activated
            regions = []
            pro_regions = []

            if mode == "face":
                if is_pro:
                    pro_regions = self.detection_engine.detect_faces_pro(self.processed_image)
                    if not pro_regions:
                        regions = self.detection_engine.detect_faces(self.processed_image)
                else:
                    regions = self.detection_engine.detect_faces(self.processed_image)

            elif mode == "eye":
                if is_pro:
                    pro_regions = self.detection_engine.detect_eyes_pro(self.processed_image)
                    if not pro_regions:
                        regions = self.detection_engine.detect_eyes(self.processed_image)
                else:
                    regions = self.detection_engine.detect_eyes(self.processed_image)

            elif mode == "body":
                regions = self.detection_engine.detect_full_body(self.processed_image)
            elif mode == "license_plate":
                regions = self.detection_engine.detect_license_plates(self.processed_image)
            elif mode == "text":
                regions = self.detection_engine.detect_text(self.processed_image)
            elif mode == "target_text":
                word = self.target_word_var.get()
                if not word:
                    QMessageBox.warning(self, "Wait!", "Please type the word you want to blur.")
                    return
                regions = self.text_detector.detect_specific_word(self.processed_image, word)
                if not regions:
                    QMessageBox.information(self, "Info", f"Could not find the word '{word}' in this image.")
                    return
            elif mode == "manual":
                if not self.drawing_regions:
                    QMessageBox.information(self, "Info", "Draw regions on the image first!")
                    return
                regions = self.drawing_regions
            elif mode == "full":
                h, w = self.processed_image.shape[:2]
                regions = [(0, 0, w, h)]
            else:
                return

            # Apply FREE rectangle regions
            for (x, y, w, h) in regions:
                self.apply_effect_to_region(x, y, w, h, effect)

            effect_kwargs = dict(
                strength=self.blur_strength.get(),
                pixel_size=self.pixel_size.get(),
                opacity=self.opacity.get(),
            )

            # ── AI Evasion — async path ────────────────────────────────────────
            if effect == "ai_evasion" and pro_regions:
                polygon_regions = [d for d in pro_regions if d["type"] == "polygon"]
                if not polygon_regions:
                    QMessageBox.warning(self, "AI Evasion",
                        "AI Evasion works on face oval regions only.\n"
                        "No face oval detected — try Face (PRO) detection mode.")
                    return

                self._run_adversarial_async(
                    self.processed_image.copy(), polygon_regions, effect_kwargs
                )
                return  # Result delivered via signal when worker finishes

            # ── Standard PRO AI regions ────────────────────────────────────────
            for det in pro_regions:
                if det["type"] == "polygon":
                    self.processed_image = self.image_processor.apply_effect_to_polygon(
                        self.processed_image, det["points"], effect, **effect_kwargs
                    )
                elif det["type"] == "rotated_rect":
                    self.processed_image = self.image_processor.apply_effect_rotated(
                        self.processed_image,
                        det["center"], det["size"], det["angle"],
                        effect, **effect_kwargs
                    )

            total = len(regions) + len(pro_regions)
            badge = " 🛡️ Anti-AI" if pro_regions else ""
            self.display_image(self.processed_image)
            self.save_btn.setEnabled(True)
            self.toolbar_save_btn.setEnabled(True)
            self.status_label.setText(f"Processed {total} region(s){badge}")
            self.update_buttons()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Processing failed: {str(e)}")

    def _run_adversarial_async(self, image, pro_regions, effect_kwargs):
        """Launch AdversarialWorker in a background QThread with a progress dialog."""
        n_faces = len(pro_regions)
        total_iters = 40

        progress_dlg = QProgressDialog(
            "🛡️ Computing AI Evasion…\nThis may take 30–90 seconds.",
            "Cancel", 0, total_iters * n_faces, self
        )
        progress_dlg.setWindowTitle("AI Evasion — Processing")
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setValue(0)

        # Disable ALL detection/effect/load/batch controls while worker runs to prevent
        # concurrent access to MediaPipe and state corruption from main thread.
        self.process_btn.setEnabled(False)
        self.toolbar_process_btn.setEnabled(False)
        if hasattr(self, 'load_btn') and self.load_btn:
            self.load_btn.setEnabled(False)
        if hasattr(self, 'toolbar_load_btn') and self.toolbar_load_btn:
            self.toolbar_load_btn.setEnabled(False)
        if hasattr(self, 'batch_btn') and self.batch_btn:
            self.batch_btn.setEnabled(False)
        if hasattr(self, 'save_btn') and self.save_btn:
            self.save_btn.setEnabled(False)
        if hasattr(self, 'toolbar_save_btn') and self.toolbar_save_btn:
            self.toolbar_save_btn.setEnabled(False)

        self.effect_button_group.setExclusive(False)
        for rb in getattr(self, 'effect_radios', []):
            rb.setEnabled(False)
        self.detection_button_group.setExclusive(False)
        for rb in getattr(self, 'detection_radios', []):
            rb.setEnabled(False)

        self._adv_worker = AdversarialWorker(image, pro_regions, effect_kwargs, self)

        def on_progress(abs_i, total_per_face, score):
            progress_dlg.setValue(abs_i)
            face_num = ((abs_i - 1) // total_per_face) + 1 if total_per_face > 0 else 1
            iter_in_face = ((abs_i - 1) % total_per_face) + 1 if total_per_face > 0 else abs_i
            progress_dlg.setLabelText(
                f"🛡️ Face {face_num}/{n_faces} — iter {iter_in_face}/{total_per_face} | score {score:.2f}"
            )
            if progress_dlg.wasCanceled():
                self._adv_worker.cancel()

        def _restore_controls():
            self.process_btn.setEnabled(True)
            self.toolbar_process_btn.setEnabled(True)
            if hasattr(self, 'load_btn') and self.load_btn:
                self.load_btn.setEnabled(True)
            if hasattr(self, 'toolbar_load_btn') and self.toolbar_load_btn:
                self.toolbar_load_btn.setEnabled(True)
            if hasattr(self, 'batch_btn') and self.batch_btn:
                self.batch_btn.setEnabled(True)
            if hasattr(self, 'save_btn') and self.save_btn:
                self.save_btn.setEnabled(True)
            if hasattr(self, 'toolbar_save_btn') and self.toolbar_save_btn:
                self.toolbar_save_btn.setEnabled(True)

            is_pro = self.license_manager.is_max_activated
            effect_values = ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint", "ai_evasion"]
            for rb, val in zip(getattr(self, 'effect_radios', []), effect_values):
                rb.setEnabled(True if val != "ai_evasion" else is_pro)
            self.effect_button_group.setExclusive(True)
            for rb in getattr(self, 'detection_radios', []):
                rb.setEnabled(True)
            self.detection_button_group.setExclusive(True)

        def on_finished(result_image, final_score):
            progress_dlg.close()
            _restore_controls()

            if result_image is None:
                self.status_label.setText("AI Evasion cancelled.")
                return
            self.history_manager.save_state(self.processed_image)
            self.processed_image = result_image
            self.display_image(self.processed_image)
            self.save_btn.setEnabled(True)
            self.toolbar_save_btn.setEnabled(True)

            # Three distinct outcomes — never mislead the user
            if final_score == 0.0:
                msg = "✅ AI Evasion complete — face is hidden from AI detectors"
            elif final_score < 1.0:
                score_pct = int((1.0 - final_score) * 100)
                msg = f"⚠️ AI Evasion partial — {score_pct}% evasion rate"
            else:
                # score==1.0: adversarial step crashed; base blur was preserved (fail-closed)
                msg = "❌ AI Evasion failed — face is blurred but NOT verified against AI detection"
            self.status_label.setText(msg)
            self.update_buttons()

        self._adv_worker.progress.connect(on_progress)
        self._adv_worker.finished_result.connect(on_finished)
        progress_dlg.canceled.connect(self._adv_worker.cancel)
        self._adv_worker.start()

    def apply_effect_to_region(self, x, y, w, h, effect):
        if self.original_image is None:
            return
        try:
            self.processed_image = ImageProcessor.apply_effect_to_region(
                self.processed_image,
                x, y, w, h,
                effect_type=effect,
                strength=self.blur_strength.get(),
                pixel_size=self.pixel_size.get(),
                opacity=self.opacity.get()
            )
        except Exception as e:
            logger.error(f"Error applying effect to region: {e}")

    def save_image(self):
        if self.processed_image is None:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Processed Image",
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
                    if self.original_exif_bytes:
                        try:
                            pil_img = Image.open(file_path)
                            pil_img.save(file_path, exif=self.original_exif_bytes)
                        except Exception as e:
                            logger.error(f"EXIF restore warning: {e}")
            elif ext in ('.jpg', '.jpeg', '.png'):
                try:
                    _spoof_metadata(file_path, file_path, profile=profile)
                except Exception as e:
                    logger.error(f"Metadata spoof warning: {e}")
            else:
                if self.original_exif_bytes:
                    try:
                        pil_img = Image.open(file_path)
                        pil_img.save(file_path, exif=self.original_exif_bytes)
                    except Exception as e:
                        logger.error(f"EXIF restore warning: {e}")
        else:
            if self.original_exif_bytes:
                try:
                    pil_img = Image.open(file_path)
                    pil_img.save(file_path, exif=self.original_exif_bytes)
                except Exception as e:
                    logger.error(f"EXIF restore warning: {e}")

        QMessageBox.information(self, "Success", "Image saved successfully!")
        self.status_label.setText(f"Saved: {os.path.basename(file_path)}")

    def save_comparison(self):
        if self.original_image is None or self.processed_image is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Comparison Image",
            os.path.expanduser("~"),
            "JPEG Images (*.jpg);;PNG Images (*.png)"
        )
        if file_path:
            ExportManager.export_comparison(self.original_image, self.processed_image, file_path)
            QMessageBox.information(self, "Success", "Comparison saved!")

    def update_parameter_visibility(self):
        if not hasattr(self, 'blur_param') or not hasattr(self, 'pixel_param') or not hasattr(self, 'text_input_frame'):
            return
        self.blur_param.setVisible(False)
        self.pixel_param.setVisible(False)
        self.text_input_frame.setVisible(False)

        if self.detection_mode.get() == "target_text":
            self.text_input_frame.setVisible(True)

        effect = self.effect_type.get()
        if effect in ["blur", "glass"]:
            self.blur_param.setVisible(True)
        elif effect == "pixelation":
            self.pixel_param.setVisible(True)

    def undo(self):
        prev_image = self.history_manager.undo()
        if prev_image is not None:
            self.history_manager.add_to_redo(self.processed_image)
            self.processed_image = prev_image
            self.display_image(self.processed_image)
            self.status_label.setText("Undo successful")
            self.update_buttons()

    def redo(self):
        next_image = self.history_manager.redo()
        if next_image is not None:
            self.history_manager.save_state(self.processed_image)
            self.processed_image = next_image
            self.display_image(self.processed_image)
            self.status_label.setText("Redo successful")
            self.update_buttons()

    def clear_regions(self):
        self.drawing_regions = []
        self.canvas.drag_start = None
        self.canvas.drag_end = None
        if self.original_image is not None:
            self.display_image(self.processed_image)
        self.status_label.setText("Cleared all selections")
        self.canvas.update()

    def reset_image(self):
        if self.original_image is not None:
            self.processed_image = self.original_image.copy()
            self.display_image(self.processed_image)
            self.drawing_regions = []
            self.history_manager.clear()
            self.status_label.setText("Image reset to original")
            self.update_buttons()

    def switch_view(self, view_type):
        if view_type == 'original' and self.original_image is not None:
            self.display_image(self.original_image)
            self.status_label.setText("Viewing Original Image")
        elif view_type == 'processed' and self.processed_image is not None:
            self.display_image(self.processed_image)
            self.status_label.setText("Viewing Processed Image")
        elif view_type == 'compare':
            if self.original_image is None or self.processed_image is None:
                return
            h1, w1 = self.original_image.shape[:2]
            h2, w2 = self.processed_image.shape[:2]
            proc_img_resized = self.processed_image
            if (h1, w1) != (h2, w2):
                proc_img_resized = cv2.resize(self.processed_image, (w1, h1))
            divider = np.ones((h1, 10, 3), dtype=np.uint8) * 255
            comparison_image = np.hstack((self.original_image, divider, proc_img_resized))
            self.display_image(comparison_image)
            self.status_label.setText("Viewing Comparison Image")

    def restore_button_states(self):
        enabled = self.original_image is not None
        self.process_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.toolbar_process_btn.setEnabled(enabled)
        self.toolbar_clear_btn.setEnabled(enabled)

        save_enabled = self.processed_image is not None
        self.save_btn.setEnabled(save_enabled)
        self.toolbar_save_btn.setEnabled(save_enabled)
        self.update_buttons()

    def update_buttons(self):
        can_undo = self.history_manager.can_undo()
        self.undo_btn.setEnabled(can_undo)
        self.toolbar_undo_btn.setEnabled(can_undo)

        can_redo = self.history_manager.can_redo()
        self.redo_btn.setEnabled(can_redo)
        self.toolbar_redo_btn.setEnabled(can_redo)

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Enter preset name:")
        if ok and name:
            settings = {
                'effect_type': self.effect_type.get(),
                'detection_mode': self.detection_mode.get(),
                'blur_strength': self.blur_strength.get(),
                'pixel_size': self.pixel_size.get(),
                'opacity': self.opacity.get()
            }
            self.preset_manager.add_preset(name, settings)
            QMessageBox.information(self, "Success", f"Preset '{name}' saved!")

    def load_preset(self):
        presets = self.preset_manager.get_all_presets()
        if not presets:
            QMessageBox.information(self, "Info", "No presets available")
            return
        
        preset_names = list(presets.keys())
        name, ok = QInputDialog.getItem(self, "Load Preset", "Select preset to load:", preset_names, 0, False)
        if ok and name:
            settings = presets[name]
            self.effect_type.set(settings.get('effect_type', 'blur'))
            self.detection_mode.set(settings.get('detection_mode', 'face'))
            self.blur_strength.set(settings.get('blur_strength', BLUR_RANGE['default']))
            self.pixel_size.set(settings.get('pixel_size', PIXEL_RANGE['default']))
            self.opacity.set(settings.get('opacity', OPACITY_RANGE['default']))
            self.update_parameter_visibility()
            QMessageBox.information(self, "Success", f"Preset '{name}' loaded!")

    def manage_presets(self):
        presets = self.preset_manager.get_all_presets()
        if not presets:
            QMessageBox.information(self, "Info", "No presets to manage.")
            return
        
        preset_names = list(presets.keys())
        name, ok = QInputDialog.getItem(self, "Delete Preset", "Select preset to delete:", preset_names, 0, False)
        if ok and name:
            self.preset_manager.delete_preset(name)
            QMessageBox.information(self, "Success", f"Preset '{name}' deleted!")

    def open_batch_window(self):
        dlg = BatchWindow(self, self.batch_processor, self.license_manager)
        dlg.exec()

    def show_activation_dialog(self):
        """Start local browser-based authentication flow."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Activating DotScramble Pro")
        dialog.setFixedSize(400, 220)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("Waiting for authentication...")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("Please complete the activation in your browser.\nThis window will close automatically.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)

        def fallback_to_manual():
            if hasattr(self, 'auth_manager') and self.auth_manager:
                self.auth_manager.stop()
            dialog.reject()
            self._show_manual_activation_dialog()

        manual_btn = QPushButton("Enter Key Manually")
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
        self.status_label.setText("Activating...")
        QApplication.processEvents()

        success, message = self.license_manager.verify_and_activate(key)
        if success:
            QMessageBox.information(self, "Success", message)
            self.update_window_title()
            self.create_menu_bar()
            self.refresh_exif_and_tier_badge()
            self.status_label.setText("DotScramble Pro Activated!")
        else:
            QMessageBox.critical(self, "Activation Failed", message)
            self.status_label.setText("Activation failed.")

    def _show_manual_activation_dialog(self):
        key, ok = QInputDialog.getText(
            self,
            "Activate Pro",
            "Enter your DotSuite API Key to unlock DotScramble Pro:"
        )
        if ok and key:
            key = key.strip()
            self.status_label.setText("Activating...")
            QApplication.processEvents()

            success, message = self.license_manager.verify_and_activate(key)
            if success:
                QMessageBox.information(self, "Success", message)
                self.update_window_title()
                self.create_menu_bar()
                self.refresh_exif_and_tier_badge()
                self.status_label.setText("DotScramble Pro Activated!")
            else:
                QMessageBox.critical(self, "Activation Failed", message)
                self.status_label.setText("Activation failed.")

    def refresh_exif_and_tier_badge(self):
        self.update_tier_badge_ui()
        self.update_exif_section_ui()
        self.update_detection_section_ui()
        self.update_effect_section_ui()

    def show_donate(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Support the Developer")
        dialog.setFixedSize(400, 320)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("Support the Developer")
        title.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("Thank you for considering supporting this project!\nChoose your preferred donation platform:")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_paypal = QPushButton("💳 PayPal")
        btn_paypal.setObjectName("btn_paypal")
        btn_paypal.clicked.connect(lambda: self.open_url("https://paypal.me/freerave1"))
        layout.addWidget(btn_paypal)

        btn_coffee = QPushButton("☕ Buy Me a Coffee")
        btn_coffee.setObjectName("btn_coffee")
        btn_coffee.clicked.connect(lambda: self.open_url("https://buymeacoffee.com/freerave"))
        layout.addWidget(btn_coffee)

        btn_kofi = QPushButton("🎨 Ko-fi")
        btn_kofi.setObjectName("btn_kofi")
        btn_kofi.clicked.connect(lambda: self.open_url("https://ko-fi.com/freerave"))
        layout.addWidget(btn_kofi)

        btn_github = QPushButton("⭐ GitHub Sponsors")
        btn_github.setObjectName("btn_github")
        btn_github.clicked.connect(lambda: self.open_url("https://github.com/sponsors/kareem2099"))
        layout.addWidget(btn_github)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)

        dialog.exec()

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception:
            QMessageBox.critical(self, "Error", f"Could not open browser. Please visit:\n{url}")

    def show_about(self):
        QMessageBox.information(self, "About",
            f"DotScramble\nVersion {APP_VERSION}\n\n"
            "Privacy Protection for the Digital Age\n\n"
            "Support the developer:\n"
            "• PayPal: https://paypal.me/freerave1\n"
            "• Buy Me a Coffee: https://buymeacoffee.com/freerave\n"
            "• Ko-fi: https://ko-fi.com/freerave\n\n"
            "Made with ❤️ by FreeRave")

    def show_shortcuts(self):
        shortcuts_text = "\n".join([f"{key}: {value}" for key, value in SHORTCUTS.items()])
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def check_for_updates(self):
        self.auto_updater.check_for_updates(silent=False)

    def open_exports_folder(self):
        try:
            webbrowser.open(str(DIRS['exports']))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open exports folder: {e}")

    def open_app_data_folder(self):
        try:
            webbrowser.open(str(SYSTEM_DIR))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open app data folder: {e}")

    def on_update_ready(self):
        self.update_btn.setVisible(True)
        QMessageBox.information(self, "Update Ready",
            "A new update has been downloaded in the background.\n"
            "You can restart anytime using the button in the status bar.")

    def apply_update(self):
        if QMessageBox.question(self, "Restart Application",
                                "Application will close to apply the update. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.auto_updater.apply_pending_update()

    def change_theme(self, theme_key):
        self.theme_manager.apply_theme(theme_key, self)

    def on_theme_changed(self, colors):
        self.colors = colors.copy()
        # Repaint canvas with new theme colors
        self.canvas.update()

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

            # Restore splitter state
            splitter_bytes = self.db_manager.get_setting('splitter_state')
            if splitter_bytes:
                from PySide6.QtCore import QByteArray
                self.splitter.restoreState(QByteArray.fromHex(splitter_bytes.encode()))
        except Exception as e:
            logger.warning(f"Could not restore window state: {e}")

    def restore_user_settings(self):
        try:
            last_language = self.db_manager.get_last_used_language()
            self.language_var.set(last_language)

            loc_mgr = get_locale_manager()
            if loc_mgr.set_language(last_language):
                self.apply_rtl_layout(last_language)
                self.update_ui_text()

            last_theme = self.db_manager.get_last_used_theme()
            self.theme_manager.apply_theme(last_theme, self)

            effect_settings = self.db_manager.get_last_effect_settings()
            self.effect_type.set(effect_settings.get('effect_type', 'blur'))
            self.detection_mode.set(effect_settings.get('detection_mode', 'face'))
            self.blur_strength.set(effect_settings.get('blur_strength', 51))
            self.pixel_size.set(effect_settings.get('pixel_size', 15))
            self.opacity.set(effect_settings.get('opacity', 100))

            real_time = self.db_manager.get_real_time_preview_enabled()
            self.real_time_preview.set(real_time)

            self.update_parameter_visibility()
            logger.info("User settings restored from database")
        except Exception as e:
            logger.warning(f"Could not restore user settings: {e}")

    def on_effect_change(self):
        effect = self.effect_type.get()
        if effect == "ai_evasion":
            self.detection_mode.set("face")

        self.update_parameter_visibility()
        self.save_current_effect_settings()
        if self.real_time_preview.get():
            self.process_image()

    def on_detection_change(self):
        mode = self.detection_mode.get()
        effect = self.effect_type.get()
        if effect == "ai_evasion" and mode != "face":
            self.detection_mode.set("face")
            return

        pro_only_modes = ['target_text', 'text', 'body', 'license_plate']

        if mode in pro_only_modes and not self.license_manager.is_max_activated:
            mode_display = mode.replace('_', ' ').title()
            QMessageBox.information(
                self,
                "Pro Feature",
                f"The '{mode_display}' detection mode is a Pro feature.\n\n"
                f"Upgrade to DotScramble Pro for advanced AI models."
            )
            self.detection_mode.set("face")
            mode = "face"

        if mode in ["face", "eye"] and self.license_manager.is_max_activated:
            from src.models.detection_engine import is_model_downloaded
            if not is_model_downloaded():
                self.prompt_download_ai_model()

        self.update_parameter_visibility()
        self.save_current_effect_settings()
        if self.real_time_preview.get() and self.original_image is not None:
            self.process_image()

    def prompt_download_ai_model(self):
        if QMessageBox.question(self, "AI Model Required",
                                 "This PRO feature requires downloading an AI model file (~8MB).\n\n"
                                 "Would you like to download it now?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        dl_win = QDialog(self)
        dl_win.setWindowTitle("Downloading AI Model")
        dl_win.setFixedSize(300, 120)

        layout = QVBoxLayout(dl_win)
        label = QLabel("Downloading face_landmarker.task...")
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
                    QMessageBox.information(self, "Success", "AI Model downloaded successfully! PRO features are now active.")
                    if self.real_time_preview.get() and self.original_image is not None:
                        self.process_image()
                else:
                    QMessageBox.critical(self, "Download Failed", "Failed to download the AI model. Please check your internet connection.")
            QTimer.singleShot(0, on_finish)

        threading.Thread(target=download_thread, daemon=True).start()
        dl_win.exec()

    def on_parameter_change(self):
        self.save_current_effect_settings()
        if self.real_time_preview.get() and self.original_image is not None:
            self.process_image()

    def save_current_effect_settings(self):
        settings = {
            'effect_type': self.effect_type.get(),
            'detection_mode': self.detection_mode.get(),
            'blur_strength': self.blur_strength.get(),
            'pixel_size': self.pixel_size.get(),
            'opacity': self.opacity.get()
        }
        try:
            self.db_manager.save_last_effect_settings(settings)
        except Exception as e:
            logger.warning(f"Could not save effect settings: {e}")

    def toggle_preview(self):
        enabled = self.real_time_preview.get()
        try:
            self.db_manager.save_real_time_preview_enabled(enabled)
        except Exception as e:
            logger.warning(f"Could not save preview preference: {e}")

        if enabled:
            self.status_label.setText("Real-time preview enabled")
            if self.original_image is not None:
                self.process_image()
        else:
            self.status_label.setText("Real-time preview disabled")

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_state_restored'):
            self._state_restored = True
            self.restore_window_state()
            self.restore_user_settings()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            is_maximized = self.isMaximized()
            if not hasattr(self, '_last_maximized_state'):
                self._last_maximized_state = False
            if is_maximized != self._last_maximized_state:
                self._last_maximized_state = is_maximized
                QTimer.singleShot(150, self.on_canvas_resize)
        super().changeEvent(event)

    def closeEvent(self, event):
        self.on_close()
        event.accept()

    def on_close(self):
        try:
            is_maximized = self.isMaximized()
            if is_maximized:
                self.db_manager.save_setting('window_state', {'maximized': True}, 'window')
            else:
                geom = self.geometry()
                self.db_manager.save_window_state(geom.width(), geom.height(), geom.x(), geom.y(), False)

            # Save splitter state
            self.db_manager.save_setting(
                'splitter_state',
                self.splitter.saveState().toHex().data().decode(),
                'window'
            )
            logger.info("Application state saved before closing")
        except Exception as e:
            logger.warning(f"Error saving application state: {e}")

        try:
            self.db_manager.close()
        except Exception:
            pass

    @property
    def is_rtl(self):
        if hasattr(self, 'rtl_manager') and self.rtl_manager:
            return self.rtl_manager.is_rtl
        return False

    def clear_recent_history(self):
        if QMessageBox.question(self, "Clear History", "Are you sure you want to clear recent files history?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.db_manager.clear_recent_files()
            self.create_menu_bar()

    def apply_rtl_layout(self, language_code):
        loc_mgr = get_locale_manager()
        if loc_mgr.set_language(language_code):
            self.rtl_manager.set_rtl_state(loc_mgr.is_rtl())

    def update_input_field_direction(self):
        if hasattr(self, 'word_entry') and self.word_entry:
            if self.is_rtl:
                self.word_entry.setAlignment(Qt.AlignmentFlag.AlignRight)
            else:
                self.word_entry.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def update_ui_text(self):
        loc_mgr = get_locale_manager()
        _ = loc_mgr.get

        self.update_window_title()
        self.update_tier_badge_ui()

        if hasattr(self, 'status_label') and self.status_label:
            current = self.status_label.text()
            if "Ready" in current or "جاهز" in current:
                self.status_label.setText(_("ui.status.ready"))

        # Update variable values
        for key, var in self.ui_strings.items():
            var.set(_(key))

        for i, key in enumerate(self.effect_keys):
            self.effect_strings[i].set(_(key))

        for i, key in enumerate(self.detection_keys):
            self.detection_strings[i].set(_(key))

        # Update labels & check/radio buttons
        if hasattr(self, 'title_label') and self.title_label:
            self.title_label.setText(self.ui_strings["ui.header.title"].get())

        if hasattr(self, 'preview_check') and self.preview_check:
            self.preview_check.setText(self.ui_strings["ui.header.preview"].get())

        if hasattr(self, 'controls_title_label') and self.controls_title_label:
            self.controls_title_label.setText(self.ui_strings["ui.controls.title"].get())

        if hasattr(self, 'load_btn') and self.load_btn:
            self.load_btn.setText(self.ui_strings["ui.controls.load_image"].get())

        if hasattr(self, 'effect_section_label') and self.effect_section_label:
            self.effect_section_label.setText(self.ui_strings["ui.controls.effect_type"].get())

        if hasattr(self, 'detection_section_label') and self.detection_section_label:
            self.detection_section_label.setText(self.ui_strings["ui.controls.detection_mode"].get())

        if hasattr(self, 'target_text_label') and self.target_text_label:
            self.target_text_label.setText(self.ui_strings["ui.controls.target_text"].get())
        if hasattr(self, 'target_text_rb') and self.target_text_rb:
            self.target_text_rb.setText(self.ui_strings["ui.controls.target_text"].get())

        if hasattr(self, 'process_btn') and self.process_btn:
            self.process_btn.setText(self.ui_strings["ui.controls.apply_effect"].get())

        if hasattr(self, 'undo_btn') and self.undo_btn:
            self.undo_btn.setText(self.ui_strings["ui.controls.undo"].get())

        if hasattr(self, 'redo_btn') and self.redo_btn:
            self.redo_btn.setText(self.ui_strings["ui.controls.redo"].get())

        if hasattr(self, 'clear_btn') and self.clear_btn:
            self.clear_btn.setText(self.ui_strings["ui.controls.clear_selections"].get())

        if hasattr(self, 'save_btn') and self.save_btn:
            self.save_btn.setText(self.ui_strings["ui.controls.save_result"].get())

        if hasattr(self, 'batch_btn') and self.batch_btn:
            self.batch_btn.setText(self.ui_strings["ui.controls.batch_process"].get())

        if hasattr(self, 'tip_label') and self.tip_label:
            self.tip_label.setText(self.ui_strings["ui.controls.tip"].get())

        # Radios
        if hasattr(self, 'effect_radios'):
            for i, rb in enumerate(self.effect_radios):
                rb.setText(self.effect_strings[i].get())

        if hasattr(self, 'detection_radios'):
            for i, rb in enumerate(self.detection_radios):
                rb.setText(self.detection_strings[i].get())

        # Parameters
        if hasattr(self, 'blur_param_label') and self.blur_param_label:
            self.blur_param_label.setText(self.ui_strings["ui.controls.blur_strength"].get())
        if hasattr(self, 'pixel_param_label') and self.pixel_param_label:
            self.pixel_param_label.setText(self.ui_strings["ui.controls.pixel_size"].get())
        if hasattr(self, 'opacity_param_label') and self.opacity_param_label:
            self.opacity_param_label.setText(self.ui_strings["ui.controls.opacity"].get())

        # Toolbar
        if hasattr(self, 'toolbar_load_btn') and self.toolbar_load_btn:
            self.toolbar_load_btn.setText("📂 " + _("ui.buttons.load").replace("📁 ", ""))
        if hasattr(self, 'toolbar_process_btn') and self.toolbar_process_btn:
            self.toolbar_process_btn.setText("🌫️ " + _("ui.buttons.apply").replace("✨ ", ""))
        if hasattr(self, 'toolbar_save_btn') and self.toolbar_save_btn:
            self.toolbar_save_btn.setText("💾 " + self.ui_strings["ui.controls.save_result"].get().replace("💾 ", ""))
        if hasattr(self, 'toolbar_clear_btn') and self.toolbar_clear_btn:
            self.toolbar_clear_btn.setText("🧹 " + _("ui.buttons.reset").replace("🗑️ ", ""))
        if hasattr(self, 'toolbar_undo_btn') and self.toolbar_undo_btn:
            self.toolbar_undo_btn.setText("↩️ " + self.ui_strings["ui.controls.undo"].get().replace("↶ ", "").replace("↩️ ", ""))
        if hasattr(self, 'toolbar_redo_btn') and self.toolbar_redo_btn:
            self.toolbar_redo_btn.setText("↪️ " + self.ui_strings["ui.controls.redo"].get().replace("↷ ", "").replace("↪️ ", ""))

        self.update_input_field_direction()
        self.create_menu_bar()

    def change_language(self, language_code):
        loc_mgr = get_locale_manager()
        if loc_mgr.set_language(language_code):
            self.db_manager.save_last_used_language(language_code)
            self.apply_rtl_layout(language_code)
            self.update_ui_text()

            current_theme = self.theme_manager.get_current_theme_key()
            self.theme_manager.apply_theme(current_theme, self)

    def on_canvas_resize(self):
        self._resize_timer.start(60)  # 60ms debounce

    def _do_canvas_resize(self):
        if self.processed_image is not None:
            self.display_image(self.processed_image)
        elif self.original_image is not None:
            self.display_image(self.original_image)
        else:
            self.canvas.update()

    def handle_dropped_file(self, file_path):
        try:
            SUPPORTED_EXTS = {
                ".jpg", ".jpeg", ".png", ".bmp",
                ".gif", ".tiff", ".tif", ".webp"
            }
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                QMessageBox.warning(
                    self,
                    "Unsupported File",
                    f"The dropped file type '{ext or '(none)'}' is not supported.\n\n"
                    "Supported formats: JPG, PNG, BMP, TIFF, WebP, GIF"
                )
                return
            self.load_image_from_path(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Drop Error", f"Could not load dropped file:\n{str(e)}")

    def _update_detection_mode_radios(self, value):
        if hasattr(self, 'detection_radios'):
            if value == "target_text":
                self.target_text_rb.setChecked(True)
            else:
                self.target_text_rb.setChecked(False)

            for rb, (mode_val, idx) in zip(self.detection_radios, self.detection_modes_list):
                if mode_val == value:
                    rb.setChecked(True)
                else:
                    rb.setChecked(False)

    def _update_effect_type_radios(self, value):
        if hasattr(self, 'effect_radios'):
            effect_values = ["blur", "pixelation", "black_bar", "gradient", "mosaic", "glass", "oil_paint", "ai_evasion"]
            for rb, val in zip(self.effect_radios, effect_values):
                if val == value:
                    rb.setChecked(True)
                else:
                    rb.setChecked(False)
            self.update_detection_section_ui()

    def _update_spoof_profile_radios(self, value):
        if hasattr(self, 'profile_radios'):
            for val, rb in self.profile_radios:
                if val == value:
                    rb.setChecked(True)
                else:
                    rb.setChecked(False)