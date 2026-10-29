"""
Reusable sidebar building blocks for the main window.

None of these widgets set colors or fonts; they expose objectNames and
`variant` / `role` properties that assets/themes/theme_template.qss styles.
"""
from __future__ import annotations

from PySide6.QtCore import Property, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from src.views.icons import bind_icon, unbind_icon


def caption(text: str = "", role: str = "caption") -> QLabel:
    """A word-wrapped secondary text label."""
    label = QLabel(text)
    label.setProperty("role", role)
    label.setWordWrap(True)
    return label


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def color_property(attr: str) -> Property:
    """
    A QColor Qt property backed by `self.<attr>`, so custom-painted widgets
    get their colors from the stylesheet:  #Widget { qproperty-accentColor: … }
    """
    def getter(self):
        return getattr(self, attr)

    def setter(self, value):
        setattr(self, attr, QColor(value))
        self.update()

    return Property(QColor, getter, setter)


class _SectionHeader(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SectionHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


class CollapsibleSection(QFrame):
    """
    A numbered, collapsible sidebar section:

        ⌄ (1) What to hide ················ Face
          <body>
    """

    def __init__(self, step: int, parent=None):
        super().__init__(parent)
        self.setObjectName("Section")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 10)
        root.setSpacing(6)

        self._header = _SectionHeader()
        self._header.clicked.connect(self.toggle)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(4, 6, 6, 6)
        header_layout.setSpacing(8)

        self._chevron = QLabel()
        self._step = QLabel(str(step))
        self._step.setObjectName("SectionStep")
        self._title = QLabel()
        self._title.setObjectName("SectionTitle")
        self._summary = QLabel()
        self._summary.setObjectName("SectionSummary")

        header_layout.addWidget(self._chevron)
        header_layout.addWidget(self._step)
        header_layout.addWidget(self._title)
        header_layout.addStretch(1)
        header_layout.addWidget(self._summary)
        root.addWidget(self._header)

        self.body = QWidget()
        self.body.setObjectName("SectionBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(4, 2, 4, 0)
        self.body_layout.setSpacing(10)
        root.addWidget(self.body)

        self.set_expanded(True)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_summary(self, text: str) -> None:
        self._summary.setText(text)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.body.setVisible(expanded)
        self._summary.setVisible(not expanded)
        self._update_chevron()

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def changeEvent(self, event):
        if event.type() == event.Type.LayoutDirectionChange:
            self._update_chevron()
        super().changeEvent(event)

    def _update_chevron(self) -> None:
        if self._expanded:
            name = "chevron_down"
        elif self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            name = "chevron_left"
        else:
            name = "chevron_right"
        bind_icon(self._chevron, name, 16, "text_secondary")


class OptionGrid(QWidget):
    """
    An exclusive set of options laid out in a grid.

    variant="tile":  icon above a short label (effects)
    variant="chip":  icon beside the label (detection modes)
    Options marked `locked` stay clickable but emit `lockedClicked`
    instead of being selected (used for Pro-only features).
    """

    valueChanged = Signal(str)
    lockedClicked = Signal(str)

    def __init__(self, columns: int, variant: str = "tile", parent=None):
        super().__init__(parent)
        self._columns = columns
        self._variant = variant
        self._buttons: dict[str, QAbstractButton] = {}
        self._icons: dict[str, str] = {}
        self._value: str | None = None
        self._next_row = 0
        self._next_col = 0

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(6)
        for col in range(columns):
            self._grid.setColumnStretch(col, 1)

    # ── Building ─────────────────────────────────────────────────────────────

    def add_heading(self, text: str = "") -> QLabel:
        """A full-width label that starts a new row."""
        self._new_row()
        label = caption(text, role="heading")
        self._grid.addWidget(label, self._next_row, 0, 1, self._columns)
        self._next_row += 1
        return label

    def add_option(self, value: str, icon: str, text: str = "", wide: bool = False) -> QAbstractButton:
        if self._variant == "tile" and not wide:
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setMinimumHeight(62)
            icon_size = 22
        else:
            button = QPushButton()
            button.setMinimumHeight(36)
            icon_size = 16
        button.setProperty("variant", "tile" if isinstance(button, QToolButton) else "chip")
        button.setCheckable(True)
        button.setText(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setProperty("_icon_size", icon_size)
        button.clicked.connect(lambda _checked=False, v=value: self._on_clicked(v))

        self._buttons[value] = button
        self._icons[value] = icon
        self._group.addButton(button)
        bind_icon(button, icon, icon_size, "text_secondary")

        if wide:
            self._new_row()
            self._grid.addWidget(button, self._next_row, 0, 1, self._columns)
            self._next_row += 1
        else:
            self._grid.addWidget(button, self._next_row, self._next_col)
            self._next_col += 1
            if self._next_col >= self._columns:
                self._new_row()
        return button

    def _new_row(self) -> None:
        if self._next_col:
            self._next_row += 1
            self._next_col = 0

    # ── State ────────────────────────────────────────────────────────────────

    def value(self) -> str | None:
        return self._value

    def set_value(self, value: str) -> None:
        """Select an option without emitting valueChanged."""
        button = self._buttons.get(value)
        if button is None:
            return
        self._value = value
        button.setChecked(True)

    def button(self, value: str) -> QAbstractButton | None:
        return self._buttons.get(value)

    def set_text(self, value: str, text: str) -> None:
        if value in self._buttons:
            self._buttons[value].setText(text)

    def set_tooltip(self, value: str, text: str) -> None:
        if value in self._buttons:
            self._buttons[value].setToolTip(text)

    def set_locked(self, value: str, locked: bool) -> None:
        button = self._buttons.get(value)
        if button is None:
            return
        button.setProperty("locked", "true" if locked else "false")
        size = button.property("_icon_size")
        bind_icon(button, "lock" if locked else self._icons[value], size, "text_secondary")
        repolish(button)

    def is_locked(self, value: str) -> bool:
        button = self._buttons.get(value)
        return button is not None and button.property("locked") == "true"

    def set_allowed(self, allowed: set[str] | None) -> None:
        """Enable only `allowed` options (None enables everything)."""
        for value, button in self._buttons.items():
            button.setEnabled(allowed is None or value in allowed)

    def _on_clicked(self, value: str) -> None:
        if self.is_locked(value):
            # Put the check mark back where it was
            if self._value in self._buttons:
                self._buttons[self._value].setChecked(True)
            self.lockedClicked.emit(value)
            return
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)


class SliderRow(QWidget):
    """
        Label ······················ [ 51 ]
        ━━━━━━━━━━━●──────────────────────
    """

    valueChanged = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, step: int = 1, suffix: str = "", parent=None):
        super().__init__(parent)
        self._suffix = suffix

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._label = QLabel()
        self._label.setProperty("role", "field-label")
        self._value_label = QLabel()
        self._value_label.setProperty("role", "value-pill")
        top.addWidget(self._label)
        top.addStretch(1)
        top.addWidget(self._value_label)
        layout.addLayout(top)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setSingleStep(step)
        self._slider.setPageStep(step * 5)
        self._slider.setValue(value)
        self._slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._slider)

        self._show_value(value)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        """Move the slider without emitting valueChanged."""
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self._show_value(self._slider.value())

    def _on_value_changed(self, value: int) -> None:
        self._show_value(value)
        self.valueChanged.emit(value)

    def _show_value(self, value: int) -> None:
        self._value_label.setText(f"{value}{self._suffix}")


