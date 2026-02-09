"""
Folder watcher for Image Factory.

Watches the INBOX folder for new PNG/JPG files and creates jobs automatically.
Dropbox-friendly: waits for file stability before processing.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from watchdog.observers import Observer

from app.config import load_settings

logger = logging.getLogger("image_factory")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Track files we've already processed or queued
_processed_files: Set[str] = set()
_lock = threading.Lock()


def mark_processed(filepath: str) -> None:
    with _lock:
        _processed_files.add(os.path.normpath(filepath))


def is_processed(filepath: str) -> bool:
    with _lock:
        return os.path.normpath(filepath) in _processed_files


def reset_processed() -> None:
    with _lock:
        _processed_files.clear()


def _should_ignore(filepath: str, settings: dict) -> bool:
    """Returns True if the file should be ignored (Dropbox temp files, hidden files, etc.)."""
    name = os.path.basename(filepath)
    # Hidden files
    if name.startswith("."):
        return True
    # Temp files
    if name.endswith(".tmp") or name.endswith(".crdownload") or name.endswith(".part"):
        return True
    # Dropbox conflict files
    if "(conflicted copy" in name.lower():
        return True
    # Trigger mode: only process files ending with _READY
    if settings.get("watcher_trigger_mode", False):
        stem = Path(filepath).stem
        if not stem.endswith("_READY"):
            return True
    return False


def _is_stable(filepath: str, wait_seconds: float = 4.0) -> bool:
    """
    Check if a file is stable (not being written to).
    Waits and checks size/mtime twice.
    """
    try:
        stat1 = os.stat(filepath)
        time.sleep(wait_seconds)
        if not os.path.exists(filepath):
            return False
        stat2 = os.stat(filepath)
        return stat1.st_size == stat2.st_size and stat1.st_mtime == stat2.st_mtime
    except OSError:
        return False


class InboxHandler(FileSystemEventHandler):
    """Handle new files appearing in the INBOX folder."""

    def __init__(self, on_new_file: Callable[[str], None]):
        super().__init__()
        self._on_new_file = on_new_file
        self._pending: Set[str] = set()
        self._pending_lock = threading.Lock()

    def _handle(self, filepath: str) -> None:
        """Process a potentially new file in a background thread."""
        filepath = os.path.normpath(filepath)

        # Quick checks
        ext = Path(filepath).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return

        if is_processed(filepath):
            return

        settings = load_settings()
        if _should_ignore(filepath, settings):
            return

        with self._pending_lock:
            if filepath in self._pending:
                return
            self._pending.add(filepath)

        def _check_and_process():
            try:
                stability_secs = settings.get("watcher_stability_seconds", 4)
                if not _is_stable(filepath, stability_secs):
                    logger.debug(f"File not stable yet, skipping: {filepath}")
                    return
                if is_processed(filepath):
                    return
                mark_processed(filepath)
                logger.info(f"Watcher detected stable file: {filepath}")
                self._on_new_file(filepath)
            finally:
                with self._pending_lock:
                    self._pending.discard(filepath)

        t = threading.Thread(target=_check_and_process, daemon=True)
        t.start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)


class FolderWatcher:
    """Manages the watchdog observer for the INBOX folder."""

    def __init__(self, on_new_file: Callable[[str], None]):
        self._on_new_file = on_new_file
        self._observer: Optional[Observer] = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        settings = load_settings()
        inbox = settings["inbox_path"]
        Path(inbox).mkdir(parents=True, exist_ok=True)

        handler = InboxHandler(self._on_new_file)
        self._observer = Observer()
        self._observer.schedule(handler, inbox, recursive=False)
        self._observer.start()
        self._running = True
        logger.info(f"Folder watcher started on: {inbox}")

    def stop(self) -> None:
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            self._running = False
            logger.info("Folder watcher stopped")

    def restart(self) -> None:
        self.stop()
        self.start()
