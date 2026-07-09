"""
Custom Animated Image Picker for DotScramble
Cyberpunk-themed, animated, heavy-duty file browser
Cross-platform: Linux (XDG), Windows, macOS
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
    QObject, Signal, QRunnable, QThreadPool, Property, QPoint, QLoggingCategory
)
QLoggingCategory.setFilterRules("qt.gui.imageio.jpeg=false")
from PySide6.QtGui import (
    QPixmap, QImage, QColor, QPainter, QPen, QBrush,
    QFont, QPainterPath, QCursor, QFontMetrics
)

# ── Palette ─────────────────────────────────────────────────────────────────
C = {
    'bg_dark':  '#0d1117',
    'bg_med':   '#161b22',
    'bg_light': '#1c2333',
    'border':   '#30363d',
    'cyan':     '#00fff5',
    'green':    '#26a69a',
    'txt':      '#e6edf3',
    'txt_dim':  '#8b949e',
    'txt_off':  '#484f58',
    'hover':    '#1f2937',
    'sel':      '#0c1e2e',
}

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
    """Return bookmarks appropriate for the current OS."""
    from src.managers.localization_manager import get_locale_manager
    _ = get_locale_manager().get

    home  = Path.home()
    marks = [('🏠', _('image_picker.bookmarks.home'), str(home))]

    if sys.platform == 'win32':
        candidates = [
            ('🖼️', _('image_picker.bookmarks.pictures'),  os.environ.get('USERPROFILE', str(home)) + '\\Pictures'),
            ('⬇️', _('image_picker.bookmarks.downloads'), str(home / 'Downloads')),
            ('🖥️', _('image_picker.bookmarks.desktop'),   str(home / 'Desktop')),
            ('📄', _('image_picker.bookmarks.documents'), os.environ.get('DOCUMENTS', str(home / 'Documents'))),
        ]
        for icon, label, path in candidates:
            if os.path.exists(path):
                marks.append((icon, label, path))
        # Add available drives
        import string
        for letter in string.ascii_uppercase:
            drive = f'{letter}:\\'
            if os.path.exists(drive):
                marks.append(('💾', f'{letter}:', drive))

    elif sys.platform == 'darwin':
        candidates = [
            ('🖼️', _('image_picker.bookmarks.pictures'),  home / 'Pictures'),
            ('⬇️', _('image_picker.bookmarks.downloads'), home / 'Downloads'),
            ('🖥️', _('image_picker.bookmarks.desktop'),   home / 'Desktop'),
            ('📄', _('image_picker.bookmarks.documents'), home / 'Documents'),
            ('🎵', _('image_picker.bookmarks.music'),     home / 'Music'),
            ('📂', _('image_picker.bookmarks.volumes'),   Path('/Volumes')),
        ]
        for icon, label, path in candidates:
            if Path(path).exists():
                marks.append((icon, label, str(path)))

    else:
        # Linux — XDG first, English fallback
        xdg = _read_xdg_user_dirs()
        candidates = [
            ('🖼️', _('image_picker.bookmarks.pictures'),  xdg.get('PICTURES',  str(home / 'Pictures'))),
            ('⬇️', _('image_picker.bookmarks.downloads'), xdg.get('DOWNLOAD',  str(home / 'Downloads'))),
            ('🖥️', _('image_picker.bookmarks.desktop'),   xdg.get('DESKTOP',   str(home / 'Desktop'))),
            ('📄', _('image_picker.bookmarks.documents'), xdg.get('DOCUMENTS', str(home / 'Documents'))),
            ('🎵', _('image_picker.bookmarks.music'),     xdg.get('MUSIC',     str(home / 'Music'))),
            ('📂', _('image_picker.bookmarks.root'),      '/'),
        ]
        for icon, label, path in candidates:
            if os.path.exists(path):
                marks.append((icon, label, path))

    return marks


# ── Thumbnail loader ─────────────────────────────────────────────────────────
class ThumbSignals(QObject):
    done = Signal(str, QPixmap)

class ThumbLoader(QRunnable):
    SIZE = 140
    def __init__(self, path: str, signals: ThumbSignals):
        super().__init__()
        self.path    = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            from PIL import Image
            img = Image.open(self.path)
            img.thumbnail((self.SIZE, self.SIZE), Image.LANCZOS)
            img = img.convert('RGBA')
            data  = img.tobytes('raw', 'RGBA')
            qimg  = QImage(data, img.width, img.height,
                           QImage.Format.Format_RGBA8888)
            # keep data alive until QImage is done
            qimg._pil_data = data
            self.signals.done.emit(self.path, QPixmap.fromImage(qimg))
        except Exception:
            pass


# ── File tile ────────────────────────────────────────────────────────────────
class FileTile(QWidget):
    clicked   = Signal(str)
    activated = Signal(str)

    TILE  = 160
    THUMB = 120

    def __init__(self, path: str, is_dir: bool, parent=None):
        super().__init__(parent)
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

        bg   = QColor(C['sel'] if self._selected else C['bg_light'])
        path = QPainterPath()
        path.addRoundedRect(2, 2, W - 4, H - 4, r, r)
        p.fillPath(path, QBrush(bg))

        # Border / glow
        if self._glow > 0.01 or self._selected:
            alpha = max(self._glow, 1.0 if self._selected else 0.0)
            col   = QColor(C['cyan'])
            col.setAlphaF(alpha * 0.85)
            p.setPen(QPen(col, 2.0 if self._selected else 1.5 * self._glow))
            p.drawPath(path)
            if self._glow > 0.3:
                gc = QColor(C['cyan'])
                gc.setAlphaF(self._glow * 0.12)
                p.setPen(QPen(gc, 6))
                p.drawPath(path)
        else:
            p.setPen(QPen(QColor(C['border']), 1))
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
            p.fillPath(ir, QBrush(QColor(C['hover'] if self.is_dir else C['bg_med'])))
            p.setPen(QPen(QColor(C['txt_dim'])))
            p.setFont(QFont("Segoe UI Emoji", 28))
            p.drawText((W - ts) // 2, ty, ts, ts,
                       Qt.AlignmentFlag.AlignCenter,
                       "📁" if self.is_dir else "🖼️")

        # Filename
        name = os.path.basename(self.path) or self.path
        p.setPen(QPen(QColor(C['txt'])))
        p.setFont(QFont("Helvetica", 8, QFont.Weight.Medium))
        text = QFontMetrics(p.font()).elidedText(
            name, Qt.TextElideMode.ElideRight, W - 8
        )
        p.drawText(0, H + 2, W, 22, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# ── Sidebar item ─────────────────────────────────────────────────────────────
class SidebarItem(QWidget):
    clicked = Signal(str)

    def __init__(self, icon: str, label: str, path: str, parent=None):
        super().__init__(parent)
        self.path    = path
        self._active = False
        self._hover  = False
        self.setFixedHeight(38)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        il = QLabel(icon)
        il.setFont(QFont("Segoe UI Emoji", 13))
        il.setFixedWidth(24)
        lay.addWidget(il)

        self.lbl = QLabel(label)
        self.lbl.setFont(QFont("Helvetica", 10))
        lay.addWidget(self.lbl)

        self._refresh()

    def set_active(self, v: bool):
        self._active = v
        self._refresh()

    def _refresh(self):
        if self._active:
            self.setStyleSheet(
                f"background:{C['sel']}; border-radius:6px;"
                f" border-left:3px solid {C['cyan']};"
            )
            self.lbl.setStyleSheet(f"color:{C['cyan']}; font-weight:bold;")
        elif self._hover:
            self.setStyleSheet(f"background:{C['hover']}; border-radius:6px;")
            self.lbl.setStyleSheet(f"color:{C['txt']};")
        else:
            self.setStyleSheet("background:transparent; border-radius:6px;")
            self.lbl.setStyleSheet(f"color:{C['txt_dim']};")

    def enterEvent(self, _):
        self._hover = True;  self._refresh()

    def leaveEvent(self, _):
        self._hover = False; self._refresh()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)


# ── Preview panel ────────────────────────────────────────────────────────────
class PreviewPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(0)
        self.setObjectName("preview_panel")
        self.setStyleSheet(
            f"#preview_panel {{ background:{C['bg_med']};"
            f" border-left:1px solid {C['border']}; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(10)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(220, 180)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet(
            f"background:{C['bg_dark']}; border-radius:8px;"
            f" border:1px solid {C['border']};"
        )
        lay.addWidget(self.thumb_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.name_lbl = QLabel()
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet(f"color:{C['txt']};")
        lay.addWidget(self.name_lbl)

        self.info_lbl = QLabel()
        self.info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_lbl.setFont(QFont("Helvetica", 8))
        self.info_lbl.setStyleSheet(f"color:{C['txt_dim']};")
        self.info_lbl.setWordWrap(True)
        lay.addWidget(self.info_lbl)

        lay.addStretch()
        self._anim = None

    def show_file(self, path: str):
        self.name_lbl.setText(os.path.basename(path))
        try:
            kb  = os.path.getsize(path) // 1024
            img = QImage(path)
            self.info_lbl.setText(f"{img.width()} × {img.height()}\n{kb} KB")
            px = QPixmap.fromImage(img.scaled(
                220, 180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.thumb_lbl.setPixmap(px)
        except Exception:
            self.thumb_lbl.setText("⚠️")
            self.info_lbl.setText("")
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
    COLS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        
        from src.managers.localization_manager import get_locale_manager
        self.locale = get_locale_manager()
        
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        if self.locale.is_rtl():
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1020, 680)

        self._cwd       = str(Path.home())
        self._selected  = ''
        self._tiles     = []
        self._pool      = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(4)
        self._drag_pos  = None

        self._build_ui()
        self._apply_styles()

        # Fade-in at compositor level — no painter conflict on Wayland
        import os as _os
        _is_wayland = (
            _os.environ.get('WAYLAND_DISPLAY') is not None or
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
        self.container.setObjectName("picker_root")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(52)
        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release

        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(18, 0, 12, 0)
        tb.setSpacing(12)

        icon_l = QLabel("📷")
        icon_l.setFont(QFont("Segoe UI Emoji", 16))
        tb.addWidget(icon_l)

        ttl = QLabel(self.locale.get("image_picker.title"))
        ttl.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color:{C['cyan']};")
        tb.addWidget(ttl)
        tb.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.locale.get("image_picker.search_placeholder"))
        self.search.setFixedWidth(220)
        self.search.setObjectName("search_bar")
        self.search.textChanged.connect(self._filter_tiles)
        tb.addWidget(self.search)

        cb = QPushButton("✕")
        cb.setFixedSize(32, 32)
        cb.setObjectName("close_btn")
        cb.clicked.connect(self.reject)
        tb.addWidget(cb)

        root.addWidget(title_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Body
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(8, 12, 8, 12)
        sb.setSpacing(2)

        ql = QLabel(self.locale.get("image_picker.quick_access"))
        ql.setFont(QFont("Helvetica", 7, QFont.Weight.Bold))
        ql.setStyleSheet(f"color:{C['txt_off']}; letter-spacing:1px;")
        sb.addWidget(ql)
        sb.addSpacing(6)

        self._sb_items = []
        for icon, label, path in get_bookmarks():   # ← cross-platform
            item = SidebarItem(icon, label, path)
            item.clicked.connect(self._navigate)
            sb.addWidget(item)
            self._sb_items.append(item)

        sb.addStretch()
        body.addWidget(sidebar)

        vl = QFrame()
        vl.setFrameShape(QFrame.Shape.VLine)
        vl.setStyleSheet(f"color:{C['border']};")
        body.addWidget(vl)

        # Center
        center = QWidget()
        center.setStyleSheet(f"background:{C['bg_dark']};")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.bread_bar = QFrame()
        self.bread_bar.setObjectName("bread_bar")
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
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background:{C['bg_dark']}; border:none; }}"
            f"QScrollBar:vertical {{ background:{C['bg_med']}; width:8px; border-radius:4px; }}"
            f"QScrollBar::handle:vertical {{ background:{C['border']}; border-radius:4px; min-height:20px; }}"
            f"QScrollBar::handle:vertical:hover {{ background:{C['cyan']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border:none; background:none; }}"
        )

        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet(f"background:{C['bg_dark']};")
        self.scroll.setWidget(self.grid_widget)
        cl.addWidget(self.scroll, 1)

        body.addWidget(center, 1)

        self.preview = PreviewPanel()
        body.addWidget(self.preview)

        root.addLayout(body, 1)

        # Bottom bar
        bottom = QFrame()
        bottom.setObjectName("bottom_bar")
        bottom.setFixedHeight(56)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(10)

        self.path_lbl = QLabel()
        self.path_lbl.setFont(QFont("Monospace", 9))
        self.path_lbl.setStyleSheet(f"color:{C['txt_dim']};")
        self.path_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bl.addWidget(self.path_lbl)

        cancel = QPushButton(self.locale.get("image_picker.cancel"))
        cancel.setObjectName("cancel_btn")
        cancel.setFixedSize(90, 34)
        cancel.clicked.connect(self.reject)
        bl.addWidget(cancel)

        self.open_btn = QPushButton(self.locale.get("image_picker.open"))
        self.open_btn.setObjectName("open_btn")
        self.open_btn.setFixedSize(100, 34)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._confirm)
        bl.addWidget(self.open_btn)

        root.addWidget(bottom)

    # ── Styles ───────────────────────────────────────────────────────────────
    def _apply_styles(self):
        self.setStyleSheet(f"""
            #picker_root  {{ background:{C['bg_med']}; border:1px solid {C['border']}; border-radius:12px; }}
            #title_bar    {{ background:{C['bg_med']}; border-top-left-radius:12px; border-top-right-radius:12px; }}
            #sidebar      {{ background:{C['bg_med']}; }}
            #bread_bar    {{ background:{C['bg_dark']}; border-bottom:1px solid {C['border']}; }}
            #bottom_bar   {{ background:{C['bg_med']}; border-top:1px solid {C['border']};
                             border-bottom-left-radius:12px; border-bottom-right-radius:12px; }}
            #search_bar   {{ background:{C['bg_dark']}; border:1px solid {C['border']};
                             border-radius:6px; padding:5px 10px; color:{C['txt']}; font-size:11px; }}
            #search_bar:focus {{ border-color:{C['cyan']}; }}
            #close_btn    {{ background:transparent; border:none; color:{C['txt_dim']};
                             font-size:13px; border-radius:6px; }}
            #close_btn:hover {{ background:#3d1f1f; color:#ff5555; }}
            #cancel_btn   {{ background:{C['bg_light']}; border:1px solid {C['border']};
                             border-radius:6px; color:{C['txt']}; font-weight:bold; font-size:11px; }}
            #cancel_btn:hover {{ border-color:{C['txt_dim']}; }}
            #open_btn     {{ background:{C['cyan']}; border:none; border-radius:6px;
                             color:{C['bg_dark']}; font-weight:bold; font-size:12px; }}
            #open_btn:hover    {{ background:{C['green']}; color:white; }}
            #open_btn:disabled {{ background:{C['bg_light']}; color:{C['txt_off']}; }}
        """)

    # ── Navigation ───────────────────────────────────────────────────────────
    def _navigate(self, path: str):
        if not os.path.isdir(path):
            return
        self._cwd      = path
        self._selected = ''
        self.open_btn.setEnabled(False)
        self.path_lbl.setText(path)
        self.preview.hide_preview()
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
                s = QLabel("›")
                s.setStyleSheet(f"color:{C['txt_off']}; font-size:12px;")
                self.bread_layout.addWidget(s)

            is_last = (i == min(3, len(parts) - 1))
            name    = part.name or str(part)
            btn     = QPushButton(name)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if is_last:
                btn.setStyleSheet(
                    f"color:{C['cyan']}; background:transparent;"
                    f" border:none; font-weight:bold; font-size:11px;"
                )
            else:
                btn.setStyleSheet(
                    f"color:{C['txt_dim']}; background:transparent;"
                    f" border:none; font-size:11px;"
                )
                btn.clicked.connect(lambda _, pt=str(part): self._navigate(pt))
            self.bread_layout.addWidget(btn)

        self.bread_layout.addStretch()

    # ── Grid ─────────────────────────────────────────────────────────────────
    def _load_grid(self):
        # Qt auto-deletes old grid_widget on setWidget() — never call deleteLater manually
        self._tiles.clear()
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet(f"background:{C['bg_dark']};")
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

        lay = QVBoxLayout(self.grid_widget)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(0)

        if not all_e:
            empty = QLabel(self.locale.get("image_picker.empty_folder"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{C['txt_off']}; font-size:13px;")
            lay.addWidget(empty)
            return

        def _row():
            r = QHBoxLayout()
            r.setSpacing(12)
            r.setContentsMargins(0, 0, 0, 0)
            return r

        cur, col = _row(), 0
        for entry in all_e:
            tile = FileTile(entry.path, entry.is_dir())
            tile.clicked.connect(self._on_tile_click)
            tile.activated.connect(self._on_tile_activate)
            cur.addWidget(tile)
            self._tiles.append(tile)
            col += 1
            if col == self.COLS:
                lay.addLayout(cur)
                lay.addSpacing(12)
                cur, col = _row(), 0

        if col > 0:
            cur.addStretch()
            lay.addLayout(cur)
        lay.addStretch()

        # Staggered fade-in via tile_opacity — no QGraphicsOpacityEffect (Wayland safe)
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
            QTimer.singleShot(min(i * 18, 300), _fade)

        # Background thumbnail loading
        for tile in self._tiles:
            if not tile.is_dir:
                sig    = ThumbSignals()
                sig.done.connect(self._on_thumb_done)
                loader = ThumbLoader(tile.path, sig)
                self._pool.start(loader)

    def _on_thumb_done(self, path: str, px: QPixmap):
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
            self.preview.show_file(path)
        else:
            self._selected = ''
            self.open_btn.setEnabled(False)
            self.preview.hide_preview()

    def _on_tile_activate(self, path: str):
        if os.path.isdir(path):
            self._navigate(path)
        else:
            self._selected = path
            self._confirm()

    def _filter_tiles(self, text: str):
        q = text.lower()
        for tile in self._tiles:
            tile.setVisible(not q or q in os.path.basename(tile.path).lower())

    def _confirm(self):
        if self._selected:
            self.accept()

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