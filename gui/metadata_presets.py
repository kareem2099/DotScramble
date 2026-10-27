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
from dataclasses import dataclass
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
# Keyed by a stable id; the shown name is translated (metadata.presets.<id>).
# Factory presets are never written to disk, so ids can't clash with saved data.
FACTORY_PRESETS: dict[str, dict] = {
    "strip_all": {
        "gps": "strip", "make": "strip", "model": "strip",
        "software": "strip", "datetime": "strip",
        "copyright": "strip", "exposure": "strip",
    },
    "strip_gps": {
        "gps": "strip", "make": "keep", "model": "keep",
        "software": "keep", "datetime": "keep",
        "copyright": "keep", "exposure": "keep",
    },
    "strip_camera_gps": {
        "gps": "strip", "make": "strip", "model": "strip",
        "software": "strip", "datetime": "keep",
        "copyright": "keep", "exposure": "strip",
    },
    "photographer": {
        "gps": "strip", "make": "spoof", "model": "spoof",
        "software": "strip", "datetime": "spoof",
        "copyright": "keep", "exposure": "keep",
    },
    "spoof_all": {
        "gps": "spoof", "make": "spoof", "model": "spoof",
        "software": "spoof", "datetime": "spoof",
        "copyright": "strip", "exposure": "spoof",
    },
}


@dataclass(frozen=True)
class Preset:
    key: str        # factory id, or the user's preset name (as stored on disk)
    label: str      # what the combo box shows
    factory: bool


def _factory_label(preset_id: str, language: str | None = None) -> str:
    from src.managers.localization_manager import get_locale_manager
    manager = get_locale_manager()
    if language is None:
        return manager.get(f"metadata.presets.{preset_id}")
    table = manager.translations.get(language, {})
    return table.get("metadata", {}).get("presets", {}).get(preset_id, preset_id)


def _load_file() -> dict:
    """Load user presets from disk (returns {} on error). Format: {name: field_actions}."""
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

def list_presets() -> list[Preset]:
    """Factory presets first (translated), then the user's saved presets."""
    factory = [Preset(pid, _factory_label(pid), True) for pid in FACTORY_PRESETS]
    user = [Preset(name, name, False) for name in _load_file()]
    return factory + user


def load_preset(preset: Preset) -> dict | None:
    """Return the field_actions dict for a preset, or None."""
    if preset.factory:
        actions = FACTORY_PRESETS.get(preset.key)
    else:
        actions = _load_file().get(preset.key)
    return dict(actions) if actions is not None else None


def save_preset(name: str, field_actions: dict) -> None:
    """Save a user preset (overwrites if name exists)."""
    data = _load_file()
    data[name] = field_actions
    _save_file(data)


def delete_preset(name: str) -> bool:
    """Delete a user preset. Returns True if deleted, False if not found."""
    data = _load_file()
    if name in data:
        del data[name]
        _save_file(data)
        return True
    return False


def is_reserved_name(name: str) -> bool:
    """
    True if `name` reads like a built-in preset in any language, so a user
    preset can't masquerade as (or be confused with) a factory one.
    """
    from src.managers.localization_manager import get_locale_manager
    languages = list(get_locale_manager().translations)
    folded = name.strip().casefold()
    for pid in FACTORY_PRESETS:
        labels = {pid} | {_factory_label(pid, lang) for lang in languages}
        if folded in {label.strip().casefold() for label in labels}:
            return True
    return False
