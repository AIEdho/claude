#!/usr/bin/env bash
# ── Image Factory – Setup Script (macOS / Linux) ────────────────────
#
# This script installs everything you need to run Image Factory.
# Run it once, then use "python run.py" to start the app.
#
set -e

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       IMAGE FACTORY – SETUP              ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "  ERROR: Python 3 is not installed."
    echo "  Please install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
fi

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Found Python $PYVER"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

echo "  Activating virtual environment..."
source venv/bin/activate

echo "  Installing dependencies (this may take a few minutes)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "  ✓ Setup complete!"
echo ""
echo "  TO RUN THE APP:"
echo "  ────────────────────────────────────"
echo "  source venv/bin/activate"
echo "  python run.py"
echo "  ────────────────────────────────────"
echo ""
echo "  Or use the one-liner:"
echo "  source venv/bin/activate && python run.py"
echo ""
