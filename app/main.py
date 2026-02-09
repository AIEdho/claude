"""
Image Factory – FastAPI application.

Serves the web UI and provides the local HTTP API for OpenClaw integration.
"""

import logging
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    ensure_folders,
    get_settings,
    load_settings,
    save_settings,
    update_settings,
)
from app.jobs import (
    complete_job,
    create_job,
    fail_job,
    get_job,
    list_jobs,
    load_all_jobs,
    update_job,
)
from app.processor import process_job
from app.watcher import FolderWatcher, mark_processed

# ── Logging setup ───────────────────────────────────────────────────

logger = logging.getLogger("image_factory")


def setup_logging():
    settings = load_settings()
    logs_path = Path(settings["logs_path"])
    logs_path.mkdir(parents=True, exist_ok=True)
    log_file = logs_path / "app.log"

    handler = logging.FileHandler(str(log_file))
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    root = logging.getLogger("image_factory")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    root.addHandler(console)


# ── App init ────────────────────────────────────────────────────────

app = FastAPI(title="Image Factory", version="1.0.0")

# Serve static files (UI)
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


def _on_new_file(filepath: str):
    """Callback for the folder watcher when a new file appears."""
    logger.info(f"Auto-processing new file: {filepath}")
    settings = load_settings()
    job = create_job(
        input_path=filepath,
        background_mode=settings.get("background_removal", "ask"),
    )
    # If background_mode is "ask", we still queue it but mark it needs decision
    if job["background_mode"] == "ask":
        update_job(job["id"], {"needs_bg_decision": True, "status": "queued"})
    else:
        _run_job_async(job["id"])


watcher = FolderWatcher(on_new_file=_on_new_file)


@app.on_event("startup")
def startup():
    setup_logging()
    ensure_folders()
    load_all_jobs()
    logger.info("Image Factory started")
    # Start watcher if enabled in settings
    settings = load_settings()
    if settings.get("watcher_enabled", False):
        watcher.start()


@app.on_event("shutdown")
def shutdown():
    watcher.stop()
    logger.info("Image Factory stopped")


# ── Helper ──────────────────────────────────────────────────────────


def _run_job_async(job_id: str):
    """Run a job in a background thread."""
    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()


# ── UI route ────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    index = _static_dir / "index.html"
    return HTMLResponse(content=index.read_text(), status_code=200)


# ── API: Health ─────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Image Factory",
        "version": "1.0.0",
        "watcher_running": watcher.running,
    }


# ── API: Settings ───────────────────────────────────────────────────


@app.get("/settings")
def api_get_settings():
    return get_settings()


class SettingsPatch(BaseModel):
    inbox_path: Optional[str] = None
    output_path: Optional[str] = None
    archive_path: Optional[str] = None
    logs_path: Optional[str] = None
    background_removal: Optional[str] = None
    upscale_quality: Optional[str] = None
    export_jpg_preview: Optional[bool] = None
    fit_mode: Optional[str] = None
    naming_template: Optional[str] = None
    selected_preset: Optional[str] = None
    watcher_enabled: Optional[bool] = None
    watcher_stability_seconds: Optional[int] = None
    watcher_trigger_mode: Optional[bool] = None
    api_port: Optional[int] = None


@app.patch("/settings")
def api_update_settings(patch: SettingsPatch):
    data = {k: v for k, v in patch.dict().items() if v is not None}
    result = update_settings(data)
    ensure_folders(result)
    # Toggle watcher if needed
    if "watcher_enabled" in data:
        if data["watcher_enabled"]:
            watcher.restart()
        else:
            watcher.stop()
    return result


# ── API: Presets ────────────────────────────────────────────────────


class PresetCreate(BaseModel):
    key: str
    label: str
    width: int
    height: int


@app.get("/presets")
def api_list_presets():
    settings = load_settings()
    return settings.get("presets", {})


@app.post("/presets")
def api_create_preset(preset: PresetCreate):
    settings = load_settings()
    presets = settings.get("presets", {})
    presets[preset.key] = {
        "label": preset.label,
        "width": preset.width,
        "height": preset.height,
    }
    settings["presets"] = presets
    save_settings(settings)
    return presets


@app.delete("/presets/{key}")
def api_delete_preset(key: str):
    settings = load_settings()
    presets = settings.get("presets", {})
    if key in presets:
        del presets[key]
        settings["presets"] = presets
        save_settings(settings)
    return presets


# ── API: Jobs ───────────────────────────────────────────────────────


@app.get("/jobs")
def api_list_jobs():
    return list_jobs()


@app.get("/jobs/{job_id}")
def api_get_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


class ProcessRequest(BaseModel):
    file_path: str
    preset: Optional[str] = None
    background_mode: Optional[str] = None
    upscale_quality: Optional[str] = None
    export_jpg: Optional[bool] = None
    fit_mode: Optional[str] = None


