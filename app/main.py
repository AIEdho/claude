"""
Skool Video Downloader – FastAPI application.

Serves the web UI and provides the HTTP API for downloading videos.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.browser_cookies import extract_skool_cookie
from app.config import ensure_folders, get_settings, load_settings, update_settings
from app.jobs import (
    complete_job,
    create_job,
    delete_job,
    fail_job,
    get_job,
    list_jobs,
    load_all_jobs,
    update_job,
)
from app.downloader import download_video, fetch_skool_page, fetch_course_lessons

# ── Logging ────────────────────────────────────────────────────────

logger = logging.getLogger("skool_downloader")


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

    root = logging.getLogger("skool_downloader")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    root.addHandler(console)


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(title="Skool Video Downloader", version="1.0.0")

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.on_event("startup")
def startup():
    setup_logging()
    ensure_folders()
    load_all_jobs()
    logger.info("Skool Video Downloader started")


# ── UI ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    index = _static_dir / "index.html"
    return HTMLResponse(content=index.read_text(), status_code=200)


# ── API: Health ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "app": "Skool Video Downloader", "version": "1.0.0"}


# ── API: Settings ──────────────────────────────────────────────────

@app.get("/settings")
def api_get_settings():
    s = get_settings()
    # Mask the cookie in the response (show first/last 4 chars)
    cookie = s.get("cookie", "")
    if len(cookie) > 12:
        s["cookie_display"] = cookie[:4] + "..." + cookie[-4:]
    elif cookie:
        s["cookie_display"] = "***"
    else:
        s["cookie_display"] = ""
    return s


class SettingsPatch(BaseModel):
    download_path: Optional[str] = None
    cookie: Optional[str] = None
    video_quality: Optional[str] = None
    filename_template: Optional[str] = None
    concurrent_downloads: Optional[int] = None


@app.patch("/settings")
def api_update_settings(patch: SettingsPatch):
    data = {k: v for k, v in patch.dict().items() if v is not None}
    result = update_settings(data)
    ensure_folders(result)
    return result


@app.post("/settings/auto-cookie")
def api_auto_cookie():
    """Extract Skool cookie from the user's browser automatically."""
    result = extract_skool_cookie()
    if result["cookie"]:
        # Save the cookie to settings
        update_settings({"cookie": result["cookie"]})
        cookie = result["cookie"]
        if len(cookie) > 12:
            display = cookie[:4] + "..." + cookie[-4:]
        else:
            display = "***"
        return {
            "success": True,
            "browser": result["browser"],
            "cookie_display": display,
        }
    else:
        return {
            "success": False,
            "error": result["error"],
        }


# ── API: Jobs ──────────────────────────────────────────────────────

@app.get("/jobs")
def api_list_jobs():
    return list_jobs()


@app.get("/jobs/{job_id}")
def api_get_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/jobs/{job_id}")
def api_delete_job(job_id: str):
    if not delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


# ── API: Download ──────────────────────────────────────────────────

class DownloadRequest(BaseModel):
    url: str
    title: Optional[str] = None


@app.post("/download")
def api_download(req: DownloadRequest):
    """Start a video download from a Skool URL or direct video URL."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    job = create_job(url=url, title=req.title or "")
    _run_download_async(job["id"])
    return {"job_id": job["id"], "status": job["status"]}


class BatchDownloadRequest(BaseModel):
    urls: list


@app.post("/download/batch")
def api_batch_download(req: BatchDownloadRequest):
    """Start multiple downloads at once."""
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    job_ids = []
    for item in req.urls:
        url = item.get("url", "") if isinstance(item, dict) else str(item)
        title = item.get("title", "") if isinstance(item, dict) else ""
        url = url.strip()
        if not url:
            continue
        job = create_job(url=url, title=title)
        _run_download_async(job["id"])
        job_ids.append(job["id"])

    return {"job_ids": job_ids, "count": len(job_ids)}


@app.post("/extract")
def api_extract(req: DownloadRequest):
    """
    Extract video info from a Skool URL without downloading.
    Returns the page title and found video URLs.
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    settings = load_settings()
    cookie = settings.get("cookie", "")

    try:
        html, title, videos = fetch_skool_page(url, cookie)
        return {"title": title, "videos": videos, "url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/extract/course")
def api_extract_course(req: DownloadRequest):
    """Extract all lesson links from a Skool course page."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    settings = load_settings()
    cookie = settings.get("cookie", "")

    if not cookie:
        raise HTTPException(
            status_code=400,
            detail="Skool cookie required. Go to Settings to configure."
        )

    try:
        lessons = fetch_course_lessons(url, cookie)
        return {"lessons": lessons, "count": len(lessons)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Helper ─────────────────────────────────────────────────────────

def _run_download_async(job_id: str):
    t = threading.Thread(target=download_video, args=(job_id,), daemon=True)
    t.start()
