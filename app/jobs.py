"""
Job management for Skool Video Downloader.

Every download job gets a unique ID and is saved as JSON in LOGS/jobs/{id}.json.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.config import load_settings

_jobs: Dict[str, dict] = {}


def _jobs_dir() -> Path:
    s = load_settings()
    d = Path(s["logs_path"]) / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_job(job: dict) -> None:
    path = _jobs_dir() / f"{job['id']}.json"
    with open(path, "w") as f:
        json.dump(job, f, indent=2, default=str)


def load_all_jobs() -> None:
    """Load every job file from disk into memory (called at startup)."""
    _jobs.clear()
    d = _jobs_dir()
    for p in sorted(d.glob("*.json")):
        try:
            with open(p) as f:
                job = json.load(f)
            _jobs[job["id"]] = job
        except (json.JSONDecodeError, KeyError):
            pass


def create_job(url: str, title: str = "", video_url: str = "") -> dict:
    """Create a new download job record."""
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "url": url,
        "title": title or "Untitled",
        "video_url": video_url,
        "status": "queued",  # queued -> extracting -> downloading -> done | failed
        "progress": 0,
        "progress_text": "",
        "file_size": "",
        "output_path": "",
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _jobs[job_id] = job
    _save_job(job)
    return job


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def list_jobs() -> List[dict]:
    return list(reversed(sorted(_jobs.values(), key=lambda j: j["created_at"])))


def update_job(job_id: str, patch: dict) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    job.update(patch)
    _save_job(job)
    return job


def fail_job(job_id: str, error_message: str) -> None:
    job = _jobs.get(job_id)
    if job:
        job["status"] = "failed"
        job["error"] = error_message
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)


def complete_job(job_id: str, output_path: str, file_size: str = "") -> None:
    job = _jobs.get(job_id)
    if job:
        job["status"] = "done"
        job["progress"] = 100
        job["output_path"] = output_path
        job["file_size"] = file_size
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)


def delete_job(job_id: str) -> bool:
    job = _jobs.pop(job_id, None)
    if job:
        path = _jobs_dir() / f"{job_id}.json"
        path.unlink(missing_ok=True)
        return True
    return False
