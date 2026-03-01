"""
Configuration and settings management for Skool Video Downloader.
Settings are saved to a JSON file so they persist between sessions.
"""

import json
from pathlib import Path
from typing import Optional

_desktop = Path.home() / "Desktop"
if not _desktop.exists():
    _desktop = Path.home()
DEFAULT_BASE = _desktop / "SkoolDownloads"

SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

DEFAULTS = {
    "download_path": str(DEFAULT_BASE),
    "logs_path": str(DEFAULT_BASE / "LOGS"),
    "cookie": "",
    "video_quality": "best",  # "best" | "1080" | "720" | "480"
    "filename_template": "{title}",
    "concurrent_downloads": 1,
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
            pass
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
    """Create download and logs folders if they don't exist."""
    s = settings or load_settings()
    Path(s["download_path"]).mkdir(parents=True, exist_ok=True)
    Path(s["logs_path"]).mkdir(parents=True, exist_ok=True)
    (Path(s["logs_path"]) / "jobs").mkdir(parents=True, exist_ok=True)
