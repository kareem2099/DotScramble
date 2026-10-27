"""
ImageCanvas — the main image view.

Everything is stored in *image* coordinates and drawn through a single
scale + offset transform, so zooming, panning, manual regions, detection
overlays and the before/after split always line up.

Interaction
    wheel                    zoom around the cursor
    drag (manual mode)       draw a region            → regionDrawn
    drag (other modes)       pan when zoomed in
    middle-drag              pan in any mode
    click a detection        include / skip it        → detectionsChanged
    drag the split handle    move the compare divider
    drop a file              → fileDropped

Colors come from the stylesheet (see "Canvas" in theme_template.qss).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from src.views.icons import IconProvider
from src.views.widgets import color_property


class ImageCanvas(QWidget):
    fileDropped = Signal(str)
    regionDrawn = Signal(QRect)        # image coordinates
    detectionsChanged = Signal()       # a detection was included / skipped
    zoomChanged = Signal(float)        # effective scale (1.0 == 100 %)

    MIN_ZOOM = 0.05
    MAX_ZOOM = 8.0
    ZOOM_STEP = 1.25
    FIT_PADDING = 0.95
    CLICK_SLOP = 4                     # px of movement still counted as a click
    SPLIT_GRAB = 10                    # px either side of the divider that grabs it

    backgroundColor = color_property("_bg")
    accentColor = color_property("_accent")
    dangerColor = color_property("_danger")
    mutedColor = color_property("_muted")
    textColor = color_property("_text")
    surfaceColor = color_property("_surface")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageCanvas")
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._bg = QColor("#1e1e1e")
        self._accent = QColor("#00bcd4")
        self._danger = QColor("#f44336")
        self._muted = QColor("#808080")
        self._text = QColor("#cccccc")
        self._surface = QColor("#252526")

        self._pixmap: QPixmap | None = None
        self._before: QPixmap | None = None    # set while comparing
        self._split = 0.5                      # divider position, 0..1 of image width
        self._zoom: float | None = None        # None → fit to view
        self._offset = QPointF(0, 0)           # image top-left in widget coords
        self._scaled_cache: dict[int, tuple[float, QPixmap]] = {}

        self._regions: list[QRectF] = []
        self._detections: list[QPolygonF] = []
        self._skipped: set[int] = set()

        self._drawing_enabled = False
        self._drag_active = False
        self._press_pos: QPointF | None = None
        self._drag_kind: str | None = None     # "draw" | "pan" | "split"
        self._drag_current: QPointF | None = None
        self._pan_start_offset = QPointF(0, 0)

        self._placeholder = ("", "")
        self._compare_labels = ("", "")

        IconProvider.instance().changed.connect(self.update)

    # ── Public API ───────────────────────────────────────────────────────────

    def has_image(self) -> bool:
        return self._pixmap is not None

    def set_image(self, pixmap: QPixmap) -> None:
        """Show a new pixmap. The view is kept when the size is unchanged (e.g. after an effect)."""
        same_size = self._pixmap is not None and self._pixmap.size() == pixmap.size()
        self._pixmap = pixmap
        self._scaled_cache.pop(0, None)
        if not same_size:
            self._zoom = None
        self._relayout()

    def clear(self) -> None:
        self._pixmap = None
        self._before = None
        self._regions = []
        self.clear_detections()
        self._scaled_cache.clear()
        self.update()

    def set_compare_image(self, pixmap: QPixmap | None) -> None:
        """Pass the original image to show a before/after split, or None to stop comparing."""
        self._before = pixmap
        self._scaled_cache.pop(1, None)
        self.update()

    def is_comparing(self) -> bool:
        return self._before is not None

    def set_regions(self, regions) -> None:
        self._regions = [QRectF(x, y, w, h) for (x, y, w, h) in regions]
        self.update()

    def set_detections(self, polygons) -> None:
        """polygons: list of [(x, y), ...] in image coordinates. All start included."""
        self._detections = [QPolygonF([QPointF(x, y) for x, y in pts]) for pts in polygons]
        self._skipped = set()
        self.update()

    def clear_detections(self) -> None:
        self._detections = []
        self._skipped = set()
        self.update()

    def skipped_detections(self) -> set[int]:
        return set(self._skipped)

    def set_drawing_enabled(self, enabled: bool) -> None:
        self._drawing_enabled = enabled
        self._update_cursor(None)

    def set_placeholder(self, title: str, subtitle: str) -> None:
        self._placeholder = (title, subtitle)
        self.update()

    def set_compare_labels(self, before: str, after: str) -> None:
        self._compare_labels = (before, after)
        self.update()

    def scale(self) -> float:
        return self._zoom if self._zoom is not None else self._fit_scale()

    def is_fit(self) -> bool:
        return self._zoom is None

    def zoom_in(self) -> None:
        self._zoom_to(self.scale() * self.ZOOM_STEP, self._view_center())

    def zoom_out(self) -> None:
        self._zoom_to(self.scale() / self.ZOOM_STEP, self._view_center())

    def zoom_actual(self) -> None:
        self._zoom_to(1.0, self._view_center())

    def zoom_to_fit(self) -> None:
        self._zoom = None
        self._relayout()

    # ── Geometry ─────────────────────────────────────────────────────────────

    def _fit_scale(self) -> float:
        if self._pixmap is None or self._pixmap.width() == 0 or self._pixmap.height() == 0:
            return 1.0
        return min(self.width() / self._pixmap.width(),
                   self.height() / self._pixmap.height()) * self.FIT_PADDING

    def _view_center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _image_rect(self) -> QRectF:
        s = self.scale()
        return QRectF(self._offset.x(), self._offset.y(), self._pixmap.width() * s, self._pixmap.height() * s)

    def _to_image(self, point: QPointF) -> QPointF:
        s = self.scale()
        return QPointF((point.x() - self._offset.x()) / s, (point.y() - self._offset.y()) / s)

    def _to_widget(self, point: QPointF) -> QPointF:
        s = self.scale()
        return QPointF(point.x() * s + self._offset.x(), point.y() * s + self._offset.y())

    def _split_x(self) -> float:
        rect = self._image_rect()
        return rect.left() + rect.width() * self._split

    def _zoom_to(self, scale: float, anchor: QPointF) -> None:
        if self._pixmap is None:
            return
        scale = max(self.MIN_ZOOM, min(self.MAX_ZOOM, scale))
        image_point = self._to_image(anchor)
        self._zoom = scale
        self._offset = QPointF(anchor.x() - image_point.x() * scale, anchor.y() - image_point.y() * scale)
        self._clamp_offset()
        self.zoomChanged.emit(self.scale())
        self.update()

    def _relayout(self) -> None:
        """Center the image when it fits, otherwise keep it inside the view."""
        if self._pixmap is None:
            self.update()
            return
        if self._zoom is None:
            s = self._fit_scale()
            self._offset = QPointF((self.width() - self._pixmap.width() * s) / 2,
                                   (self.height() - self._pixmap.height() * s) / 2)
        self._clamp_offset()
        self.zoomChanged.emit(self.scale())
        self.update()

    def _clamp_offset(self) -> None:
        s = self.scale()
        w, h = self._pixmap.width() * s, self._pixmap.height() * s
        x, y = self._offset.x(), self._offset.y()
        x = (self.width() - w) / 2 if w <= self.width() else min(0, max(self.width() - w, x))
        y = (self.height() - h) / 2 if h <= self.height() else min(0, max(self.height() - h, y))
        self._offset = QPointF(x, y)

    def _scaled(self, slot: int, pixmap: QPixmap) -> QPixmap | None:
        """Pre-scaled copy for zoomed-out views (smooth and cheap to repaint while panning)."""
        s = self.scale()
        if s >= 1.0:
            return None
        cached = self._scaled_cache.get(slot)
        if cached and abs(cached[0] - s) < 1e-6 and cached[1].width() == round(pixmap.width() * s):
            return cached[1]
        scaled = pixmap.scaled(round(pixmap.width() * s), round(pixmap.height() * s),
                               Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._scaled_cache[slot] = (s, scaled)
        return scaled

    def _detection_at(self, widget_pos: QPointF) -> int | None:
        image_pos = self._to_image(widget_pos)
        for index in reversed(range(len(self._detections))):
            if self._detections[index].containsPoint(image_pos, Qt.FillRule.OddEvenFill):
                return index
        return None

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), self._bg)

        if self._pixmap is None:
            self._paint_placeholder(painter)
        else:
            self._paint_image(painter)
            self._paint_overlays(painter)
            if self._before is not None:
                self._paint_split(painter)

        if self._drag_active:
            painter.setPen(QPen(self._accent, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 8, 8)

    def _draw_pixmap(self, painter: QPainter, slot: int, pixmap: QPixmap, rect: QRectF) -> None:
        scaled = self._scaled(slot, pixmap)
        if scaled is not None:
            painter.drawPixmap(rect.topLeft(), scaled)
        else:
            painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))

    def _paint_image(self, painter: QPainter) -> None:
        rect = self._image_rect()
        self._draw_pixmap(painter, 0, self._pixmap, rect)
        if self._before is not None and self._before.size() == self._pixmap.size():
            painter.save()
            painter.setClipRect(QRectF(rect.left(), rect.top(), self._split_x() - rect.left(), rect.height()))
            self._draw_pixmap(painter, 1, self._before, rect)
            painter.restore()

    def _paint_overlays(self, painter: QPainter) -> None:
        # Manual regions
        pen = QPen(self._accent, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for region in self._regions:
            painter.drawRect(QRectF(self._to_widget(region.topLeft()), self._to_widget(region.bottomRight())))

        # Detections: included = solid accent, skipped = dashed muted
        for index, polygon in enumerate(self._detections):
            mapped = QPolygonF([self._to_widget(p) for p in polygon])
            if index in self._skipped:
                painter.setPen(QPen(self._muted, 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            else:
                fill = QColor(self._accent)
                fill.setAlpha(45)
                painter.setPen(QPen(self._accent, 2))
                painter.setBrush(QBrush(fill))
            painter.drawPolygon(mapped)

        # Rectangle being drawn
        if self._drag_kind == "draw" and self._press_pos and self._drag_current:
            painter.setPen(QPen(self._accent, 2))
            fill = QColor(self._accent)
            fill.setAlpha(30)
            painter.setBrush(fill)
            painter.drawRect(QRectF(self._press_pos, self._drag_current).normalized())

    def _paint_split(self, painter: QPainter) -> None:
        rect = self._image_rect()
        x = self._split_x()
        top, bottom = max(rect.top(), 0), min(rect.bottom(), self.height())

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))

        handle = QRectF(x - 14, (top + bottom) / 2 - 14, 28, 28)
        painter.setPen(QPen(self._accent, 2))
        painter.setBrush(self._surface)
        painter.drawEllipse(handle)
        painter.setPen(QPen(self._accent, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cy = handle.center().y()
        for direction in (-1, 1):
            tip = x + direction * 7
            painter.drawLine(QPointF(x + direction * 2, cy - 4), QPointF(tip, cy))
            painter.drawLine(QPointF(tip, cy), QPointF(x + direction * 2, cy + 4))

        before, after = self._compare_labels
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        for text, left_side in ((before, True), (after, False)):
            if not text:
                continue
            width = painter.fontMetrics().horizontalAdvance(text) + 16
            px = (rect.left() + 10) if left_side else (rect.right() - width - 10)
            pill = QRectF(max(px, 6), max(rect.top(), 0) + 10, width, 20)
            back = QColor(0, 0, 0, 150)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(back)
            painter.drawRoundedRect(pill, 10, 10)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_placeholder(self, painter: QPainter) -> None:
        area = QRectF(self.rect()).adjusted(28, 28, -28, -28)
        path = QPainterPath()
        path.addRoundedRect(area, 14, 14)
        painter.setPen(QPen(self._accent if self._drag_active else self._muted, 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        icon = IconProvider.instance().pixmap("drop", 56, "accent_cyan")
        center = area.center()
        painter.drawPixmap(QPointF(center.x() - 28, center.y() - 70), icon)

        title, subtitle = self._placeholder
        font = QFont(self.font())
        font.setPixelSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self._accent)
        painter.drawText(QRectF(area.left(), center.y() + 2, area.width(), 28), Qt.AlignmentFlag.AlignCenter, title)

        font.setPixelSize(13)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(self._text)
        painter.drawText(QRectF(area.left(), center.y() + 34, area.width(), 22), Qt.AlignmentFlag.AlignCenter, subtitle)

    # ── Mouse & keyboard ─────────────────────────────────────────────────────

    def _near_split(self, pos: QPointF) -> bool:
        if self._before is None or self._pixmap is None:
            return False
        rect = self._image_rect()
        return abs(pos.x() - self._split_x()) <= self.SPLIT_GRAB and rect.top() <= pos.y() <= rect.bottom()

    def _can_pan(self) -> bool:
        rect = self._image_rect()
        return rect.width() > self.width() or rect.height() > self.height()

    def _update_cursor(self, pos: QPointF | None) -> None:
        if self._drag_kind == "pan":
            shape = Qt.CursorShape.ClosedHandCursor
        elif self._drag_kind == "split" or (pos is not None and self._near_split(pos)):
            shape = Qt.CursorShape.SplitHCursor
        elif self._pixmap is not None and pos is not None and self._detection_at(pos) is not None:
            shape = Qt.CursorShape.PointingHandCursor
        elif self._pixmap is not None and self._drawing_enabled:
            shape = Qt.CursorShape.CrossCursor
        elif self._pixmap is not None and self._can_pan():
            shape = Qt.CursorShape.OpenHandCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.setCursor(shape)

    def mousePressEvent(self, event):
        if self._pixmap is None:
            return
        pos = event.position()
        self._press_pos = pos
        self._drag_current = pos
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag_kind = "pan"
        elif event.button() == Qt.MouseButton.LeftButton:
            if self._near_split(pos):
                self._drag_kind = "split"
            elif self._drawing_enabled and self._image_rect().contains(pos):
                self._drag_kind = "draw"
            else:
                self._drag_kind = "pan"
        self._pan_start_offset = QPointF(self._offset)
        self._update_cursor(pos)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_kind == "split":
            rect = self._image_rect()
            self._split = min(1.0, max(0.0, (pos.x() - rect.left()) / max(rect.width(), 1)))
            self.update()
        elif self._drag_kind == "draw":
            self._drag_current = pos
            self.update()
        elif self._drag_kind == "pan" and self._press_pos is not None and self._can_pan():
            self._offset = self._pan_start_offset + (pos - self._press_pos)
            self._clamp_offset()
            self.update()
        self._update_cursor(pos)

    def mouseReleaseEvent(self, event):
        if self._press_pos is None:
            return
        pos = event.position()
        moved = (pos - self._press_pos).manhattanLength() > self.CLICK_SLOP
        kind = self._drag_kind

        if kind == "draw" and moved:
            self._emit_drawn_region(self._press_pos, pos)
        elif not moved and kind in ("pan", "draw"):
            index = self._detection_at(pos)
            if index is not None:
                self._skipped ^= {index}
                self.detectionsChanged.emit()

        self._press_pos = None
        self._drag_current = None
        self._drag_kind = None
        self._update_cursor(pos)
        self.update()

    def _emit_drawn_region(self, start: QPointF, end: QPointF) -> None:
        a, b = self._to_image(start), self._to_image(end)
        rect = QRectF(a, b).normalized().intersected(QRectF(self._pixmap.rect()))
        if rect.width() > 10 and rect.height() > 10:
            self.regionDrawn.emit(rect.toRect())

    def wheelEvent(self, event):
        if self._pixmap is None:
            return
        delta = event.angleDelta().y()
        if delta:
            factor = self.ZOOM_STEP if delta > 0 else 1 / self.ZOOM_STEP
            self._zoom_to(self.scale() * factor, event.position())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap is not None:
            self._relayout()

    # ── Drag & drop ──────────────────────────────────────────────────────────

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
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.fileDropped.emit(path)
                break
