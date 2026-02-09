# Image Factory

**Local desktop app that automates print-on-demand image prep.**

No cloud, no accounts, no external services. Everything runs on your computer.

---

## Quick Start (3 steps)

### Step 1: Install

**macOS / Linux:**
```bash
cd image-factory
./setup.sh
```

**Windows:**
```
Double-click setup.bat
```

This creates a virtual environment and installs all dependencies. Only needed once.

### Step 2: Run

**macOS / Linux:**
```bash
source venv/bin/activate
python run.py
```

**Windows:**
```
venv\Scripts\activate.bat
python run.py
```

### Step 3: Use

Your browser opens automatically at **http://localhost:5555**

That's it! You're running.

---

## How to Use

### Import an Image
1. Click **"+ Import Image"** in the top bar
2. Select a PNG or JPG file
3. The job appears in the left panel

### Or: Drop Files into INBOX
1. Open your INBOX folder (default: `~/Desktop/ImageFactory/INBOX/`)
2. Turn on **"Auto Watch"** toggle in the top bar
3. Drop PNG/JPG files into that folder — they get processed automatically

### Job Lifecycle
Each image goes through these steps:
1. **Detect** – identifies file type and checks for transparency
2. **Background Removal** – removes background (if enabled)
3. **Edge Cleanup** – softens cutout edges, removes halos
4. **Upscale** – enlarges to target print size
5. **Resize** – fits to your chosen preset dimensions
6. **Export** – saves print-ready PNG (and optional JPG preview)

### View a Job
Click any job in the left panel to see:
- Processing steps checklist with live status
- Settings used for that job
- Output files
- Error messages (if any)

### Re-run or Duplicate
- **Re-run**: Processes the same image with the same settings
- **Duplicate**: Processes the same image with different settings (e.g., different preset)

---

## Settings

Click **"Settings"** in the top bar to configure:

### Folders
| Setting | Default | Description |
|---------|---------|-------------|
| INBOX | `~/Desktop/ImageFactory/INBOX/` | Where to watch for new files |
| OUTPUT | `~/Desktop/ImageFactory/OUTPUT/` | Where processed images go |
| ARCHIVE | `~/Desktop/ImageFactory/ARCHIVE/` | Where originals get moved after success |
| LOGS | `~/Desktop/ImageFactory/LOGS/` | App logs and per-job logs |

### Processing
| Setting | Options | Default |
|---------|---------|---------|
| Background Removal | Auto / Ask each time / Never | Ask each time |
| Upscale Quality | Fast / Best | Fast |
| Fit Mode | Pad to fit / Crop to fill | Pad |

### Output Presets
Built-in presets:
- **Portrait 2:3** — 4500×5400 pixels
- **Square 1:1** — 5000×5000 pixels

Add custom presets via the API (see below).

### Naming
Default template: `{date}_{original}_{preset}_v{version}`

Files are **never overwritten** — the version number auto-increments.

### Folder Watcher (Dropbox-friendly)
- **Stability Wait**: Waits 4 seconds for file to stop changing before processing
- **Trigger Mode**: Only processes files ending with `_READY.png` or `_READY.jpg`
- Automatically ignores hidden files (`.file`), temp files (`.tmp`), and Dropbox conflicts

---

## Using with Dropbox

1. Open **Settings** → set your INBOX path to a Dropbox folder
2. Enable **Trigger Mode** (optional) — only processes files you mark as `_READY`
3. Turn on **Auto Watch**
4. Files synced via Dropbox will be detected and processed automatically
5. The stability check prevents processing half-synced files

---

## Local API (for OpenClaw)

The app exposes a REST API on `localhost:5555` for automation.

### Endpoints

#### Health Check
```bash
curl http://localhost:5555/health
```
```json
{"status": "ok", "app": "Image Factory", "version": "1.0.0", "watcher_running": false}
```

#### Process an Image
```bash
curl -X POST http://localhost:5555/process \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/path/to/image.png",
    "preset": "4500x5400_portrait",
    "background_mode": "auto",
    "upscale_quality": "best",
    "export_jpg": true
  }'
```
```json
{"job_id": "20250209143022_a1b2c3d4", "status": "queued"}
```

