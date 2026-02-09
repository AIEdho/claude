#!/usr/bin/env python3
"""
Image Factory – One-command launcher.

Usage:
    python run.py            # Start the app (opens browser automatically)
    python run.py --port 5555  # Use a custom port
    python run.py --no-browser # Don't auto-open the browser
"""

import argparse
import sys
import threading
import time
import webbrowser


def main():
    parser = argparse.ArgumentParser(description="Image Factory – Local Print-on-Demand Image Prep")
    parser.add_argument("--port", type=int, default=5555, help="Port to run on (default: 5555)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open the browser")
    args = parser.parse_args()

    # Auto-open browser after a short delay
    if not args.no_browser:
        def open_browser():
            time.sleep(2)
            url = f"http://localhost:{args.port}"
            print(f"\n  Opening {url} in your browser...\n")
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    print(f"""
    ╔══════════════════════════════════════════╗
    ║         IMAGE FACTORY  v1.0.0            ║
    ║                                          ║
    ║   Running at: http://localhost:{args.port}     ║
    ║                                          ║
    ║   Press Ctrl+C to stop                   ║
    ╚══════════════════════════════════════════╝
    """)

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
