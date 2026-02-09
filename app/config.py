"""
Configuration and settings management for Image Factory.
Settings are saved to a JSON file so they persist between sessions.
"""

import json
import os
from pathlib import Path
from typing import Optional

# Default base directory: a folder called "ImageFactory" on the user's Desktop
_desktop = Path.home() / "Desktop"
if not _desktop.exists():
    _desktop = Path.home()
DEFAULT_BASE = _desktop / "ImageFactory"

SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

# ── Preset definitions ──────────────────────────────────────────────
DEFAULT_PRESETS = {
    "4500x5400_portrait": {
        "label": "Portrait 2:3 (4500×5400)",
        "width": 4500,
        "height": 5400,
    },
    "5000x5000_square": {
        "label": "Square 1:1 (5000×5000)",
        "width": 5000,
        "height": 5000,
    },
}

# ── Default settings ────────────────────────────────────────────────
DEFAULTS = {
    "inbox_path": str(DEFAULT_BASE / "INBOX"),
    "output_path": str(DEFAULT_BASE / "OUTPUT"),
    "archive_path": str(DEFAULT_BASE / "ARCHIVE"),
    "logs_path": str(DEFAULT_BASE / "LOGS"),
    "background_removal": "ask",  # "auto" | "ask" | "never"
    "upscale_quality": "fast",  # "fast" | "best"
    "export_jpg_preview": False,
    "fit_mode": "pad",  # "pad" | "crop"
    "pad_color": [255, 255, 255, 0],  # transparent by default
    "naming_template": "{date}_{original}_{preset}_v{version}",
    "presets": DEFAULT_PRESETS,
    "selected_preset": "4500x5400_portrait",
    "watcher_enabled": False,
    "watcher_stability_seconds": 4,
    "watcher_trigger_mode": False,  # only process *_READY.png / *_READY.jpg
    "api_port": 5555,
}


def load_settings() -> dict:
    """Load settings from disk, filling in any missing keys with defaults."""
    settings = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt file → use defaults
    return settings


def save_settings(settings: dict) -> None:
    """Persist settings to disk."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_settings() -> dict:
    return load_settings()


def update_settings(patch: dict) -> dict:
    """Merge *patch* into current settings, save, and return the result."""
    settings = load_settings()
    settings.update(patch)
    save_settings(settings)
    return settings


def ensure_folders(settings: Optional[dict] = None) -> None:
    """Create INBOX / OUTPUT / ARCHIVE / LOGS folders if they don't exist."""
    s = settings or load_settings()
    for key in ("inbox_path", "output_path", "archive_path", "logs_path"):
        Path(s[key]).mkdir(parents=True, exist_ok=True)
    # Also create the jobs log folder
    (Path(s["logs_path"]) / "jobs").mkdir(parents=True, exist_ok=True)
