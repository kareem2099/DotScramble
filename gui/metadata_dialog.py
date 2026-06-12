"""
DotScramble — Metadata Customizer Dialog
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Per-field EXIF control: Keep / Strip / Spoof / Custom value.
Used as the "Custom" profile inside create_exif_section().
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.config import COLORS
from gui import metadata_presets as presets
from tkinter import messagebox, simpledialog

# ── Field definitions ─────────────────────────────────────────────────────────
# Each entry: (field_key, display_label, field_type, default_action)
#   field_type: "text" | "gps" | "datetime" | "exposure" (no custom input)
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
ACTION_COLORS = {
    "keep":   "#4CAF50",
    "strip":  "#F44336",
    "spoof":  "#2196F3",
    "custom": "#FF9800",
}
ACTION_LABELS = {
    "keep":   "✅ Keep",
    "strip":  "🗑 Strip",
    "spoof":  "🎲 Spoof",
    "custom": "✏️ Custom",
}


class MetadataCustomizerDialog:
    """
    Modal dialog that lets the user set a per-field action for each EXIF tag.

    Usage:
        dlg = MetadataCustomizerDialog(parent_window, current_exif_dict)
        result = dlg.result   # None if cancelled, else dict of field_actions
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel, current_exif: dict | None = None):
        self.result: dict | None = None
        self._current = current_exif or {}

        self.win = tk.Toplevel(parent)
        self.win.title("DotScramble — Custom Metadata Control")
        self.win.configure(bg=COLORS['bg_dark'])
        self.win.resizable(False, True)
        self.win.transient(parent)
        self.win.grab_set()

        # Center on parent
        self.win.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = 600, 600
        self.win.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")

        self._action_vars: dict[str, tk.StringVar] = {}
        self._custom_vars: dict[str, tk.StringVar] = {}
        self._custom_frames: dict[str, tk.Frame] = {}
        self._lat_var = tk.StringVar()
        self._lon_var = tk.StringVar()

        self._build_ui()
        self.win.wait_window()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ─────────────────────────────────────────────────────────
        hdr = tk.Frame(self.win, bg=COLORS['bg_medium'], height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr,
            text="🛡️  Custom Metadata Control",
            font=("Helvetica", 14, "bold"),
            bg=COLORS['bg_medium'],
            fg=COLORS['accent_cyan'],
        ).pack(side="left", padx=20, pady=15)

        tk.Label(
            hdr,
            text="Max Plan",
            font=("Helvetica", 9, "italic"),
            bg=COLORS['bg_medium'],
            fg=COLORS['accent_orange'],
        ).pack(side="right", padx=20)

        # ── Presets Toolbar ────────────────────────────────────────────────
        preset_frame = tk.Frame(self.win, bg=COLORS['bg_dark'])
        preset_frame.pack(fill="x", padx=20, pady=(10, 0))

        tk.Label(
            preset_frame, text="Preset:",
            font=("Helvetica", 9), bg=COLORS['bg_dark'], fg=COLORS['text_gray']
        ).pack(side="left", padx=(0, 8))

        self.preset_combo = ttk.Combobox(
            preset_frame, state="readonly", width=30,
            values=presets.all_preset_names()
        )
        self.preset_combo.pack(side="left", padx=(0, 10))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        tk.Button(
            preset_frame, text="💾 Save Current As...",
            font=("Helvetica", 8), bg=COLORS['bg_medium'], fg=COLORS['text_white'],
            relief="flat", cursor="hand2", padx=8, pady=2,
            command=self._save_current_as_preset
        ).pack(side="left", padx=4)

        self.del_preset_btn = tk.Button(
            preset_frame, text="🗑 Delete",
            font=("Helvetica", 8), bg=COLORS['bg_medium'], fg="#F44336",
            relief="flat", cursor="hand2", padx=8, pady=2,
            command=self._delete_selected_preset
        )
        self.del_preset_btn.pack(side="left", padx=4)

        # ── Legend ─────────────────────────────────────────────────────────
        legend = tk.Frame(self.win, bg=COLORS['bg_dark'])
        legend.pack(fill="x", padx=20, pady=(10, 4))

        for action, color in ACTION_COLORS.items():
            tk.Label(
                legend,
                text=ACTION_LABELS[action],
                font=("Helvetica", 8, "bold"),
                bg=color,
                fg="white",
                padx=6, pady=2,
            ).pack(side="left", padx=4)

        # ── Scrollable field list ───────────────────────────────────────────
        container = tk.Frame(self.win, bg=COLORS['bg_dark'])
        container.pack(fill="both", expand=True, padx=20, pady=8)

        canvas = tk.Canvas(container, bg=COLORS['bg_dark'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg=COLORS['bg_dark'])

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        win_id = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Avoid bind_all to prevent global conflicts and TclError after destroy
        def _scroll_handler(e):
            if canvas.winfo_exists():
                canvas.yview_scroll(-1 if getattr(e, 'num', 0) == 4 or getattr(e, 'delta', 0) > 0 else 1, "units")

        self.win.bind("<Button-4>", _scroll_handler)
        self.win.bind("<Button-5>", _scroll_handler)
        self.win.bind("<MouseWheel>", _scroll_handler)

        def _bind_to_children(widget):
            for child in widget.winfo_children():
                if not isinstance(child, ttk.Combobox):
                    child.bind("<Button-4>", _scroll_handler)
                    child.bind("<Button-5>", _scroll_handler)
                    child.bind("<MouseWheel>", _scroll_handler)
                _bind_to_children(child)
        
        self.win.after(50, lambda: _bind_to_children(self.win))

        for key, label, ftype, default in EXIF_FIELDS:
            self._build_field_row(self._scroll_frame, key, label, ftype, default)

        # ── Bottom buttons ──────────────────────────────────────────────────
        btn_frame = tk.Frame(self.win, bg=COLORS['bg_medium'], height=55)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=("Helvetica", 10),
            bg=COLORS['bg_light'], fg=COLORS['text_white'],
            relief="flat", cursor="hand2", padx=20,
            command=self._cancel,
        ).pack(side="right", padx=(8, 20), pady=10)

        tk.Button(
            btn_frame,
            text="✅  Apply",
            font=("Helvetica", 10, "bold"),
            bg=COLORS['accent_cyan'], fg=COLORS['bg_dark'],
            relief="flat", cursor="hand2", padx=20,
            command=self._apply,
        ).pack(side="right", padx=4, pady=10)

        tk.Button(
            btn_frame,
            text="🎲 Spoof All",
            font=("Helvetica", 9),
            bg=COLORS['bg_dark'], fg=COLORS['accent_cyan'],
            relief="flat", cursor="hand2", padx=12,
            command=lambda: self._set_all("spoof"),
        ).pack(side="left", padx=(20, 4), pady=10)

        tk.Button(
            btn_frame,
            text="🗑 Strip All",
            font=("Helvetica", 9),
            bg=COLORS['bg_dark'], fg="#F44336",
            relief="flat", cursor="hand2", padx=12,
            command=lambda: self._set_all("strip"),
        ).pack(side="left", padx=4, pady=10)

    def _build_field_row(self, parent, key, label, ftype, default):
        """Build one field row with action radio buttons + optional custom input."""
        action_var = tk.StringVar(value=default)
        custom_var = tk.StringVar()

        self._action_vars[key] = action_var
        self._custom_vars[key] = custom_var

        # Outer card
        card = tk.Frame(parent, bg=COLORS['bg_medium'], pady=0)
        card.pack(fill="x", pady=4)

        # ── Top row: label + current value ──────────────────────────────────
        top = tk.Frame(card, bg=COLORS['bg_medium'])
        top.pack(fill="x", padx=12, pady=(8, 4))

        tk.Label(
            top,
            text=label,
            font=("Helvetica", 10, "bold"),
            bg=COLORS['bg_medium'], fg=COLORS['text_white'],
            width=22, anchor="w",
        ).pack(side="left")

        current_val = self._get_current_value(key)
        val_color   = COLORS['accent_cyan'] if current_val else COLORS['text_gray']
        val_text    = current_val[:30] + "…" if len(current_val) > 30 else current_val
        tk.Label(
            top,
            text=val_text or "—",
            font=("Helvetica", 8),
            bg=COLORS['bg_dark'], fg=val_color,
            padx=6, pady=2,
        ).pack(side="left", padx=8)

        # ── Radio buttons ────────────────────────────────────────────────────
        radio_frame = tk.Frame(card, bg=COLORS['bg_medium'])
        radio_frame.pack(fill="x", padx=12, pady=(0, 6))

        valid_actions = ACTIONS if ftype != "exposure" else ["keep", "strip", "spoof"]
        for act in valid_actions:
            tk.Radiobutton(
                radio_frame,
                text=ACTION_LABELS[act],
                variable=action_var,
                value=act,
                command=lambda k=key, a=act: self._on_action_change(k, a),
                font=("Helvetica", 9),
                bg=COLORS['bg_medium'], fg=COLORS['text_white'],
                selectcolor=ACTION_COLORS[act],
                activebackground=COLORS['bg_medium'],
                indicatoron=0,
                padx=8, pady=3,
                relief="flat",
                cursor="hand2",
                bd=0, highlightthickness=0,
            ).pack(side="left", padx=3)

        # ── Custom input area (hidden by default) ────────────────────────────
        custom_frame = tk.Frame(card, bg=COLORS['bg_medium'])
        self._custom_frames[key] = custom_frame

        if ftype == "gps":
            self._build_gps_inputs(custom_frame, key)
        elif ftype in ("text", "datetime", "copyright"):
            self._build_text_input(custom_frame, custom_var,
                                   placeholder=self._get_current_value(key))

        if default == "custom":
            custom_frame.pack(fill="x", padx=12, pady=(0, 8))

    def _build_text_input(self, parent, var: tk.StringVar, placeholder: str = ""):
        tk.Label(
            parent,
            text="Custom value:",
            font=("Helvetica", 9),
            bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
        ).pack(side="left", padx=(0, 8))

        entry = tk.Entry(
            parent,
            textvariable=var,
            bg=COLORS['bg_dark'], fg="white",
            insertbackground="white",
            font=("Helvetica", 9),
            width=32,
        )
        entry.pack(side="left")
        if placeholder and not var.get():
            entry.insert(0, placeholder)

    def _build_gps_inputs(self, parent, key):
        """Two entries for lat / lon."""
        for lbl_text, var in [("Lat:", self._lat_var), ("Lon:", self._lon_var)]:
            tk.Label(
                parent, text=lbl_text,
                font=("Helvetica", 9),
                bg=COLORS['bg_medium'], fg=COLORS['text_gray'],
            ).pack(side="left", padx=(0, 4))

            tk.Entry(
                parent,
                textvariable=var,
                bg=COLORS['bg_dark'], fg="white",
                insertbackground="white",
                font=("Helvetica", 9),
                width=12,
            ).pack(side="left", padx=(0, 12))

        # Pre-fill with current GPS if available
        cur = self._current.get("gps")
        if cur and isinstance(cur, dict):
            self._lat_var.set(str(cur.get("lat", "")))
            self._lon_var.set(str(cur.get("lon", "")))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_current_value(self, key: str) -> str:
        v = self._current.get(key)
        if v is None:
            return ""
        if key == "gps" and isinstance(v, dict):
            return f"{v.get('lat', '')}, {v.get('lon', '')}"
        if key == "exposure" and isinstance(v, dict):
            return f"{v.get('shutter','?')}  {v.get('fnumber','?')}  ISO{v.get('iso','?')}"
        return str(v)

    def _on_action_change(self, key: str, action: str):
        frame = self._custom_frames.get(key)
        if frame is None:
            return
        if action == "custom":
            frame.pack(fill="x", padx=12, pady=(0, 8))
        else:
            frame.pack_forget()

    def _set_all(self, action: str):
        for key, var in self._action_vars.items():
            var.set(action)
            self._on_action_change(key, action)

    # ── Presets ───────────────────────────────────────────────────────────────

    def _get_current_actions(self) -> dict:
        """Read currently selected UI state into a dict."""
        result = {}
        for key, action_var in self._action_vars.items():
            action = action_var.get()
            if action == "custom":
                if key == "gps":
                    try:
                        result[key] = {"lat": float(self._lat_var.get()), "lon": float(self._lon_var.get())}
                    except ValueError:
                        result[key] = "spoof"
                else:
                    val = self._custom_vars[key].get().strip()
                    result[key] = {"value": val} if val else "spoof"
            else:
                result[key] = action
        return result

    def _load_actions_into_ui(self, actions: dict):
        """Update UI based on a field_actions dict."""
        for key, action_var in self._action_vars.items():
            act = actions.get(key, "keep")
            if isinstance(act, dict):
                action_var.set("custom")
                self._on_action_change(key, "custom")
                if key == "gps":
                    self._lat_var.set(str(act.get("lat", "")))
                    self._lon_var.set(str(act.get("lon", "")))
                else:
                    self._custom_vars[key].set(act.get("value", ""))
            else:
                action_var.set(act)
                self._on_action_change(key, act)

    def _on_preset_selected(self, event=None):
        name = self.preset_combo.get()
        if not name: return
        data = presets.load_preset(name)
        if data:
            self._load_actions_into_ui(data)
        
        # Disable delete for factory presets
        if presets.is_factory(name):
            self.del_preset_btn.config(state="disabled")
        else:
            self.del_preset_btn.config(state="normal")

    def _save_current_as_preset(self):
        name = simpledialog.askstring("Save Preset", "Enter a name for this preset:", parent=self.win)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if presets.is_factory(name):
            messagebox.showerror("Error", "Cannot overwrite a factory preset.", parent=self.win)
            return
        
        actions = self._get_current_actions()
        presets.save_preset(name, actions)
        
        # Refresh combo
        self.preset_combo['values'] = presets.all_preset_names()
        self.preset_combo.set(name)
        self.del_preset_btn.config(state="normal")
        messagebox.showinfo("Saved", f"Preset '{name}' saved successfully.", parent=self.win)

    def _delete_selected_preset(self):
        name = self.preset_combo.get()
        if not name or presets.is_factory(name):
            return
        if messagebox.askyesno("Delete Preset", f"Are you sure you want to delete '{name}'?", parent=self.win):
            if presets.delete_preset(name):
                self.preset_combo['values'] = presets.all_preset_names()
                self.preset_combo.set("")
                self.del_preset_btn.config(state="disabled")

    # ── Result ────────────────────────────────────────────────────────────────

    def _apply(self):
        self.result = self._get_current_actions()
        self.win.destroy()

    def _cancel(self):
        self.result = None
        self.win.destroy()
