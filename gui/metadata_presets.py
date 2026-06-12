"""
DotScramble — Metadata Preset Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Saves and loads named metadata field-action presets to/from disk.
Stored in: ~/.local/share/DotScramble/presets/metadata_presets.json
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# ── Storage path ──────────────────────────────────────────────────────────────
try:
    from src.config import DIRS
    _PRESET_FILE = Path(DIRS['presets']) / "metadata_presets.json"
except Exception:
    _PRESET_FILE = Path.home() / ".local/share/DotScramble/presets/metadata_presets.json"
    _PRESET_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Built-in factory presets (always available, read-only) ────────────────────
FACTORY_PRESETS: dict[str, dict] = {
    "🔇 Strip Everything": {
        "gps": "strip", "make": "strip", "model": "strip",
        "software": "strip", "datetime": "strip",
        "copyright": "strip", "exposure": "strip",
    },
    "📍 Strip GPS Only": {
        "gps": "strip", "make": "keep", "model": "keep",
        "software": "keep", "datetime": "keep",
        "copyright": "keep", "exposure": "keep",
    },
    "📷 Strip Camera + GPS": {
        "gps": "strip", "make": "strip", "model": "strip",
        "software": "strip", "datetime": "keep",
        "copyright": "keep", "exposure": "strip",
    },
    "🎨 Photographer (keep ©)": {
        "gps": "strip", "make": "spoof", "model": "spoof",
        "software": "strip", "datetime": "spoof",
        "copyright": "keep", "exposure": "keep",
    },
    "🎲 Spoof Everything": {
        "gps": "spoof", "make": "spoof", "model": "spoof",
        "software": "spoof", "datetime": "spoof",
        "copyright": "strip", "exposure": "spoof",
    },
}


def _load_file() -> dict:
    """Load user presets from disk (returns {} on error)."""
    try:
        if _PRESET_FILE.exists():
            return json.loads(_PRESET_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_file(data: dict) -> None:
    """Persist user presets to disk."""
    _PRESET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PRESET_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def all_preset_names() -> list[str]:
    """Return factory preset names first, then user preset names."""
    user = list(_load_file().keys())
    return list(FACTORY_PRESETS.keys()) + user


def load_preset(name: str) -> dict | None:
    """Return the field_actions dict for a preset name, or None."""
    if name in FACTORY_PRESETS:
        return dict(FACTORY_PRESETS[name])
    user = _load_file()
    return dict(user[name]) if name in user else None


def save_preset(name: str, field_actions: dict) -> None:
    """Save a user preset (overwrites if name exists)."""
    data = _load_file()
    data[name] = field_actions
    _save_file(data)


def delete_preset(name: str) -> bool:
    """Delete a user preset. Returns True if deleted, False if not found or factory."""
    if name in FACTORY_PRESETS:
        return False   # factory presets are immutable
    data = _load_file()
    if name in data:
        del data[name]
        _save_file(data)
        return True
    return False


def is_factory(name: str) -> bool:
    return name in FACTORY_PRESETS
