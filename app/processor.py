"""
Image processing pipeline for Image Factory.

Steps: detect → background_removal → edge_cleanup → upscale → resize → export
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageFilter, ImageOps

from app.config import load_settings
from app.jobs import (
    complete_job,
    fail_job,
    get_job,
    set_step,
    update_job,
)

logger = logging.getLogger("image_factory")

# ── rembg lazy import (heavy dependency) ────────────────────────────
_rembg_session = None


def _get_rembg():
    """Lazy-load rembg to avoid slow startup."""
    global _rembg_session
    try:
        from rembg import remove, new_session

        if _rembg_session is None:
            _rembg_session = new_session("u2net")
        return remove, _rembg_session
    except ImportError:
        return None, None


# ── Helpers ─────────────────────────────────────────────────────────


def _has_transparency(img: Image.Image) -> bool:
    """Check if an image actually uses transparency."""
    if img.mode != "RGBA":
        return False
    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    # If minimum alpha < 255, there are transparent pixels
    return extrema[0] < 250


def _output_filename(
    original_name: str,
    preset_key: str,
    ext: str,
    output_dir: Path,
    template: str,
) -> Path:
    """Generate a unique filename that never overwrites existing files."""
    stem = Path(original_name).stem
    date_str = datetime.now().strftime("%Y%m%d")
    version = 1
    while True:
        name = (
            template.replace("{date}", date_str)
            .replace("{original}", stem)
            .replace("{preset}", preset_key)
            .replace("{version}", str(version))
            .replace("{v#}", str(version))
        )
        candidate = output_dir / f"{name}{ext}"
        if not candidate.exists():
            return candidate
        version += 1
        if version > 9999:
            raise RuntimeError("Too many versions — something is wrong")


# ── Edge cleanup ────────────────────────────────────────────────────


def _edge_cleanup(img: Image.Image) -> Image.Image:
    """
    Reduce white/black halos around transparency edges.
    Works by slightly contracting the alpha mask and blurring the edge.
    """
    if img.mode != "RGBA":
        return img

    r, g, b, a = img.split()

    # Erode the alpha slightly to remove halo fringe
    # Use MinFilter to shrink the alpha by ~1px
    a_eroded = a.filter(ImageFilter.MinFilter(3))

    # Smooth the alpha edge for softer cutout
    a_smooth = a_eroded.filter(ImageFilter.GaussianBlur(radius=0.8))

    # Recombine
    result = Image.merge("RGBA", (r, g, b, a_smooth))
    return result


# ── Upscale ─────────────────────────────────────────────────────────


def _upscale(img: Image.Image, target_w: int, target_h: int, quality: str) -> Image.Image:
    """
    Upscale image to at least target dimensions while preserving aspect ratio.
    'fast' uses LANCZOS, 'best' uses LANCZOS + sharpen pass.
    """
    w, h = img.size
    # Calculate scale needed to cover the target
    scale_w = target_w / w if w < target_w else 1
    scale_h = target_h / h if h < target_h else 1
    scale = max(scale_w, scale_h)

    if scale <= 1:
        # Already large enough
        return img

    new_w = int(w * scale)
    new_h = int(h * scale)

    resampled = img.resize((new_w, new_h), Image.LANCZOS)

    if quality == "best":
        # Multi-pass sharpen for cleaner upscale
        resampled = resampled.filter(ImageFilter.UnsharpMask(radius=1.5, percent=50, threshold=2))

    return resampled


# ── Resize / crop / pad ────────────────────────────────────────────


def _resize_to_preset(
    img: Image.Image, target_w: int, target_h: int, fit_mode: str, pad_color: list
) -> Image.Image:
    """Resize image to exact target dimensions using pad or crop."""
    if fit_mode == "crop":
        # Crop to fill: resize so image covers target, then center-crop
        w, h = img.size
        ratio_w = target_w / w
        ratio_h = target_h / h
        scale = max(ratio_w, ratio_h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
    else:
        # Pad to fit: resize to fit within target, then pad
        img.thumbnail((target_w, target_h), Image.LANCZOS)
        # Create canvas
        if img.mode == "RGBA":
            canvas = Image.new("RGBA", (target_w, target_h), tuple(pad_color))
        else:
            canvas = Image.new("RGB", (target_w, target_h), tuple(pad_color[:3]))
        # Center paste
        x = (target_w - img.width) // 2
        y = (target_h - img.height) // 2
        canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)
        img = canvas

    return img


# ── Main pipeline ──────────────────────────────────────────────────


def process_job(job_id: str) -> None:
    """
    Run the full processing pipeline for a job.
    This is meant to be called in a background thread.
    """
    job = get_job(job_id)
    if not job:
        return

    settings = load_settings()
    presets = settings.get("presets", {})

    try:
        update_job(job_id, {
            "status": "processing",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        input_path = Path(job["input_path"])
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        preset_key = job["preset"]
        preset = presets.get(preset_key)
        if not preset:
            raise ValueError(f"Unknown preset: {preset_key}")

        target_w = preset["width"]
        target_h = preset["height"]
        fit_mode = job.get("fit_mode", settings.get("fit_mode", "pad"))
        pad_color = settings.get("pad_color", [255, 255, 255, 0])
        bg_mode = job["background_mode"]
        upscale_q = job["upscale_quality"]
        export_jpg = job.get("export_jpg", False)
        naming = settings.get("naming_template", "{date}_{original}_{preset}_v{version}")

        # ── Step 1: Detect ──────────────────────────────────────
        set_step(job_id, "detect", "running")
        img = Image.open(input_path)
        original_format = img.format  # PNG or JPEG
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        transparency = _has_transparency(img)
        update_job(job_id, {"has_transparency": transparency})
        set_step(job_id, "detect", "done")
        logger.info(f"[{job_id}] Detected format={original_format}, transparency={transparency}")

        # ── Step 2: Background removal ──────────────────────────
        if bg_mode == "never" or (transparency and bg_mode != "auto"):
            set_step(job_id, "background_removal", "skipped")
            update_job(job_id, {"background_removal_skipped": True})
            logger.info(f"[{job_id}] Background removal skipped")
        elif bg_mode == "ask":
            # Mark that we need a user decision — the UI will handle this
            set_step(job_id, "background_removal", "skipped")
            update_job(job_id, {"background_removal_skipped": True})
            logger.info(f"[{job_id}] Background removal set to 'ask' — skipping (user can re-run)")
        else:
            # bg_mode == "auto" or explicitly requested
            set_step(job_id, "background_removal", "running")
            remove_fn, session = _get_rembg()
            if remove_fn is None:
                set_step(job_id, "background_removal", "skipped")
                update_job(job_id, {"background_removal_skipped": True})
                logger.warning(f"[{job_id}] rembg not available — skipping background removal")
            else:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img = remove_fn(img, session=session)
                set_step(job_id, "background_removal", "done")
                logger.info(f"[{job_id}] Background removed")

        # ── Step 3: Edge cleanup ────────────────────────────────
        if img.mode == "RGBA" and _has_transparency(img):
            set_step(job_id, "edge_cleanup", "running")
            img = _edge_cleanup(img)
            set_step(job_id, "edge_cleanup", "done")
            logger.info(f"[{job_id}] Edge cleanup done")
        else:
            set_step(job_id, "edge_cleanup", "skipped")

        # ── Step 4: Upscale ─────────────────────────────────────
        set_step(job_id, "upscale", "running")
        img = _upscale(img, target_w, target_h, upscale_q)
        set_step(job_id, "upscale", "done")
        logger.info(f"[{job_id}] Upscaled to {img.size}")

        # ── Step 5: Resize to preset ────────────────────────────
        set_step(job_id, "resize", "running")
        img = _resize_to_preset(img, target_w, target_h, fit_mode, pad_color)
        set_step(job_id, "resize", "done")
        logger.info(f"[{job_id}] Resized to {target_w}x{target_h} ({fit_mode})")

        # ── Step 6: Export ──────────────────────────────────────
        set_step(job_id, "export", "running")
        output_dir = Path(settings["output_path"]) / preset_key
        output_dir.mkdir(parents=True, exist_ok=True)

        outputs: List[str] = []

        # PNG (always)
        png_path = _output_filename(
            job["original_filename"], preset_key, ".png", output_dir, naming
        )
        # Ensure RGBA for PNG
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(str(png_path), "PNG", optimize=True)
        outputs.append(str(png_path))
        logger.info(f"[{job_id}] Saved PNG: {png_path}")

        # JPG preview (optional)
        if export_jpg:
            jpg_path = _output_filename(
                job["original_filename"], preset_key, ".jpg", output_dir, naming
            )
            rgb_img = img.convert("RGB")
            rgb_img.save(str(jpg_path), "JPEG", quality=90)
            outputs.append(str(jpg_path))
            logger.info(f"[{job_id}] Saved JPG: {jpg_path}")

        set_step(job_id, "export", "done")

        # ── Archive original ────────────────────────────────────
        archive_dir = Path(settings["archive_path"]) / datetime.now().strftime("%Y-%m-%d")
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_dest = archive_dir / input_path.name
        # Don't overwrite in archive either
        if archive_dest.exists():
            stem = archive_dest.stem
            ext = archive_dest.suffix
            counter = 1
            while archive_dest.exists():
                archive_dest = archive_dir / f"{stem}_{counter}{ext}"
                counter += 1
        shutil.move(str(input_path), str(archive_dest))
        logger.info(f"[{job_id}] Archived original to {archive_dest}")

        complete_job(job_id, outputs)
        logger.info(f"[{job_id}] Job completed successfully")

    except Exception as e:
        logger.exception(f"[{job_id}] Job failed: {e}")
        fail_job(job_id, str(e))