#### List All Jobs
```bash
curl http://localhost:5555/jobs
```

#### Get Job Status
```bash
curl http://localhost:5555/jobs/20250209143022_a1b2c3d4
```

#### Re-run a Job
```bash
curl -X POST http://localhost:5555/jobs/20250209143022_a1b2c3d4/rerun
```

#### Duplicate with Different Settings
```bash
curl -X POST http://localhost:5555/jobs/20250209143022_a1b2c3d4/duplicate \
  -H "Content-Type: application/json" \
  -d '{"preset": "5000x5000_square"}'
```

#### Upload a File
```bash
curl -X POST http://localhost:5555/import \
  -F "file=@/path/to/image.png"
```

#### Control Folder Watcher
```bash
curl -X POST http://localhost:5555/watcher/start
curl -X POST http://localhost:5555/watcher/stop
curl http://localhost:5555/watcher/status
```

#### Get/Update Settings
```bash
curl http://localhost:5555/settings

curl -X PATCH http://localhost:5555/settings \
  -H "Content-Type: application/json" \
  -d '{"background_removal": "auto", "upscale_quality": "best"}'
```

#### Manage Presets
```bash
# List presets
curl http://localhost:5555/presets

# Add a custom preset
curl -X POST http://localhost:5555/presets \
  -H "Content-Type: application/json" \
  -d '{"key": "custom_3000x3000", "label": "Custom 3000x3000", "width": 3000, "height": 3000}'

# Delete a preset
curl -X DELETE http://localhost:5555/presets/custom_3000x3000
```

---

## Where to Edit Things

| What | File | Notes |
|------|------|-------|
| Default settings | `app/config.py` | `DEFAULTS` dict at the top |
| Built-in presets | `app/config.py` | `DEFAULT_PRESETS` dict |
| Image processing logic | `app/processor.py` | The pipeline steps |
| Edge cleanup algorithm | `app/processor.py` | `_edge_cleanup()` function |
| Upscale logic | `app/processor.py` | `_upscale()` function |
| Folder watcher rules | `app/watcher.py` | `_should_ignore()` and `_is_stable()` |
| UI layout | `app/static/index.html` | HTML structure |
| UI styling | `app/static/style.css` | Colors, layout, spacing |
| UI behavior | `app/static/app.js` | Button actions, API calls |
| API routes | `app/main.py` | All endpoint definitions |
| Runtime settings | `settings.json` | Auto-generated, safe to edit |

---

## Folder Structure (auto-created)

```
~/Desktop/ImageFactory/
├── INBOX/                    ← Drop images here
├── OUTPUT/
│   ├── 4500x5400_portrait/   ← Processed images by preset
│   └── 5000x5000_square/
├── ARCHIVE/
│   └── 2025-02-09/           ← Originals moved here after success
└── LOGS/
    ├── app.log               ← Application log
    └── jobs/
        └── {job_id}.json     ← Per-job detailed log
```

---

## Troubleshooting

**"rembg not available"**: Background removal requires the `rembg` package. The first time you use it, it downloads a ~170MB AI model. After that, it works fully offline. If install fails, set background removal to "Never" and the app works fine without it.

**Port already in use**: Run with a different port: `python run.py --port 6666`

**Job failed**: Click the job to see the error message. Common causes:
- File was deleted before processing started
- Corrupt image file
- Disk full

**Files not being detected by watcher**: Make sure:
- Auto Watch is enabled (toggle in top bar)
- Files are PNG or JPG
- Files don't start with `.` or end with `.tmp`
- If trigger mode is on, files must end with `_READY.png` or `_READY.jpg`

---

## Tech Stack

- **Backend**: Python 3.10+ with FastAPI
- **UI**: HTML/CSS/JS served locally (no build step, no Node.js needed)
- **Image Processing**: Pillow (resize, upscale, crop, pad)
- **Background Removal**: rembg with U2Net (fully offline after first model download)
- **Folder Watching**: watchdog library
- **Server**: uvicorn

Everything runs locally. No data leaves your computer.
