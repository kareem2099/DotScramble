"""
Custom Animated Image Picker for DotScramble
Animated, heavy-duty file browser
Cross-platform: Linux (XDG), Windows, macOS

Styling lives in assets/themes/theme_template.qss ("Image picker" section);
custom-painted tiles read their colors from qproperty-* values set there.
"""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame,
    QSizePolicy, QApplication
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QObject, Signal, QRunnable, QThreadPool, Property, QPoint, QEvent
)
from PySide6.QtGui import (
    QPixmap, QImage, QColor, QPainter, QPen, QBrush,
    QFont, QPainterPath, QCursor, QFontMetrics
)

from src.views.icons import IconProvider, bind_icon
from src.views.widgets import caption, color_property, repolish

EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp'}


# ── Cross-platform bookmarks ─────────────────────────────────────────────────
def _read_xdg_user_dirs() -> dict:
    """Parse ~/.config/user-dirs.dirs to get real localized folder paths."""
    result = {}
    config = Path.home() / '.config' / 'user-dirs.dirs'
    if not config.exists():
        return result
    try:
        with open(config) as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.replace('XDG_', '').replace('_DIR', '')
                val = val.strip().strip('"').replace('$HOME', str(Path.home()))
                if val:
                    result[key] = val
    except Exception:
        pass
    return result


def get_bookmarks() -> list[tuple[str, str, str]]:
    """Return (icon name, label, path) bookmarks appropriate for the current OS."""
    from src.managers.localization_manager import get_locale_manager
    _ = get_locale_manager().get

    home  = Path.home()
    marks = [('home', _('image_picker.bookmarks.home'), str(home))]

    if sys.platform == 'win32':
        candidates = [
            ('full', _('image_picker.bookmarks.pictures'),  os.environ.get('USERPROFILE', str(home)) + '\\Pictures'),
            ('save', _('image_picker.bookmarks.downloads'), str(home / 'Downloads')),
            ('monitor', _('image_picker.bookmarks.desktop'),   str(home / 'Desktop')),
            ('file', _('image_picker.bookmarks.documents'), os.environ.get('DOCUMENTS', str(home / 'Documents'))),
        ]
        for icon, label, path in candidates:
            if os.path.exists(path):
                marks.append((icon, label, path))
        # Add available drives
        import string
        for letter in string.ascii_uppercase:
            drive = f'{letter}:\\'
            if os.path.exists(drive):
                marks.append(('drive', f'{letter}:', drive))

    elif sys.platform == 'darwin':
        candidates = [
            ('full', _('image_picker.bookmarks.pictures'),  home / 'Pictures'),
            ('save', _('image_picker.bookmarks.downloads'), home / 'Downloads'),
            ('monitor', _('image_picker.bookmarks.desktop'),   home / 'Desktop'),
            ('file', _('image_picker.bookmarks.documents'), home / 'Documents'),
            ('music', _('image_picker.bookmarks.music'),     home / 'Music'),
            ('drive', _('image_picker.bookmarks.volumes'),   Path('/Volumes')),
        ]
        for icon, label, path in candidates:
            if Path(path).exists():
                marks.append((icon, label, str(path)))

    else:
        # Linux — XDG first, English fallback
        xdg = _read_xdg_user_dirs()
        candidates = [
            ('full', _('image_picker.bookmarks.pictures'),  xdg.get('PICTURES',  str(home / 'Pictures'))),
            ('save', _('image_picker.bookmarks.downloads'), xdg.get('DOWNLOAD',  str(home / 'Downloads'))),
            ('monitor', _('image_picker.bookmarks.desktop'),   xdg.get('DESKTOP',   str(home / 'Desktop'))),
            ('file', _('image_picker.bookmarks.documents'), xdg.get('DOCUMENTS', str(home / 'Documents'))),
            ('music', _('image_picker.bookmarks.music'),     xdg.get('MUSIC',     str(home / 'Music'))),
            ('drive', _('image_picker.bookmarks.root'),      '/'),
        ]
        for icon, label, path in candidates:
            if os.path.exists(path):
                marks.append((icon, label, path))

    return marks


