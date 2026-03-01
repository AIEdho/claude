"""
Skool Video Downloader – core extraction and download logic.

Flow:
1. Fetch the Skool page using the user's session cookie
2. Parse the HTML to find embedded video URLs (Vimeo, YouTube, Wistia, direct mp4)
3. Use yt-dlp to download the video
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import load_settings
from app.jobs import complete_job, fail_job, update_job

logger = logging.getLogger("skool_downloader")

SKOOL_BASE = "https://www.skool.com"


def _build_session(cookie: str) -> requests.Session:
    """Create a requests session with Skool authentication."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    if cookie:
        session.headers["Cookie"] = cookie
    return session


def extract_video_urls(html: str, page_url: str = "") -> list:
    """
    Extract video embed URLs from Skool page HTML.

    Looks for:
    - Vimeo iframes / player embeds
    - YouTube iframes / embeds
    - Wistia embeds
    - Direct .mp4 links
    - HTML5 <video> source tags
    """
    soup = BeautifulSoup(html, "html.parser")
    videos = []

    # 1. iframe embeds (Vimeo, YouTube, Wistia, etc.)
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or iframe.get("data-src") or ""
        if not src:
            continue
        # Normalize protocol-relative URLs
        if src.startswith("//"):
            src = "https:" + src
        if any(host in src for host in [
            "player.vimeo.com", "vimeo.com",
            "youtube.com", "youtu.be", "youtube-nocookie.com",
            "wistia.com", "fast.wistia.net",
            "loom.com",
        ]):
            videos.append({"type": "iframe", "url": src})
        elif ".mp4" in src:
            videos.append({"type": "direct", "url": src})

    # 2. HTML5 <video> tags
    for video in soup.find_all("video"):
        src = video.get("src") or ""
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(page_url or SKOOL_BASE, src)
            videos.append({"type": "direct", "url": src})
        for source in video.find_all("source"):
            s = source.get("src") or ""
            if s:
                if s.startswith("//"):
                    s = "https:" + s
                elif s.startswith("/"):
                    s = urljoin(page_url or SKOOL_BASE, s)
                videos.append({"type": "direct", "url": s})

    # 3. Regex fallbacks for dynamically-loaded video URLs in scripts
    # Vimeo video IDs in scripts
    for match in re.findall(r'player\.vimeo\.com/video/(\d+)', html):
        url = f"https://player.vimeo.com/video/{match}"
        if not any(v["url"] == url for v in videos):
            videos.append({"type": "vimeo", "url": url})

    # YouTube video IDs in scripts
    for match in re.findall(r'(?:youtube\.com/embed/|youtu\.be/)([\w-]+)', html):
        url = f"https://www.youtube.com/watch?v={match}"
        if not any(match in v["url"] for v in videos):
            videos.append({"type": "youtube", "url": url})

    # Direct mp4 URLs in scripts or attributes
    for match in re.findall(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html):
        if not any(v["url"] == match for v in videos):
            videos.append({"type": "direct", "url": match})

    # Wistia video IDs
    for match in re.findall(r'wistia\.(?:com|net)/(?:medias|embed/iframe)/(\w+)', html):
        url = f"https://fast.wistia.net/embed/iframe/{match}"
        if not any(match in v["url"] for v in videos):
            videos.append({"type": "wistia", "url": url})

    return videos


def extract_page_title(html: str) -> str:
    """Extract the page title from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Try <title> tag
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()
        # Remove " - Skool" suffix if present
        title = re.sub(r'\s*[-|]\s*Skool\s*$', '', title)
        if title:
            return title
    # Try <h1> tag
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def _sanitize_filename(name: str) -> str:
    """Remove characters that aren't safe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:200] if name else "video"


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def fetch_skool_page(url: str, cookie: str) -> tuple:
    """
    Fetch a Skool page and return (html, title, video_urls).
    Raises on error.
    """
    session = _build_session(cookie)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    html = resp.text
    title = extract_page_title(html)
    video_urls = extract_video_urls(html, url)

    return html, title, video_urls


