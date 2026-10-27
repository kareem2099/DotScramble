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

from gui import metadata_presets as presets
from src.managers.localization_manager import get_locale_manager


def _t(key: str, **kwargs) -> str:
    return get_locale_manager().get(key, **kwargs)


# ── Field definitions (key, input type, default action) ──────────────────────
# Display names live in the locale files under metadata.fields.<key>
EXIF_FIELDS = [
    ("gps",       "gps",      "spoof"),
    ("make",      "text",     "spoof"),
    ("model",     "text",     "spoof"),
    ("software",  "text",     "spoof"),
    ("datetime",  "datetime", "spoof"),
    ("copyright", "text",     "keep"),
    ("exposure",  "exposure", "spoof"),
]

# Labels: metadata.actions.<action>
ACTIONS = ["keep", "strip", "spoof", "custom"]


class MetadataCustomizerDialog(QDialog):
    """
    Modal dialog that lets the user set a per-field action for each EXIF tag.
    """

    def __init__(self, parent=None, current_exif: dict | None = None):
        super().__init__(parent)
        self.result: dict | None = None
        self._current = current_exif or {}

        self.setWindowTitle(_t("metadata.customizer.window_title"))
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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("DialogHeader")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 10, 20, 10)

        title_lbl = QLabel(_t("metadata.customizer.title"))
        title_lbl.setObjectName("DialogTitle")
        hdr_layout.addWidget(title_lbl)

        plan_lbl = QLabel(_t("metadata.customizer.plan"))
        plan_lbl.setObjectName("plan_lbl")
        hdr_layout.addWidget(plan_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(hdr)

        # ── Presets Toolbar ────────────────────────────────────────────────
        preset_frame = QFrame()
        preset_layout = QHBoxLayout(preset_frame)
        preset_layout.setContentsMargins(20, 10, 20, 5)
        
        preset_lbl = QLabel(_t("metadata.customizer.preset"))
        preset_lbl.setObjectName("preset_lbl")
        preset_layout.addWidget(preset_lbl)

        self.preset_combo = QComboBox()
        self._fill_preset_combo()
        self.preset_combo.setPlaceholderText(_t("metadata.customizer.preset_placeholder"))
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.preset_combo, 1)

        save_btn = QPushButton(_t("metadata.customizer.save_as"))
        save_btn.clicked.connect(self._save_current_as_preset)
        preset_layout.addWidget(save_btn)

        self.del_preset_btn = QPushButton(_t("metadata.customizer.delete"))
        self.del_preset_btn.setObjectName("del_preset_btn")
        self.del_preset_btn.setEnabled(False)  # only user presets can be deleted
        self.del_preset_btn.clicked.connect(self._delete_selected_preset)
        preset_layout.addWidget(self.del_preset_btn)

        main_layout.addWidget(preset_frame)

        # ── Legend ─────────────────────────────────────────────────────────
        legend_frame = QFrame()
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(20, 5, 20, 5)
        legend_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for action in ACTIONS:
            lbl = QLabel(_t(f"metadata.actions.{action}"))
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

        for key, ftype, default in EXIF_FIELDS:
            card = self._build_field_row(key, ftype, default)
            scroll_layout.addWidget(card)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # ── Bottom buttons ──────────────────────────────────────────────────
        btn_frame = QFrame()
        btn_frame.setObjectName("btn_frame")
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 10, 20, 10)

        spoof_all_btn = QPushButton(_t("metadata.customizer.spoof_all"))
        spoof_all_btn.clicked.connect(lambda: self._set_all("spoof"))
        btn_layout.addWidget(spoof_all_btn)

        strip_all_btn = QPushButton(_t("metadata.customizer.strip_all"))
        strip_all_btn.setObjectName("strip_all_btn")
        strip_all_btn.clicked.connect(lambda: self._set_all("strip"))
        btn_layout.addWidget(strip_all_btn)

        btn_layout.addStretch(1)

        cancel_btn = QPushButton(_t("metadata.cancel"))
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton(_t("metadata.customizer.apply"))
        apply_btn.setObjectName("primary_action")
        apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(apply_btn)

        main_layout.addWidget(btn_frame)

    def _build_field_row(self, key: str, ftype: str, default: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card_frame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # Top row: Label & current value
        top_row = QHBoxLayout()
        name_lbl = QLabel(_t(f"metadata.fields.{key}"))
        name_lbl.setProperty("role", "field-label")
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
            rb = QRadioButton(_t(f"metadata.actions.{act}"))
            rb.setProperty("variant", "action")   # styled as a pill in the QSS
            rb.setProperty("action", act)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(rb, valid_actions.index(act))
            
            # Map action value to button text/data
            rb.setProperty("action_val", act)
            radio_row.addWidget(rb)
            
            if act == default:
                rb.setChecked(True)

        card_layout.addLayout(radio_row)

        # Custom input frame
        custom_input_widget = QWidget()
        custom_input_widget.setObjectName("card_row")
        custom_layout = QHBoxLayout(custom_input_widget)
        custom_layout.setContentsMargins(0, 5, 0, 0)
        self._custom_fields[key] = custom_input_widget

        if ftype == "gps":
            custom_layout.addWidget(QLabel(_t("metadata.customizer.lat")))
            self._lat_input.setPlaceholderText(_t("metadata.customizer.lat_placeholder"))
            self._lat_input.setFixedWidth(100)
            custom_layout.addWidget(self._lat_input)
            
            custom_layout.addWidget(QLabel(_t("metadata.customizer.lon")))
            self._lon_input.setPlaceholderText(_t("metadata.customizer.lon_placeholder"))
            self._lon_input.setFixedWidth(100)
            custom_layout.addWidget(self._lon_input)
            custom_layout.addStretch(1)
        elif ftype in ("text", "datetime", "copyright"):
            custom_layout.addWidget(QLabel(_t("metadata.customizer.custom_value")))
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

    def _fill_preset_combo(self, select_user: str | None = None):
        """(Re)fill the combo; each item carries its Preset so labels can be translated."""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for preset in presets.list_presets():
            self.preset_combo.addItem(preset.label, preset)
        index = -1
        if select_user is not None:
            for i in range(self.preset_combo.count()):
                preset = self.preset_combo.itemData(i)
                if not preset.factory and preset.key == select_user:
                    index = i
                    break
        self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def _selected_preset(self):
        return self.preset_combo.currentData()

    def _on_preset_selected(self, idx: int):
        preset = self._selected_preset()
        if preset is None:
            return
        data = presets.load_preset(preset)
        if data:
            self._load_actions_into_ui(data)

        self.del_preset_btn.setEnabled(not preset.factory)

    def _save_current_as_preset(self):
        name, ok = QInputDialog.getText(self, _t("metadata.customizer.save_title"), _t("metadata.customizer.save_prompt"))
        if not ok or not name:
            return
        name = name.strip()
        if not name:
            return
        if presets.is_reserved_name(name):
            QMessageBox.critical(self, _t("metadata.customizer.error_title"), _t("metadata.customizer.factory_error"))
            return
        
        actions = self._get_current_actions()
        presets.save_preset(name, actions)
        
        self._fill_preset_combo(select_user=name)
        self.del_preset_btn.setEnabled(True)
        
        QMessageBox.information(self, _t("metadata.customizer.saved_title"), _t("metadata.customizer.saved_msg", name=name))

    def _delete_selected_preset(self):
        preset = self._selected_preset()
        if preset is None or preset.factory:
            return
        name = preset.key
        reply = QMessageBox.question(
            self, _t("metadata.customizer.delete_title"), _t("metadata.customizer.delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if presets.delete_preset(name):
                self._fill_preset_combo()
                self.del_preset_btn.setEnabled(False)

    def _apply(self):
        self.result = self._get_current_actions()
        self.accept()

    def _cancel(self):
        self.result = None
        self.reject()
