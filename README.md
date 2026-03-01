# Skool Video Downloader

**Download videos from Skool courses for offline viewing.**

A local web app that lets you save Skool lesson videos as MP4 files. Runs entirely on your computer - no third-party services needed.

## Features

- **Single Video Download** – Paste a Skool lesson URL and download the video
- **Direct URL Support** – Also works with direct Vimeo, YouTube, and other video URLs
- **Video Extraction** – Preview what videos are on a page before downloading
- **Quality Selection** – Choose between best, 1080p, 720p, or 480p
- **Download Progress** – Real-time progress tracking in the web UI
- **Job History** – Track all your downloads with status and file info
- **Dark Mode UI** – Clean, modern interface

## Prerequisites

- Python 3.10+
- A Skool account with access to the courses you want to download
- FFmpeg (recommended, for video merging) – [Install FFmpeg](https://ffmpeg.org/download.html)

## Quick Start

### 1. Setup

**macOS / Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```
setup.bat
```

### 2. Run

```bash
source venv/bin/activate   # Windows: venv\Scripts\activate.bat
python run.py
```

The app opens at [http://localhost:5555](http://localhost:5555).

### 3. Configure

1. Click **Settings** in the top-right
2. Paste your Skool session cookie (see below)
3. Set your download folder and preferred video quality
4. Click **Save Settings**

### 4. Download

1. Copy a lesson URL from Skool (e.g., `https://www.skool.com/your-community/classroom/...`)
2. Paste it in the URL bar
3. Click **Download**

## Getting Your Skool Cookie

1. Log into [Skool](https://www.skool.com) in your browser
2. Open DevTools (F12 or right-click → Inspect)
3. Go to the **Network** tab
4. Reload the page
5. Click any request to `skool.com`
6. Find the **Cookie** header in the Request Headers
7. Copy the entire cookie value
8. Paste it in the app's Settings

## Project Structure

```
├── run.py              # App launcher
├── selfcheck.py        # Dependency checker
├── requirements.txt    # Python dependencies
├── setup.sh / .bat     # Setup scripts
└── app/
    ├── main.py         # FastAPI application & API routes
    ├── config.py       # Settings management
    ├── jobs.py         # Download job tracking
    ├── downloader.py   # Video extraction & download logic
    └── static/         # Web UI (HTML, CSS, JS)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/health` | Health check |
| GET | `/settings` | Get current settings |
| PATCH | `/settings` | Update settings |
| GET | `/jobs` | List all download jobs |
| GET | `/jobs/{id}` | Get job details |
| DELETE | `/jobs/{id}` | Delete a job |
| POST | `/download` | Start a download |
| POST | `/download/batch` | Start multiple downloads |
| POST | `/extract` | Extract video info from a URL |
| POST | `/extract/course` | Extract all lesson links from a course |

## Disclaimer

This tool is intended for personal, offline use by users who have legitimate access to Skool courses. It does not encourage piracy or redistribution of copyrighted material. Please respect content creators and the terms of service of the platforms you use.
