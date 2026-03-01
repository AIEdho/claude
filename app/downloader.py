"""
Skool Video Downloader – core extraction and download logic.

Flow:
1. Fetch the Skool page using the user's session cookie
2. Parse the HTML to find embedded video URLs (Vimeo, YouTube, Wistia, direct mp4)
   - Also extracts from Skool's embedded JSON data (__NEXT_DATA__, inline JSON)
3. Use yt-dlp to download the video
"""

import json
import logging
import os
import re
import signal
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import load_settings
from app.jobs import complete_job, fail_job, update_job

logger = logging.getLogger("skool_downloader")

SKOOL_BASE = "https://www.skool.com"

# Timeout for yt-dlp operations (5 minutes)
YT_DLP_TIMEOUT = 300


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


def _extract_from_next_data(html: str) -> list:
    """
    Extract video URLs from Next.js __NEXT_DATA__ JSON embedded in the page.
    Skool is a Next.js app, so lesson content is often in this script tag.
    """
    videos = []
    match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return videos

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return videos

    # Recursively search the JSON for video URLs
    _find_videos_in_json(data, videos)
    return videos


def _find_videos_in_json(obj, videos: list, depth: int = 0) -> None:
    """Recursively walk a JSON object looking for video URLs."""
    if depth > 20:
        return

    if isinstance(obj, str):
        # Check if this string is a video URL
        if any(host in obj for host in [
            "player.vimeo.com", "vimeo.com/video",
            "youtube.com/embed", "youtube.com/watch", "youtu.be/",
            "wistia.com", "fast.wistia.net",
            "loom.com/share", "loom.com/embed",
        ]):
            url = obj
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http") and not any(v["url"] == url for v in videos):
                videos.append({"type": "json_embed", "url": url})
        elif obj.endswith(".mp4") or ".mp4?" in obj:
            if obj.startswith("http") and not any(v["url"] == obj for v in videos):
                videos.append({"type": "direct", "url": obj})

    elif isinstance(obj, dict):
        for value in obj.values():
            _find_videos_in_json(value, videos, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _find_videos_in_json(item, videos, depth + 1)


def _extract_from_inline_json(html: str) -> list:
    """
    Extract video URLs from inline JSON/JavaScript in the page.
    Looks for JSON objects containing video-related keys.
    """
    videos = []

    # Look for JSON-like structures with video URLs in script tags
    # Pattern: {"videoUrl":"..."} or {"video_url":"..."} or {"src":"...vimeo..."}
    for pattern in [
        r'"(?:videoUrl|video_url|videoSrc|video_src|embedUrl|embed_url)"\s*:\s*"(https?://[^"]+)"',
        r'"(?:url|src|source)"\s*:\s*"(https?://(?:player\.vimeo\.com|(?:www\.)?youtube\.com|youtu\.be|fast\.wistia\.net|(?:www\.)?loom\.com)[^"]+)"',
    ]:
        for match in re.findall(pattern, html):
            url = match.replace("\\/", "/")  # Unescape JSON forward slashes
            if not any(v["url"] == url for v in videos):
                vtype = "vimeo" if "vimeo" in url else "youtube" if "youtube" in url or "youtu.be" in url else "direct"
                videos.append({"type": vtype, "url": url})

    return videos


def extract_video_urls(html: str, page_url: str = "") -> list:
    """
    Extract video embed URLs from Skool page HTML.

    Looks for:
    - Next.js __NEXT_DATA__ embedded JSON (most reliable for Skool)
    - Inline JSON/JavaScript video references
    - Vimeo iframes / player embeds
    - YouTube iframes / embeds
    - Wistia embeds
    - Direct .mp4 links
    - HTML5 <video> source tags
    """
    soup = BeautifulSoup(html, "html.parser")
    videos = []

    # 0. Try Next.js embedded JSON first (most reliable for Skool SPA pages)
    json_videos = _extract_from_next_data(html)
    videos.extend(json_videos)
    if json_videos:
        logger.info("Found %d video(s) in __NEXT_DATA__", len(json_videos))

    # 0b. Try inline JSON patterns
    inline_videos = _extract_from_inline_json(html)
    for v in inline_videos:
        if not any(existing["url"] == v["url"] for existing in videos):
            videos.append(v)

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
            if not any(v["url"] == src for v in videos):
                videos.append({"type": "iframe", "url": src})
        elif ".mp4" in src:
            if not any(v["url"] == src for v in videos):
                videos.append({"type": "direct", "url": src})

    # 2. HTML5 <video> tags
    for video in soup.find_all("video"):
        src = video.get("src") or ""
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(page_url or SKOOL_BASE, src)
            if not any(v["url"] == src for v in videos):
                videos.append({"type": "direct", "url": src})
        for source in video.find_all("source"):
            s = source.get("src") or ""
            if s:
                if s.startswith("//"):
                    s = "https:" + s
                elif s.startswith("/"):
                    s = urljoin(page_url or SKOOL_BASE, s)
                if not any(v["url"] == s for v in videos):
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

    logger.info("Total videos found: %d (page: %s)", len(videos), page_url)
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
    logger.info("Fetching Skool page: %s", url)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    html = resp.text
    logger.debug("Page HTML length: %d chars", len(html))

    # Log a warning if we got a login redirect or empty page
    if len(html) < 500:
        logger.warning("Page HTML is very short (%d chars) – cookie may be invalid", len(html))
    if "sign-in" in html.lower() or "login" in html.lower():
        logger.warning("Page appears to be a login page – cookie may be expired")

    title = extract_page_title(html)
    video_urls = extract_video_urls(html, url)

    return html, title, video_urls


def download_video(job_id: str) -> None:
    """
    Download a video for the given job. Runs in a background thread.
    Uses yt-dlp for robust video downloading from various providers.

    This function catches ALL exceptions (including BaseException) to ensure
    the job status is always updated, even if the thread is interrupted.
    """
    from app.jobs import get_job

    job = get_job(job_id)
    if not job:
        logger.error("[%s] Job not found, cannot download", job_id)
        return

    settings = load_settings()

    try:
        update_job(job_id, {"status": "extracting", "progress_text": "Extracting video info..."})
        logger.info("[%s] Starting download for URL: %s", job_id, job.get("url", ""))

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
                    "Skool session cookie, or use Auto-detect to grab it from your browser."
                )

            _html, title, found_videos = fetch_skool_page(skool_url, cookie)

            if not found_videos:
                # Provide more helpful error message
                html_len = len(_html) if _html else 0
                raise ValueError(
                    f"No video found on this page (HTML size: {html_len} chars). "
                    "Possible causes:\n"
                    "- Your cookie may have expired (try refreshing it)\n"
                    "- The page may not contain a video\n"
                    "- The URL may be incorrect"
                )

            video_url = found_videos[0]["url"]
            logger.info("[%s] Found video URL: %s", job_id, video_url)
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
            try:
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
            except Exception as hook_err:
                logger.debug("[%s] Progress hook error: %s", job_id, hook_err)

        ydl_opts = {
            "format": format_spec,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
        }

        # If cookie string is provided and the video is from Skool directly,
        # we may need to pass referer headers
        if cookie and "skool.com" in (skool_url or ""):
            ydl_opts["http_headers"] = {
                "Referer": skool_url,
                "Cookie": cookie,
            }

        update_job(job_id, {"status": "downloading", "progress_text": "Starting download..."})
        logger.info("[%s] Starting yt-dlp download: %s", job_id, video_url)

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
                logger.info("[%s] Download complete: %s (%s)", job_id, output_file, file_size)
            else:
                raise RuntimeError("yt-dlp returned no info for this video")

    except Exception as e:
        logger.exception("[%s] Download failed: %s", job_id, e)
        fail_job(job_id, str(e))
    except BaseException as e:
        # Catch KeyboardInterrupt, SystemExit, etc. so the job doesn't stay stuck
        logger.error("[%s] Download interrupted: %s", job_id, e)
        fail_job(job_id, f"Download interrupted: {e}")
        raise


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

    # Try to get lesson links from __NEXT_DATA__ first
    next_match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if next_match:
        try:
            data = json.loads(next_match.group(1))
            _find_lessons_in_json(data, lessons, url)
        except (json.JSONDecodeError, ValueError):
            pass

    # Also look for lesson links in HTML as fallback
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/classroom/" in href and href != url:
            full_url = href if href.startswith("http") else urljoin(SKOOL_BASE, href)
            title = link.get_text(strip=True) or "Untitled Lesson"
            # Avoid duplicates
            if not any(l["url"] == full_url for l in lessons):
                lessons.append({"title": title, "url": full_url})

    logger.info("Found %d lesson(s) on course page: %s", len(lessons), url)
    return lessons


def _find_lessons_in_json(obj, lessons: list, base_url: str, depth: int = 0) -> None:
    """Recursively walk JSON looking for lesson/classroom URLs."""
    if depth > 20:
        return

    if isinstance(obj, str):
        if "/classroom/" in obj and obj.startswith("/"):
            full_url = urljoin(SKOOL_BASE, obj)
            if not any(l["url"] == full_url for l in lessons):
                lessons.append({"title": "Untitled Lesson", "url": full_url})
    elif isinstance(obj, dict):
        # Look for objects that have both a URL and title
        href = obj.get("href", "") or obj.get("url", "") or obj.get("path", "")
        title = obj.get("title", "") or obj.get("name", "") or obj.get("label", "")
        if isinstance(href, str) and "/classroom/" in href:
            full_url = href if href.startswith("http") else urljoin(SKOOL_BASE, href)
            if not any(l["url"] == full_url for l in lessons):
                lessons.append({"title": title or "Untitled Lesson", "url": full_url})

        for value in obj.values():
            _find_lessons_in_json(value, lessons, base_url, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _find_lessons_in_json(item, lessons, base_url, depth + 1)
