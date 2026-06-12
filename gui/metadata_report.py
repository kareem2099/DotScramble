"""
DotScramble — Metadata Save Report Dialog
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shows a quick summary of what metadata actions will be applied
before the user confirms the save operation.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.config import COLORS

# ── Human-readable summaries ──────────────────────────────────────────────────
_PROFILE_SUMMARY = {
    "ghost":  ("👻 Ghost Profile",  "Nokia 3310 · Antarctica GPS · Year 2000 timestamp"),
    "troll":  ("🌊 Troll Profile",  "Random vintage camera · Random ocean GPS · Recent-ish date"),
    "artist": ("🎨 Artist Profile", "Hides GPS & camera device · Keeps copyright field"),
    "custom": ("⚙️ Custom Profile", "Per-field rules (see details below)"),
}

_ACTION_ICONS = {
    "keep":  ("✅", "#4CAF50", "Kept as-is"),
    "strip": ("🗑", "#F44336", "Stripped / removed"),
    "spoof": ("🎲", "#2196F3", "Replaced with fake data"),
}

_FIELD_LABELS = {
    "gps":       "📍 GPS Location",
    "make":      "📷 Camera Make",
    "model":     "📷 Camera Model",
    "software":  "💻 Software",
    "datetime":  "🕐 Date / Time",
    "copyright": "©️  Copyright",
    "exposure":  "🔆 Exposure Data",
}


def _describe_action(key: str, action) -> tuple[str, str, str]:
    """Return (icon, color, description) for a field action."""
    if isinstance(action, dict):
        if key == "gps":
            lat = action.get("lat", "?")
            lon = action.get("lon", "?")
            return ("✏️", "#FF9800", f"Custom GPS: {lat}, {lon}")
        val = action.get("value", "")
        return ("✏️", "#FF9800", f"Custom value: '{val[:30]}'" if val else "Custom (empty → spoof)")
    return _ACTION_ICONS.get(action, ("❓", "#888", action))


class MetadataReportDialog:
    """
    Pre-save confirmation dialog.

    Returns:
        self.confirmed  True  → user clicked "Save"
                        False → user cancelled
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        *,
        mode: str,                        # "scrub" | "spoof" | "restore"
        profile: str | None = None,       # ghost / troll / artist / custom
        field_actions: dict | None = None,
        filename: str = "",
    ):
        self.confirmed = False

        self.win = tk.Toplevel(parent)
        self.win.title("DotScramble — Confirm Save")
        self.win.configure(bg=COLORS['bg_dark'])
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        # Center
        self.win.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = 500, 420
        self.win.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")

        self._build(mode, profile, field_actions, filename)
        self.win.wait_window()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self, mode, profile, field_actions, filename):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.win, bg=COLORS['bg_medium'], height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="📋  Metadata Summary",
                 font=("Helvetica", 14, "bold"),
                 bg=COLORS['bg_medium'], fg=COLORS['accent_cyan']
                 ).pack(side="left", padx=20, pady=15)

        if filename:
            short = filename if len(filename) <= 32 else "…" + filename[-29:]
            tk.Label(hdr, text=short,
                     font=("Helvetica", 8, "italic"),
                     bg=COLORS['bg_medium'], fg=COLORS['text_gray']
                     ).pack(side="right", padx=16)

        # ── Mode banner ───────────────────────────────────────────────────────
        if mode == "scrub":
            banner_text  = "🗑  All metadata will be STRIPPED"
            banner_color = "#F44336"
            banner_desc  = "GPS, camera model, timestamps and all other EXIF data will be permanently removed."
        elif mode == "restore":
            banner_text  = "✅  Original metadata will be PRESERVED"
            banner_color = "#4CAF50"
            banner_desc  = "The image's original EXIF data will be restored exactly as it was."
        else:   # spoof
            pname, pdesc = _PROFILE_SUMMARY.get(profile or "ghost", ("🎲 Spoof", ""))
            banner_text  = f"🎭  Metadata will be SPOOFED  ({pname})"
            banner_color = "#2196F3"
            banner_desc  = pdesc

        banner = tk.Frame(self.win, bg=banner_color)
        banner.pack(fill="x", padx=0, pady=0)

        tk.Label(banner, text=banner_text,
                 font=("Helvetica", 10, "bold"),
                 bg=banner_color, fg="white",
                 padx=20, pady=8
                 ).pack(anchor="w")

        tk.Label(banner, text=banner_desc,
                 font=("Helvetica", 8, "italic"),
                 bg=banner_color, fg="white",
                 padx=20, pady=(0, 8), wraplength=460, justify="left"
                 ).pack(anchor="w")

        # ── Per-field detail (only for spoof / custom) ────────────────────────
        if mode == "spoof" and field_actions:
            detail_frame = tk.Frame(self.win, bg=COLORS['bg_dark'])
            detail_frame.pack(fill="both", expand=True, padx=16, pady=(12, 4))

            tk.Label(detail_frame, text="Field-by-field actions:",
                     font=("Helvetica", 9, "bold"),
                     bg=COLORS['bg_dark'], fg=COLORS['text_gray']
                     ).pack(anchor="w", pady=(0, 6))

            for key, action in field_actions.items():
                label = _FIELD_LABELS.get(key, key)
                icon, color, desc = _describe_action(key, action)

                row = tk.Frame(detail_frame, bg=COLORS['bg_medium'])
                row.pack(fill="x", pady=2)

                tk.Label(row, text=f"  {label}",
                         font=("Helvetica", 9),
                         bg=COLORS['bg_medium'], fg=COLORS['text_white'],
                         width=24, anchor="w"
                         ).pack(side="left")

                tk.Label(row, text=f"{icon} {desc}",
                         font=("Helvetica", 9),
                         bg=color, fg="white",
                         padx=6, pady=2
                         ).pack(side="left", padx=6)

        elif mode == "scrub":
            # Simple list of what gets removed
            detail_frame = tk.Frame(self.win, bg=COLORS['bg_dark'])
            detail_frame.pack(fill="both", expand=True, padx=16, pady=(12, 4))

            items = ["📍 GPS coordinates", "📷 Camera make & model",
                     "💻 Software identifier", "🕐 Timestamps",
                     "©️  Copyright", "🔆 Exposure data", "🔒 Device fingerprint"]
            for item in items:
                tk.Label(detail_frame, text=f"  🗑  {item}",
                         font=("Helvetica", 9),
                         bg=COLORS['bg_dark'], fg="#ef9a9a",
                         anchor="w"
                         ).pack(anchor="w", pady=1)

        else:
            # restore or simple spoof without custom fields
            detail_frame = tk.Frame(self.win, bg=COLORS['bg_dark'])
            detail_frame.pack(fill="both", expand=True)
            if mode == "spoof" and profile in _PROFILE_SUMMARY:
                _, pdesc = _PROFILE_SUMMARY[profile]
                tk.Label(detail_frame, text=pdesc,
                         font=("Helvetica", 9, "italic"),
                         bg=COLORS['bg_dark'], fg=COLORS['text_gray'],
                         wraplength=460, justify="left"
                         ).pack(anchor="w", padx=16, pady=12)

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self.win, bg=COLORS['bg_medium'], height=55)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)

        tk.Button(btn_frame, text="Cancel",
                  font=("Helvetica", 10),
                  bg=COLORS['bg_light'], fg=COLORS['text_white'],
                  relief="flat", cursor="hand2", padx=20,
                  command=self._cancel
                  ).pack(side="right", padx=(8, 20), pady=10)

        tk.Button(btn_frame, text="💾  Save",
                  font=("Helvetica", 10, "bold"),
                  bg=COLORS['accent_cyan'], fg=COLORS['bg_dark'],
                  relief="flat", cursor="hand2", padx=24,
                  command=self._confirm
                  ).pack(side="right", padx=4, pady=10)

    def _confirm(self):
        self.confirmed = True
        self.win.destroy()

    def _cancel(self):
        self.confirmed = False
        self.win.destroy()
