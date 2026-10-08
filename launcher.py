"""One-window launcher. The packaged UI needs no Node installation."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8000"


def running_app():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return json.load(response).get("version") == "3.2.0"
    except Exception: return False


def main():
    if sys.version_info < (3, 10): raise RuntimeError("Install Python 3.10 or newer, then run start.bat again.")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        raise RuntimeError("The built interface is missing. Restore frontend/dist from the ZIP, or run npm ci and npm run build inside frontend.")
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        print("First launch: creating an isolated Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    requirements = ROOT / "backend" / "requirements-desktop.txt"
    digest = hashlib.sha256(requirements.read_bytes() + (ROOT / "backend" / "requirements.txt").read_bytes()).hexdigest()
    stamp = environment / ".report-ready-requirements"
    if not stamp.exists() or stamp.read_text() != digest:
        print("Installing required packages. Internet access is needed for this setup step...", flush=True)
        subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(requirements)])
        stamp.write_text(digest)
    if "--enable-pdf" in sys.argv:
        subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(ROOT / "backend" / "requirements-pdf.txt")])
        print("PDF conversion is installed. Restart Report Ready.")
        return
    if running_app():
        webbrowser.open(URL)
        print("Report Ready is already running. Open " + URL)
        return
    try:
        with socket.socket() as probe: probe.bind(("127.0.0.1", 8000))
    except OSError as exc: raise RuntimeError("Port 8000 is in use. Close the older Report Ready window or the app using this port, then try again.") from exc
    print("Starting Report Ready. Keep this window open. Press Ctrl+C to stop.", flush=True)
    process = subprocess.Popen([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT / "backend", env={**os.environ, "REPORT_READY_LOCAL_MODE": "1"})
    try:
        for _ in range(120):
            if process.poll() is not None: raise RuntimeError("The local service stopped. Check the error above.")
            if running_app():
                print("Ready: " + URL, flush=True); webbrowser.open(URL); break
            time.sleep(.25)
        else: raise RuntimeError("Startup took too long. Check the error above and try again.")
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nReport Ready stopped.")
    except Exception as error:
        print(f"\nCould not start Report Ready: {error}\nYour files have not been changed.", file=sys.stderr)
        sys.exit(1)