@app.post("/process")
def api_process(req: ProcessRequest):
    """Create and start a processing job. Core API for OpenClaw integration."""
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=400, detail=f"File not found: {req.file_path}")

    ext = Path(req.file_path).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    job = create_job(
        input_path=req.file_path,
        preset=req.preset,
        background_mode=req.background_mode or "auto",
        upscale_quality=req.upscale_quality,
        export_jpg=req.export_jpg,
        fit_mode=req.fit_mode,
    )
    mark_processed(req.file_path)
    _run_job_async(job["id"])
    return {"job_id": job["id"], "status": job["status"]}


@app.post("/jobs/{job_id}/rerun")
def api_rerun_job(job_id: str):
    """Re-run a job (creates a new job with the same input)."""
    original = get_job(job_id)
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if the original input still exists (might be in archive)
    input_path = original["input_path"]
    if not Path(input_path).exists():
        # Try to find it in archive
        settings = load_settings()
        archive_base = Path(settings["archive_path"])
        found = None
        for archive_dir in archive_base.iterdir():
            candidate = archive_dir / original["original_filename"]
            if candidate.exists():
                found = str(candidate)
                break
        if not found:
            raise HTTPException(
                status_code=400,
                detail="Original file not found in INBOX or ARCHIVE",
            )
        input_path = found

    new_job = create_job(
        input_path=input_path,
        preset=original["preset"],
        background_mode=original["background_mode"],
        upscale_quality=original["upscale_quality"],
        export_jpg=original.get("export_jpg", False),
        fit_mode=original.get("fit_mode", "pad"),
    )
    _run_job_async(new_job["id"])
    return {"job_id": new_job["id"], "status": new_job["status"]}


class DuplicateRequest(BaseModel):
    preset: Optional[str] = None
    background_mode: Optional[str] = None
    upscale_quality: Optional[str] = None
    export_jpg: Optional[bool] = None
    fit_mode: Optional[str] = None


@app.post("/jobs/{job_id}/duplicate")
def api_duplicate_job(job_id: str, req: DuplicateRequest):
    """Duplicate a job with different settings."""
    original = get_job(job_id)
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")

    input_path = original["input_path"]
    if not Path(input_path).exists():
        settings = load_settings()
        archive_base = Path(settings["archive_path"])
        found = None
        for archive_dir in sorted(archive_base.iterdir(), reverse=True):
            candidate = archive_dir / original["original_filename"]
            if candidate.exists():
                found = str(candidate)
                break
        if not found:
            raise HTTPException(
                status_code=400,
                detail="Original file not found in INBOX or ARCHIVE",
            )
        input_path = found

    new_job = create_job(
        input_path=input_path,
        preset=req.preset or original["preset"],
        background_mode=req.background_mode or original["background_mode"],
        upscale_quality=req.upscale_quality or original["upscale_quality"],
        export_jpg=req.export_jpg if req.export_jpg is not None else original.get("export_jpg", False),
        fit_mode=req.fit_mode or original.get("fit_mode", "pad"),
    )
    _run_job_async(new_job["id"])
    return {"job_id": new_job["id"], "status": new_job["status"]}


@app.post("/jobs/{job_id}/decide-bg")
def api_decide_background(job_id: str, remove: bool = True):
    """When background_mode is 'ask', the user decides via this endpoint."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.get("needs_bg_decision"):
        raise HTTPException(status_code=400, detail="Job doesn't need a background decision")

    if remove:
        update_job(job_id, {"background_mode": "auto", "needs_bg_decision": False})
    else:
        update_job(job_id, {"background_mode": "never", "needs_bg_decision": False})

    _run_job_async(job_id)
    return {"job_id": job_id, "status": "processing", "background_removal": remove}


# ── API: Import file via upload ─────────────────────────────────────


@app.post("/import")
async def api_import_file(file: UploadFile = File(...)):
    """Import a file by uploading it to the INBOX."""
    settings = load_settings()
    inbox = Path(settings["inbox_path"])
    inbox.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    dest = inbox / file.filename
    # Don't overwrite
    if dest.exists():
        stem = dest.stem
        counter = 1
        while dest.exists():
            dest = inbox / f"{stem}_{counter}{ext}"
            counter += 1

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    job = create_job(input_path=str(dest))
    settings = load_settings()
    if job["background_mode"] == "ask":
        update_job(job["id"], {"needs_bg_decision": True})
    else:
        _run_job_async(job["id"])

    return {"job_id": job["id"], "status": job["status"], "file_saved": str(dest)}


# ── API: Watcher control ───────────────────────────────────────────


@app.post("/watcher/start")
def api_watcher_start():
    update_settings({"watcher_enabled": True})
    watcher.restart()
    return {"watcher_running": True}


@app.post("/watcher/stop")
def api_watcher_stop():
    update_settings({"watcher_enabled": False})
    watcher.stop()
    return {"watcher_running": False}


@app.get("/watcher/status")
def api_watcher_status():
    return {"watcher_running": watcher.running}
