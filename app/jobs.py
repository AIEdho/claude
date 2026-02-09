"""
Job management – create, update, query, and persist job records.

Every job gets a unique ID and is saved as a JSON file in LOGS/jobs/{id}.json.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import load_settings

# In-memory cache of jobs (also persisted to disk)
_jobs: Dict[str, dict] = {}


def _jobs_dir() -> Path:
    s = load_settings()
    d = Path(s["logs_path"]) / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_job(job: dict) -> None:
    """Write job JSON to disk."""
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


def create_job(
    input_path: str,
    preset: Optional[str] = None,
    background_mode: Optional[str] = None,
    upscale_quality: Optional[str] = None,
    export_jpg: Optional[bool] = None,
    fit_mode: Optional[str] = None,
) -> dict:
    """Create a new job record and return it."""
    settings = load_settings()
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "input_path": str(input_path),
        "original_filename": Path(input_path).name,
        "preset": preset or settings.get("selected_preset", "4500x5400_portrait"),
        "background_mode": background_mode or settings.get("background_removal", "ask"),
        "upscale_quality": upscale_quality or settings.get("upscale_quality", "fast"),
        "export_jpg": export_jpg if export_jpg is not None else settings.get("export_jpg_preview", False),
        "fit_mode": fit_mode or settings.get("fit_mode", "pad"),
        "status": "queued",  # queued → processing → done | failed
        "steps": {
            "detect": None,
            "background_removal": None,
            "edge_cleanup": None,
            "upscale": None,
            "resize": None,
            "export": None,
        },
        "has_transparency": None,
        "background_removal_skipped": False,
        "needs_bg_decision": False,
        "output_files": [],
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
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


def set_step(job_id: str, step: str, status: str) -> None:
    """Set a processing step's status: 'pending' | 'running' | 'done' | 'skipped' | 'failed'."""
    job = _jobs.get(job_id)
    if job:
        job["steps"][step] = status
        _save_job(job)


def fail_job(job_id: str, error_message: str) -> None:
    job = _jobs.get(job_id)
    if job:
        job["status"] = "failed"
        job["error"] = error_message
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)


def complete_job(job_id: str, output_files: List[str]) -> None:
    job = _jobs.get(job_id)
    if job:
        job["status"] = "done"
        job["output_files"] = output_files
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)
