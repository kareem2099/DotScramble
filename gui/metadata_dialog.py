"""
DotScramble — Metadata Customizer Dialog (PySide6 version)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Per-field EXIF control: Keep / Strip / Spoof / Custom value.
"""
from __future__ import annotations

import sys
import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QComboBox, QScrollArea, QFrame, QRadioButton, QButtonGroup, 
    QLineEdit, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt

from src.config import COLORS
from gui import metadata_presets as presets

# ── Field definitions ─────────────────────────────────────────────────────────
EXIF_FIELDS = [
    ("gps",       "📍 GPS Location",  "gps",      "spoof"),
    ("make",      "📷 Camera Make",   "text",     "spoof"),
    ("model",     "📷 Camera Model",  "text",     "spoof"),
    ("software",  "💻 Software",      "text",     "spoof"),
    ("datetime",  "🕐 Date / Time",   "datetime", "spoof"),
    ("copyright", "©️  Copyright",     "text",     "keep"),
    ("exposure",  "🔆 Exposure Data", "exposure", "spoof"),
]

ACTIONS = ["keep", "strip", "spoof", "custom"]
ACTION_LABELS = {
    "keep":   "✅ Keep",
    "strip":  "🗑 Strip",
    "spoof":  "🎲 Spoof",
    "custom": "✏️ Custom",
}


