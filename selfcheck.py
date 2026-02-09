#!/usr/bin/env python3
"""
Image Factory – Self-Check Script.

Verifies that the app is set up correctly and all dependencies are available.
Run: python selfcheck.py
"""

import sys
import importlib

CHECKS = []
passed = 0
failed = 0


def check(name):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn
    return decorator


@check("Python version >= 3.10")
def check_python():
    v = sys.version_info
    assert v.major == 3 and v.minor >= 10, f"Got Python {v.major}.{v.minor}, need 3.10+"


@check("FastAPI installed")
def check_fastapi():
    import fastapi
    assert fastapi.__version__


@check("Uvicorn installed")
def check_uvicorn():
    import uvicorn


@check("Pillow (PIL) installed")
def check_pillow():
    from PIL import Image
    assert Image.LANCZOS


@check("Watchdog installed")
def check_watchdog():
    from watchdog.observers import Observer


@check("rembg installed (background removal)")
def check_rembg():
    try:
        from rembg import remove
    except ImportError:
        print("    WARNING: rembg not installed. Background removal will be unavailable.")
        print("    The app still works — just set Background Removal to 'Never' in Settings.")
        return "warn"


@check("App modules importable")
def check_app():
    from app.config import load_settings, ensure_folders
    from app.jobs import create_job, list_jobs
    from app.processor import process_job
    from app.watcher import FolderWatcher
    from app.main import app


@check("Settings load correctly")
def check_settings():
    from app.config import load_settings
    s = load_settings()
    assert "inbox_path" in s
    assert "presets" in s
    assert len(s["presets"]) >= 2


def run():
    global passed, failed
    print()
    print("  Image Factory – Self-Check")
    print("  " + "=" * 40)
    print()

    warnings = 0
    for name, fn in CHECKS:
        try:
            result = fn()
            if result == "warn":
                print(f"  [WARN] {name}")
                warnings += 1
            else:
                print(f"  [ OK ] {name}")
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}")
            print(f"         {e}")
            failed += 1

    print()
    print(f"  Results: {passed} passed, {failed} failed, {warnings} warnings")
    print()

    if failed == 0:
        print("  All checks passed! Run 'python run.py' to start the app.")
    else:
        print("  Some checks failed. Run './setup.sh' (or setup.bat on Windows) to fix.")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