def download_video(job_id: str) -> None:
    """
    Download a video for the given job. Runs in a background thread.
    Uses yt-dlp for robust video downloading from various providers.
    """
    from app.jobs import get_job

    job = get_job(job_id)
    if not job:
        return

    settings = load_settings()

    try:
        update_job(job_id, {"status": "extracting", "progress_text": "Extracting video info..."})

        video_url = job.get("video_url", "")
        skool_url = job.get("url", "")
        cookie = settings.get("cookie", "")
        quality = settings.get("video_quality", "best")
        download_path = Path(settings["download_path"])
        download_path.mkdir(parents=True, exist_ok=True)

        # If we don't have a video URL yet, fetch the Skool page
        if not video_url:
            if not cookie:
                raise ValueError(
                    "No Skool cookie configured. Go to Settings and paste your "
                    "Skool session cookie to authenticate."
                )
            _html, title, found_videos = fetch_skool_page(skool_url, cookie)
            if not found_videos:
                raise ValueError(
                    "No video found on this page. Make sure the URL points to a "
                    "Skool lesson that contains a video, and that your cookie is valid."
                )
            video_url = found_videos[0]["url"]
            update_job(job_id, {
                "title": title or job["title"],
                "video_url": video_url,
            })
            # Refresh job data
            job = get_job(job_id)

        title = _sanitize_filename(job.get("title", "video"))
        template = settings.get("filename_template", "{title}")
        filename = template.replace("{title}", title)
        filename = _sanitize_filename(filename)

        # Build yt-dlp options
        import yt_dlp

        output_template = str(download_path / f"{filename}.%(ext)s")

        # Quality mapping
        format_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        if quality == "1080":
            format_spec = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
        elif quality == "720":
            format_spec = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        elif quality == "480":
            format_spec = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"

        # Progress hook
        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    pct = int((downloaded / total) * 100)
                    update_job(job_id, {
                        "status": "downloading",
                        "progress": pct,
                        "progress_text": f"Downloading: {pct}% ({_format_size(downloaded)} / {_format_size(total)})",
                        "file_size": _format_size(total),
                    })
                else:
                    update_job(job_id, {
                        "status": "downloading",
                        "progress_text": f"Downloading: {_format_size(downloaded)}",
                    })
            elif d["status"] == "finished":
                update_job(job_id, {
                    "progress": 95,
                    "progress_text": "Finalizing...",
                })

        ydl_opts = {
            "format": format_spec,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        # If cookie string is provided and the video is from Skool directly,
        # we may need to pass referer headers
        if cookie and "skool.com" in (skool_url or ""):
            ydl_opts["http_headers"] = {
                "Referer": skool_url,
                "Cookie": cookie,
            }

        update_job(job_id, {"status": "downloading", "progress_text": "Starting download..."})

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if info:
                # Get the actual output filename
                output_file = ydl.prepare_filename(info)
                # yt-dlp may change extension during merge
                if not Path(output_file).exists():
                    # Try with .mp4 extension
                    mp4_path = Path(output_file).with_suffix(".mp4")
                    if mp4_path.exists():
                        output_file = str(mp4_path)

                file_size = ""
                if Path(output_file).exists():
                    file_size = _format_size(Path(output_file).stat().st_size)

                # Update title from video info if we got a better one
                video_title = info.get("title", "")
                if video_title and job.get("title") == "Untitled":
                    update_job(job_id, {"title": _sanitize_filename(video_title)})

                complete_job(job_id, output_file, file_size)
                logger.info(f"[{job_id}] Download complete: {output_file}")
            else:
                raise RuntimeError("yt-dlp returned no info for this video")

    except Exception as e:
        logger.exception(f"[{job_id}] Download failed: {e}")
        fail_job(job_id, str(e))


def fetch_course_lessons(url: str, cookie: str) -> list:
    """
    Fetch a Skool course/classroom page and extract all lesson links.
    Returns a list of dicts: [{"title": ..., "url": ...}, ...]
    """
    session = _build_session(cookie)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    lessons = []

    # Look for lesson links - Skool uses various patterns
    # Common: links containing /classroom/ paths
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/classroom/" in href and href != url:
            full_url = href if href.startswith("http") else urljoin(SKOOL_BASE, href)
            title = link.get_text(strip=True) or "Untitled Lesson"
            # Avoid duplicates
            if not any(l["url"] == full_url for l in lessons):
                lessons.append({"title": title, "url": full_url})

    return lessons