class MetadataCustomizerDialog(QDialog):
    """
    Modal dialog that lets the user set a per-field action for each EXIF tag.
    """

    def __init__(self, parent=None, current_exif: dict | None = None):
        super().__init__(parent)
        self.result: dict | None = None
        self._current = current_exif or {}

        # Get active colors from parent or default
        if parent and hasattr(parent, 'colors'):
            self.colors = parent.colors
        else:
            self.colors = COLORS

        self.action_colors = {
            "keep":   self.colors.get('accent_green', '#4CAF50'),
            "strip":  self.colors.get('accent_red', '#F44336'),
            "spoof":  self.colors.get('accent_cyan', '#2196F3'),
            "custom": self.colors.get('accent_orange', '#FF9800'),
        }
        
        self.setWindowTitle("DotScramble — Custom Metadata Control")
        self.setMinimumSize(620, 650)
        self.resize(620, 650)
        
        # Track widget variables
        self._action_groups: dict[str, QButtonGroup] = {}
        self._custom_fields: dict[str, QWidget] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._lat_input = QLineEdit()
        self._lon_input = QLineEdit()

        self._build_ui()
        self._load_current_values()

    def _build_ui(self):
        from PySide6.QtGui import QFont
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)

        title_lbl = QLabel("🛡️  Custom Metadata Control")
        title_lbl.setObjectName("DialogTitle")
        title_lbl.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        hdr_layout.addWidget(title_lbl)

        plan_lbl = QLabel("Max Plan")
        plan_lbl.setObjectName("plan_lbl")
        hdr_layout.addWidget(plan_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(hdr)

        # ── Presets Toolbar ────────────────────────────────────────────────
        preset_frame = QFrame()
        preset_layout = QHBoxLayout(preset_frame)
        preset_layout.setContentsMargins(20, 10, 20, 5)
        
        preset_lbl = QLabel("Preset:")
        preset_lbl.setObjectName("preset_lbl")
        preset_layout.addWidget(preset_lbl)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(presets.all_preset_names())
        self.preset_combo.setPlaceholderText("Select a preset...")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.preset_combo, 1)

        save_btn = QPushButton("💾 Save As...")
        save_btn.clicked.connect(self._save_current_as_preset)
        preset_layout.addWidget(save_btn)

        self.del_preset_btn = QPushButton("🗑 Delete")
        self.del_preset_btn.setObjectName("del_preset_btn")
        self.del_preset_btn.clicked.connect(self._delete_selected_preset)
        preset_layout.addWidget(self.del_preset_btn)

        main_layout.addWidget(preset_frame)

        # ── Legend ─────────────────────────────────────────────────────────
        legend_frame = QFrame()
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(20, 5, 20, 5)
        legend_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for action in ACTIONS:
            lbl = QLabel(ACTION_LABELS[action])
            lbl.setObjectName(f"legend_{action}")
            legend_layout.addWidget(lbl)

        main_layout.addWidget(legend_frame)

        # ── Scrollable field list ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 5, 20, 5)
        scroll_layout.setSpacing(8)

        for key, label, ftype, default in EXIF_FIELDS:
            card = self._build_field_row(key, label, ftype, default)
            scroll_layout.addWidget(card)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # ── Bottom buttons ──────────────────────────────────────────────────
        btn_frame = QFrame()
        btn_frame.setObjectName("btn_frame")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 10, 20, 10)

        spoof_all_btn = QPushButton("🎲 Spoof All")
        spoof_all_btn.clicked.connect(lambda: self._set_all("spoof"))
        btn_layout.addWidget(spoof_all_btn)

        strip_all_btn = QPushButton("🗑 Strip All")
        strip_all_btn.setObjectName("strip_all_btn")
        strip_all_btn.clicked.connect(lambda: self._set_all("strip"))
        btn_layout.addWidget(strip_all_btn)

        btn_layout.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("✅  Apply")
        apply_btn.setObjectName("primary_action")
        apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(apply_btn)

        main_layout.addWidget(btn_frame)

    def _build_field_row(self, key: str, label: str, ftype: str, default: str) -> QFrame:
        from PySide6.QtGui import QFont
        card = QFrame()
        card.setObjectName("card_frame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # Top row: Label & current value
        top_row = QHBoxLayout()
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        top_row.addWidget(name_lbl)

        current_val = self._get_current_value(key)
        val_text = current_val[:35] + "…" if len(current_val) > 35 else current_val
        val_lbl = QLabel(val_text or "—")
        val_lbl.setObjectName("card_val_lbl_active" if current_val else "card_val_lbl_inactive")
        top_row.addWidget(val_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        
        card_layout.addLayout(top_row)

        # Radio buttons row
        radio_row = QHBoxLayout()
        radio_row.setSpacing(6)
        
        group = QButtonGroup(card)
        self._action_groups[key] = group

        valid_actions = ACTIONS if ftype != "exposure" else ["keep", "strip", "spoof"]
        for act in valid_actions:
            rb = QRadioButton(ACTION_LABELS[act])
            rb.setStyleSheet(f"QRadioButton::indicator {{ width: 0px; height: 0px; }} QRadioButton {{ padding: 3px 8px; background-color: {self.colors['bg_dark']}; border: 1px solid {self.colors['border_color']}; border-radius: 4px; }} QRadioButton:checked {{ background-color: {self.action_colors[act]}; color: white; border: none; }}")
            group.addButton(rb, valid_actions.index(act))
            
            # Map action value to button text/data
            rb.setProperty("action_val", act)
            radio_row.addWidget(rb)
            
            if act == default:
                rb.setChecked(True)

        card_layout.addLayout(radio_row)

        # Custom input frame
        custom_input_widget = QWidget()
        custom_layout = QHBoxLayout(custom_input_widget)
        custom_layout.setContentsMargins(0, 5, 0, 0)
        self._custom_fields[key] = custom_input_widget

        if ftype == "gps":
            custom_layout.addWidget(QLabel("Lat:"))
            self._lat_input.setPlaceholderText("Latitude")
            self._lat_input.setFixedWidth(100)
            custom_layout.addWidget(self._lat_input)
            
            custom_layout.addWidget(QLabel("Lon:"))
            self._lon_input.setPlaceholderText("Longitude")
            self._lon_input.setFixedWidth(100)
            custom_layout.addWidget(self._lon_input)
            custom_layout.addStretch(1)
        elif ftype in ("text", "datetime", "copyright"):
            custom_layout.addWidget(QLabel("Custom value:"))
            inp = QLineEdit()
            inp.setPlaceholderText(current_val)
            custom_layout.addWidget(inp, 1)
            self._text_inputs[key] = inp

        card_layout.addWidget(custom_input_widget)
        
        # Connect change listener
        group.buttonClicked.connect(lambda btn, k=key: self._on_action_toggled(k, btn.property("action_val")))

        # Initial visibility setup
        custom_input_widget.setVisible(default == "custom")
        
        return card

    def _on_action_toggled(self, key: str, action: str):
        if key in self._custom_fields:
            self._custom_fields[key].setVisible(action == "custom")

    def _set_all(self, action: str):
        for key, group in self._action_groups.items():
            for btn in group.buttons():
                if btn.property("action_val") == action:
                    btn.setChecked(True)
                    self._on_action_toggled(key, action)
                    break

    def _get_current_value(self, key: str) -> str:
        v = self._current.get(key)
        if v is None:
            return ""
        if key == "gps" and isinstance(v, dict):
            return f"{v.get('lat', '')}, {v.get('lon', '')}"
        if key == "exposure" and isinstance(v, dict):
            return f"{v.get('shutter','?')}  {v.get('fnumber','?')}  ISO{v.get('iso','?')}"
        return str(v)

    def _load_current_values(self):
        # Pre-fill custom GPS fields
        cur_gps = self._current.get("gps")
        if cur_gps and isinstance(cur_gps, dict):
            self._lat_input.setText(str(cur_gps.get("lat", "")))
            self._lon_input.setText(str(cur_gps.get("lon", "")))

    def _get_current_actions(self) -> dict:
        result = {}
        for key, group in self._action_groups.items():
            checked_btn = group.checkedButton()
            action = checked_btn.property("action_val") if checked_btn else "keep"
            
            if action == "custom":
                if key == "gps":
                    try:
                        result[key] = {"lat": float(self._lat_input.text()), "lon": float(self._lon_input.text())}
                    except ValueError:
                        result[key] = "spoof"
                else:
                    inp = self._text_inputs.get(key)
                    val = inp.text().strip() if inp else ""
                    result[key] = {"value": val} if val else "spoof"
            else:
                result[key] = action
        return result

    def _load_actions_into_ui(self, actions: dict):
        for key, group in self._action_groups.items():
            act = actions.get(key, "keep")
            action_val = "custom" if isinstance(act, dict) else act
            
            for btn in group.buttons():
                if btn.property("action_val") == action_val:
                    btn.setChecked(True)
                    self._on_action_toggled(key, action_val)
                    
                    if isinstance(act, dict):
                        if key == "gps":
                            self._lat_input.setText(str(act.get("lat", "")))
                            self._lon_input.setText(str(act.get("lon", "")))
                        else:
                            inp = self._text_inputs.get(key)
                            if inp:
                                inp.setText(act.get("value", ""))
                    break

    def _on_preset_selected(self, idx: int):
        name = self.preset_combo.currentText()
        if not name:
            return
        data = presets.load_preset(name)
        if data:
            self._load_actions_into_ui(data)
        
        self.del_preset_btn.setEnabled(not presets.is_factory(name))

    def _save_current_as_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Enter a name for this preset:")
        if not ok or not name:
            return
        name = name.strip()
        if not name:
            return
        if presets.is_factory(name):
            QMessageBox.critical(self, "Error", "Cannot overwrite a factory preset.")
            return
        
        actions = self._get_current_actions()
        presets.save_preset(name, actions)
        
        # Refresh combo
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(presets.all_preset_names())
        self.preset_combo.setCurrentText(name)
        self.preset_combo.blockSignals(False)
        self.del_preset_btn.setEnabled(True)
        
        QMessageBox.information(self, "Saved", f"Preset '{name}' saved successfully.")

    def _delete_selected_preset(self):
        name = self.preset_combo.currentText()
        if not name or presets.is_factory(name):
            return
        reply = QMessageBox.question(
            self, "Delete Preset", f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if presets.delete_preset(name):
                self.preset_combo.blockSignals(True)
                self.preset_combo.clear()
                self.preset_combo.addItems(presets.all_preset_names())
                self.preset_combo.setCurrentIndex(-1)
                self.preset_combo.blockSignals(False)
                self.del_preset_btn.setEnabled(False)

    def _apply(self):
        self.result = self._get_current_actions()
        self.accept()

    def _cancel(self):
        self.result = None
        self.reject()