# ── Thumbnail loader ─────────────────────────────────────────────────────────
class ThumbSignals(QObject):
    # Bug #1 fix: carry the load epoch so stale callbacks can be discarded
    done = Signal(str, QPixmap, int)

class ThumbLoader(QRunnable):
    SIZE = 140
    def __init__(self, path: str, signals: ThumbSignals, epoch: int):
        super().__init__()
        self.path    = path
        self.signals = signals
        self.epoch   = epoch
        self.setAutoDelete(True)

    def run(self):
        try:
            from PIL import Image
            img = Image.open(self.path)
            img.thumbnail((self.SIZE, self.SIZE), Image.LANCZOS)
            img = img.convert('RGBA')
            data = img.tobytes('raw', 'RGBA')
            # Bug #6 fix: pass explicit bytesPerLine (img.width * 4) to avoid
            # row-padding misalignment on certain PIL builds
            qimg = QImage(data, img.width, img.height,
                          img.width * 4,
                          QImage.Format.Format_RGBA8888)
            self.signals.done.emit(self.path, QPixmap.fromImage(qimg), self.epoch)
        except Exception:
            pass


# ── Preview loader (async — Bug #2 fix) ──────────────────────────────────────
class PreviewSignals(QObject):
    done = Signal(str, QPixmap, int, int, int)   # path, pixmap, w, h, kb

