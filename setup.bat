@echo off
REM ── Skool Video Downloader – Setup Script (Windows) ────────────────
REM
REM This script installs everything you need to run the downloader.
REM Run it once, then use "python run.py" to start the app.
REM

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║   SKOOL VIDEO DOWNLOADER – SETUP         ║
echo   ╚══════════════════════════════════════════╝
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python is not installed.
    echo   Please install Python 3.10+ from https://www.python.org/downloads/
    echo   IMPORTANT: Check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%i
echo   Found Python %PYVER%

REM Create virtual environment
if not exist "venv" (
    echo   Creating virtual environment...
    python -m venv venv
)

echo   Activating virtual environment...
call venv\Scripts\activate.bat

echo   Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo   Setup complete!
echo.
echo   TO RUN THE APP:
echo   ────────────────────────────────────
echo   venv\Scripts\activate.bat
echo   python run.py
echo   ────────────────────────────────────
echo.
pause