class SegmentedControl(QWidget):
    """A row of joined, mutually exclusive buttons:  [ Keep | Strip | Decoy ]"""

    valueChanged = Signal(str)

    def __init__(self, values: list[str], parent=None):
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        self._value = values[0]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        group = QButtonGroup(self)
        group.setExclusive(True)
        for value in values:
            button = QPushButton()
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("variant", "segment")
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, v=value: self._on_clicked(v))
            group.addButton(button)
            layout.addWidget(button)
            self._buttons[value] = button
        self._buttons[self._value].setChecked(True)
        self._update_positions()

    def changeEvent(self, event):
        if event.type() == event.Type.LayoutDirectionChange:
            self._update_positions()
        super().changeEvent(event)

    def _update_positions(self) -> None:
        """Rounded ends sit on the visual left/right, so they follow the reading direction."""
        values = list(self._buttons)
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        first, last = (values[-1], values[0]) if rtl else (values[0], values[-1])
        for value, button in self._buttons.items():
            button.setProperty("position", "first" if value == first else "last" if value == last else "middle")
            repolish(button)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value in self._buttons:
            self._value = value
            self._buttons[value].setChecked(True)

    def set_text(self, value: str, text: str) -> None:
        self._buttons[value].setText(text)

    def set_locked(self, value: str, locked: bool) -> None:
        """A locked option stays clickable (so it can offer an upgrade) but looks locked."""
        button = self._buttons.get(value)
        if button is None:
            return
        button.setProperty("locked", "true" if locked else "false")
        if locked:
            bind_icon(button, "lock", 12, "text_disabled")
        else:
            unbind_icon(button)
        repolish(button)

    def is_locked(self, value: str) -> bool:
        button = self._buttons.get(value)
        return button is not None and button.property("locked") == "true"

    def _on_clicked(self, value: str) -> None:
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)