class PreviewLoader(QRunnable):
    """Loads the full preview image on a worker thread to avoid UI-thread freeze."""
    TARGET_W = 220
    TARGET_H = 180

    def __init__(self, path: str, signals: PreviewSignals):
        super().__init__()
        self.path    = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            kb  = os.path.getsize(self.path) // 1024
            img = QImage(self.path)
            if img.isNull():
                return
            px = QPixmap.fromImage(img.scaled(
                self.TARGET_W, self.TARGET_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.signals.done.emit(self.path, px, img.width(), img.height(), kb)
        except Exception:
            pass


# ── File tile ────────────────────────────────────────────────────────────────
class FileTile(QWidget):
    clicked   = Signal(str)
    activated = Signal(str)

    TILE  = 160
    THUMB = 120

    # Set from the stylesheet: QWidget#PickerTile { qproperty-…: … }
    tileColor     = color_property("_c_tile")
    selectedColor = color_property("_c_selected")
    accentColor   = color_property("_c_accent")
    borderColor   = color_property("_c_border")
    slotColor     = color_property("_c_slot")
    textColor     = color_property("_c_text")

    def __init__(self, path: str, is_dir: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("PickerTile")
        self._c_tile     = QColor("#1c2333")
        self._c_selected = QColor("#0c1e2e")
        self._c_accent   = QColor("#00bcd4")
        self._c_border   = QColor("#30363d")
        self._c_slot     = QColor("#161b22")
        self._c_text     = QColor("#e6edf3")
        self.path          = path
        self.is_dir        = is_dir
        self.thumb         = None
        self._selected     = False
        self._glow         = 0.0
        self._tile_opacity = 0.0   # animated via Property — no QGraphicsOpacityEffect
        self._anim         = None

        self.setFixedSize(self.TILE, self.TILE + 28)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

    # ── Properties ────────────────────────────────────────────────────────
    def _get_opacity(self): return self._tile_opacity
    def _set_opacity(self, v):
        self._tile_opacity = max(0.0, min(1.0, v))
        self.update()
    tile_opacity = Property(float, _get_opacity, _set_opacity)

    def _get_glow(self): return self._glow
    def _set_glow(self, v):
        self._glow = v
        self.update()
    glow = Property(float, _get_glow, _set_glow)

    # ── State ─────────────────────────────────────────────────────────────
    def set_selected(self, v: bool):
        self._selected = v
        self.update()

    def set_thumb(self, px: QPixmap):
        self.thumb = px
        self.update()

    # ── Mouse ─────────────────────────────────────────────────────────────
    def enterEvent(self, _):
        self._animate_glow(1.0)

    def leaveEvent(self, _):
        if not self._selected:
            self._animate_glow(0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.path)

    def _animate_glow(self, target: float):
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b'glow', self)
        self._anim.setDuration(180)
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    # ── Paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # tile_opacity in painter — avoids QGraphicsOpacityEffect/Wayland conflict
        p.setOpacity(self._tile_opacity)

        W, H = self.width(), self.TILE
        r    = 10

        bg   = self._c_selected if self._selected else self._c_tile
        path = QPainterPath()
        path.addRoundedRect(2, 2, W - 4, H - 4, r, r)
        p.fillPath(path, QBrush(bg))

        # Border / glow
        if self._glow > 0.01 or self._selected:
            alpha = max(self._glow, 1.0 if self._selected else 0.0)
            col   = QColor(self._c_accent)
            col.setAlphaF(alpha * 0.85)
            p.setPen(QPen(col, 2.0 if self._selected else 1.5 * self._glow))
            p.drawPath(path)
            if self._glow > 0.3:
                gc = QColor(self._c_accent)
                gc.setAlphaF(self._glow * 0.12)
                p.setPen(QPen(gc, 6))
                p.drawPath(path)
        else:
            p.setPen(QPen(self._c_border, 1))
            p.drawPath(path)

        # Thumbnail
        ty = 14
        ts = self.THUMB
        if self.thumb:
            tx   = (W - ts) // 2
            clip = QPainterPath()
            clip.addRoundedRect(tx, ty, ts, ts, 6, 6)
            p.setClipPath(clip)
            tw = self.thumb.width()
            th = self.thumb.height()
            p.drawPixmap(tx + (ts - tw) // 2, ty + (ts - th) // 2, self.thumb)
            p.setClipping(False)
        else:
            ir = QPainterPath()
            ir.addRoundedRect((W - ts) // 2, ty, ts, ts, 6, 6)
            p.fillPath(ir, QBrush(self._c_slot))
            icon = IconProvider.instance().pixmap(
                "open" if self.is_dir else "full", 40,
                "accent_cyan" if self.is_dir else "text_secondary")
            p.drawPixmap((W - 40) // 2, ty + (ts - 40) // 2, icon)

        # Filename
        name = os.path.basename(self.path) or self.path
        p.setPen(QPen(self._c_text))
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        text = QFontMetrics(p.font()).elidedText(
            name, Qt.TextElideMode.ElideRight, W - 8
        )
        p.drawText(0, H + 2, W, 22, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# ── Sidebar item ─────────────────────────────────────────────────────────────
class SidebarItem(QPushButton):
    """A quick-access place. Look (hover / active) comes from QPushButton#PickerPlace."""
    selected = Signal(str)

    def __init__(self, icon: str, label: str, path: str, parent=None):
        super().__init__(label, parent)
        self.path = path
        self.setObjectName("PickerPlace")
        self.setFixedHeight(36)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setProperty("active", "false")
        bind_icon(self, icon, 16, "text_secondary")
        self.clicked.connect(lambda: self.selected.emit(self.path))

    def set_active(self, v: bool):
        self.setProperty("active", "true" if v else "false")
        repolish(self)


# ── Preview panel ────────────────────────────────────────────────────────────
class PreviewPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(0)
        self.setObjectName("PickerPreview")
        # The panel's border sits on the side facing the grid
        self.setProperty("rtl", "true" if self.isRightToLeft() else "false")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(10)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setObjectName("PickerPreviewThumb")
        self.thumb_lbl.setFixedSize(220, 180)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.thumb_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.name_lbl = QLabel()
        self.name_lbl.setProperty("role", "field-label")
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.name_lbl)

        self.info_lbl = caption()
        self.info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.info_lbl)

        lay.addStretch()
        self._anim = None

    def show_file(self, path: str, pixmap: QPixmap, w: int, h: int, kb: int):
        """Called from the main thread after PreviewLoader finishes — never blocks."""
        self.name_lbl.setText(os.path.basename(path))
        self.info_lbl.setText(f"{w} × {h}\n{kb} KB")
        self.thumb_lbl.setPixmap(pixmap)
        self._slide(True)

    def show_loading(self, path: str):
        """Show name + spinner immediately while the async loader is working."""
        from src.managers.localization_manager import get_locale_manager
        self.name_lbl.setText(os.path.basename(path))
        self.info_lbl.setText(get_locale_manager().get("image_picker.loading"))
        self.thumb_lbl.setPixmap(QPixmap())
        self._slide(True)

    def hide_preview(self):
        self._slide(False)

    def _slide(self, show: bool):
        target = 248 if show else 0
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b'maximumWidth', self)
        self._anim.setDuration(260)
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if show else QEasingCurve.Type.InCubic
        )
        self._anim.start()


# ── Main dialog ──────────────────────────────────────────────────────────────
class ImagePicker(QDialog):
    GRID_MARGIN  = 16
    GRID_SPACING = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        
        from src.managers.localization_manager import get_locale_manager
        self.locale = get_locale_manager()
        
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        if self.locale.is_rtl():
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            
        self.setObjectName("ImagePicker")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1020, 680)

        self._cwd          = str(Path.home())
        self._selected     = ''
        self._tiles        = []
        self._drag_pos     = None

        # Bug #1 fix: epoch counter — incremented on every _load_grid call so
        # callbacks from a previous folder are silently discarded.
        self._load_epoch   = 0

        # Bug #5 fix: private pool instead of globalInstance() so we can
        # call clear() on reject without affecting the rest of the app.
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(4)

        # Bug #6 fix: separate pool / signals for the preview panel loader
        self._preview_pool    = QThreadPool()
        self._preview_pool.setMaxThreadCount(1)
        self._preview_signals = PreviewSignals()
        self._preview_signals.done.connect(self._on_preview_done)
        self._preview_path    = ''   # track which file the preview is for

        # Bug #6 fix: list of pending staggered-fade QTimers so we can
        # cancel them when navigating to a new folder.
        self._pending_fades: list[QTimer] = []

        # Debounce timer — fires 200ms after the user stops typing
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_filter)

        # Re-flow the grid when the visible width changes (window resize, preview slide)
        self._cols = 0
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self._reflow_if_needed)

        self._build_ui()

        # Fade-in at compositor level — no painter conflict on Wayland
        # Bug #7 fix: use the already-imported `os` instead of `import os as _os`
        _is_wayland = (
            os.environ.get('WAYLAND_DISPLAY') is not None or
            QApplication.platformName() == 'wayland'
        )

        if not _is_wayland:
            self.setWindowOpacity(0.0)
            self._open_anim = QPropertyAnimation(self, b'windowOpacity', self)
            self._open_anim.setDuration(220)
            self._open_anim.setStartValue(0.0)
            self._open_anim.setEndValue(1.0)
            self._open_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._open_anim.start()

        self._navigate(self._cwd)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame(self)
        self.container.setObjectName("PickerRoot")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("PickerTitleBar")
        title_bar.setFixedHeight(52)
        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release

        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(18, 0, 12, 0)
        tb.setSpacing(12)

        icon_l = QLabel()
        bind_icon(icon_l, "camera", 20, "accent_cyan")
        tb.addWidget(icon_l)

        ttl = QLabel(self.locale.get("image_picker.title"))
        ttl.setObjectName("PickerTitle")
        tb.addWidget(ttl)
        tb.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.locale.get("image_picker.search_placeholder"))
        self.search.setFixedWidth(220)
        self.search.setObjectName("PickerSearch")
        self.search.textChanged.connect(self._on_search_changed)
        tb.addWidget(self.search)

        cb = QPushButton()
        cb.setFixedSize(32, 32)
        cb.setObjectName("PickerClose")
        bind_icon(cb, "close", 16, "text_secondary")
        cb.clicked.connect(self.reject)
        tb.addWidget(cb)

        root.addWidget(title_bar)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Body
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("PickerSidebar")
        sidebar.setFixedWidth(190)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(8, 12, 8, 12)
        sb.setSpacing(2)

        ql = caption(self.locale.get("image_picker.quick_access"), role="heading")
        sb.addWidget(ql)
        sb.addSpacing(6)

        self._sb_items = []
        for icon, label, path in get_bookmarks():   # ← cross-platform
            item = SidebarItem(icon, label, path)
            item.selected.connect(self._navigate)
            sb.addWidget(item)
            self._sb_items.append(item)

        sb.addStretch()
        body.addWidget(sidebar)

        divider = QFrame()
        divider.setObjectName("PickerDivider")
        divider.setFixedWidth(1)
        body.addWidget(divider)

        # Center
        center = QWidget()
        center.setObjectName("PickerCenter")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.bread_bar = QFrame()
        self.bread_bar.setObjectName("PickerBreadcrumbs")
        self.bread_bar.setFixedHeight(38)
        bb = QHBoxLayout(self.bread_bar)
        bb.setContentsMargins(14, 0, 14, 0)
        bb.setSpacing(4)
        self.bread_layout = bb
        cl.addWidget(self.bread_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)

        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("PickerGrid")
        self.scroll.setWidget(self.grid_widget)
        cl.addWidget(self.scroll, 1)

        body.addWidget(center, 1)

        self.preview = PreviewPanel()
        body.addWidget(self.preview)

        root.addLayout(body, 1)

        # Bottom bar
        bottom = QFrame()
        bottom.setObjectName("PickerFooter")
        bottom.setFixedHeight(56)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(10)

        self.path_lbl = QLabel()
        self.path_lbl.setObjectName("PickerPath")
        self.path_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bl.addWidget(self.path_lbl)

        cancel = QPushButton(self.locale.get("image_picker.cancel"))
        cancel.setProperty("variant", "ghost")
        cancel.setMinimumSize(90, 34)
        cancel.clicked.connect(self.reject)
        bl.addWidget(cancel)

        self.open_btn = QPushButton(self.locale.get("image_picker.open"))
        self.open_btn.setProperty("variant", "primary")
        self.open_btn.setMinimumSize(100, 34)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._confirm)
        bl.addWidget(self.open_btn)

        root.addWidget(bottom)

    # ── Navigation ───────────────────────────────────────────────────────────
    def _navigate(self, path: str):
        if not os.path.isdir(path):
            return
        self._cwd      = path
        self._selected = ''
        self.open_btn.setEnabled(False)
        self.path_lbl.setText(path)
        self.preview.hide_preview()

        # Bug #3 fix: clear search text silently so the filter isn't carried
        # over to the new folder — blockSignals prevents a debounce trigger.
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._search_timer.stop()

        self._update_sidebar_active()
        self._update_breadcrumb()
        self._load_grid()

    def _update_sidebar_active(self):
        for item in self._sb_items:
            item.set_active(item.path == self._cwd)

    def _update_breadcrumb(self):
        while self.bread_layout.count():
            w = self.bread_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        parts = []
        p = Path(self._cwd)
        parts.append(p)
        while p.parent != p:
            p = p.parent
            parts.insert(0, p)

        for i, part in enumerate(parts[-4:]):
            if i > 0:
                self.bread_layout.addWidget(caption("‹" if self.isRightToLeft() else "›"))

            is_last = (i == min(3, len(parts) - 1))
            name    = part.name or str(part)
            btn     = QPushButton(name)
            btn.setObjectName("PickerCrumb")
            btn.setProperty("current", "true" if is_last else "false")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if not is_last:
                btn.clicked.connect(lambda _, pt=str(part): self._navigate(pt))
            self.bread_layout.addWidget(btn)

        self.bread_layout.addStretch()

    # ── Grid ─────────────────────────────────────────────────────────────────
    def _load_grid(self):
        # Bug #5 fix: cancel all pending staggered-fade timers from the
        # previous folder before building the new grid.
        for t in self._pending_fades:
            t.stop()
        self._pending_fades.clear()

        # Bug #1 fix: bump the epoch — any ThumbLoader that finishes after
        # this point will carry an old epoch and be silently dropped.
        self._load_epoch += 1
        epoch = self._load_epoch

        # Qt auto-deletes old grid_widget on setWidget() — never call deleteLater manually
        self._tiles.clear()
        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("PickerGrid")
        self.scroll.setWidget(self.grid_widget)

        try:
            entries = sorted(
                os.scandir(self._cwd),
                key=lambda e: (not e.is_dir(), e.name.lower())
            )
        except PermissionError:
            return

        dirs  = [e for e in entries if e.is_dir()  and not e.name.startswith('.')]
        files = [e for e in entries if e.is_file()
                 and os.path.splitext(e.name)[1].lower() in EXTS]
        all_e = dirs + files

        for entry in all_e:
            tile = FileTile(entry.path, entry.is_dir())
            tile.clicked.connect(self._on_tile_click)
            tile.activated.connect(self._on_tile_activate)
            self._tiles.append(tile)

        self._arrange_grid()

        # Bug #5 fix: staggered fade-in uses tracked QTimers (with self as
        # parent) instead of bare QTimer.singleShot so they can be cancelled.
        for i, tile in enumerate(self._tiles):
            tile._tile_opacity = 0.0
            def _fade(t=tile):
                a = QPropertyAnimation(t, b'tile_opacity', t)
                a.setDuration(200)
                a.setStartValue(0.0)
                a.setEndValue(1.0)
                a.setEasingCurve(QEasingCurve.Type.OutCubic)
                a.start()
                t._reveal_anim = a   # keep ref — prevents GC killing animation
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(_fade)
            timer.start(min(i * 18, 300))
            self._pending_fades.append(timer)

        # Background thumbnail loading — Bug #1 fix: pass epoch to loader
        for tile in self._tiles:
            if not tile.is_dir:
                sig    = ThumbSignals()
                sig.done.connect(self._on_thumb_done)
                loader = ThumbLoader(tile.path, sig, epoch)
                self._pool.start(loader)

    def _arrange_grid(self):
        # Detach existing tiles from layout so they aren't destroyed
        for tile in self._tiles:
            tile.setParent(None)

        if self.grid_widget.layout() is not None:
            # Delete layout by reparenting to a dummy widget
            QWidget().setLayout(self.grid_widget.layout())

        # Re-parent tiles back to grid_widget
        for tile in self._tiles:
            tile.setParent(self.grid_widget)

        q = self.search.text().lower()
        visible_tiles = []
        for tile in self._tiles:
            is_visible = not q or q in os.path.basename(tile.path).lower()
            tile.setVisible(is_visible)
            if is_visible:
                visible_tiles.append(tile)

        self._cols = self._columns_for_width()
        m = self.GRID_MARGIN
        lay = QVBoxLayout(self.grid_widget)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(0)

        if not visible_tiles:
            key = "image_picker.empty_folder" if not self._tiles else "image_picker.no_matches"
            empty = caption(self.locale.get(key))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(empty)
            return

        def _row():
            r = QHBoxLayout()
            r.setSpacing(self.GRID_SPACING)
            r.setContentsMargins(0, 0, 0, 0)
            return r

        cur, col = _row(), 0
        for tile in visible_tiles:
            cur.addWidget(tile)
            col += 1
            if col == self._cols:
                lay.addLayout(cur)
                lay.addSpacing(self.GRID_SPACING)
                cur, col = _row(), 0

        if col > 0:
            cur.addStretch()
            lay.addLayout(cur)
        lay.addStretch()

    def _on_thumb_done(self, path: str, px: QPixmap, epoch: int):
        # Bug #1 fix: discard callbacks that belong to a previous folder load
        if epoch != self._load_epoch:
            return
        for tile in self._tiles:
            if tile.path == path:
                tile.set_thumb(px)
                break

    # ── Tile interaction ──────────────────────────────────────────────────────
    def _on_tile_click(self, path: str):
        for tile in self._tiles:
            tile.set_selected(tile.path == path)
        if os.path.isfile(path):
            self._selected = path
            self.open_btn.setEnabled(True)
            self.path_lbl.setText(path)
            # Bug #2 fix: show a loading placeholder immediately, then kick
            # off PreviewLoader on a worker thread — no main-thread freeze.
            self._preview_path = path
            self.preview.show_loading(path)
            loader = PreviewLoader(path, self._preview_signals)
            self._preview_pool.start(loader)
        else:
            self._selected = ''
            self.open_btn.setEnabled(False)
            self.preview.hide_preview()

    def _on_preview_done(self, path: str, px: QPixmap, w: int, h: int, kb: int):
        """Slot called on the main thread when PreviewLoader finishes."""
        # Only apply if the user hasn't moved to a different file in the meantime
        if path == self._preview_path:
            self.preview.show_file(path, px, w, h, kb)

    def _on_tile_activate(self, path: str):
        if os.path.isdir(path):
            self._navigate(path)
        else:
            self._selected = path
            self._confirm()

    def _columns_for_width(self) -> int:
        """How many tiles fit side by side in the visible grid area."""
        width = self.scroll.viewport().width() - 2 * self.GRID_MARGIN
        return max(1, (width + self.GRID_SPACING) // (FileTile.TILE + self.GRID_SPACING))

    def _reflow_if_needed(self):
        if self._columns_for_width() != self._cols:
            self._arrange_grid()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow_timer.start(60)
        return super().eventFilter(obj, event)

    def _on_search_changed(self, _text: str):
        """Restart the debounce timer every time the user types a character."""
        self._search_timer.start(200)

    def _apply_filter(self):
        """Run once, 200 ms after the user stops typing — no per-keystroke reload."""
        self._arrange_grid()
        # Scroll back to the top so the first matching result is always visible
        self.scroll.verticalScrollBar().setValue(0)

    def _confirm(self):
        if self._selected:
            self.accept()

    # Bug #5 fix: stop all background work before the dialog closes so we
    # never emit signals into destroyed widgets.
    def reject(self):
        self._pool.clear()
        self._preview_pool.clear()
        self._search_timer.stop()
        for t in self._pending_fades:
            t.stop()
        self._pending_fades.clear()
        super().reject()

    def accept(self):
        self._pool.clear()
        self._preview_pool.clear()
        self._search_timer.stop()
        for t in self._pending_fades:
            t.stop()
        self._pending_fades.clear()
        super().accept()

    def open(self) -> str | None:
        """Show dialog; return selected path or None."""
        return self._selected if self.exec() == QDialog.DialogCode.Accepted else None

    # ── Frameless drag ────────────────────────────────────────────────────────
    def _tb_press(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _tb_release(self, _):
        self._drag_pos = None

    # ── Keyboard ─────────────────────────────────────────────────────────────
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._selected:
                self._confirm()
        elif e.key() == Qt.Key.Key_Backspace:
            parent = str(Path(self._cwd).parent)
            if parent != self._cwd:
                self._navigate(parent)
        else:
            super().keyPressEvent(e)