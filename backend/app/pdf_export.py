"""DOCX to PDF on the server with LibreOffice (headless). Microsoft Word is used only as a Windows desktop fallback."""
from __future__ import annotations

import importlib.util
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

NOTE = ("This PDF was rendered with LibreOffice. Fonts that are not installed on the server are substituted, so line breaks can differ "
        "slightly from Word. Check the DOCX in Word if exact pagination matters.")


def find_soffice(settings) -> str | None:
    if settings.soffice_path: return settings.soffice_path if Path(settings.soffice_path).exists() or shutil.which(settings.soffice_path) else None
    return shutil.which("soffice") or shutil.which("libreoffice")


def word_available() -> bool:
    return os.name == "nt" and importlib.util.find_spec("pythoncom") is not None


def available(settings) -> bool:
    return bool(find_soffice(settings)) or word_available()


def _kill(process: subprocess.Popen):
    try:
        if os.name == "nt": process.kill()
        else: os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError): pass


def libreoffice_convert(soffice: str, source: Path, folder: Path, timeout: int) -> Path:
    """Convert in a private profile directory so concurrent conversions never share a lock."""
    profile = Path(tempfile.mkdtemp(prefix="lo-profile-", dir=folder)); out = folder / "pdf-out"; out.mkdir(exist_ok=True)
    command = [soffice, "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nofirststartwizard", f"-env:UserInstallation={profile.as_uri()}",
               "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(out), str(source)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, "HOME": str(profile)},
                               start_new_session=(os.name != "nt"))
    try: process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(process); process.communicate()
        raise ValueError("PDF export took too long. Try again, or download the DOCX and save it as PDF in Word.")
    finally:
        if process.poll() is None: _kill(process)
        shutil.rmtree(profile, ignore_errors=True)
    result = out / (source.stem + ".pdf")
    if not result.is_file() or result.read_bytes()[:5] != b"%PDF-":
        raise ValueError("The PDF could not be created from this document. Download the DOCX and save it as PDF in Word.")
    return result


def word_convert(source: Path, dest: Path) -> Path:
    import pythoncom
    import win32com.client
    word = document = None; pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application"); word.Visible = False; word.DisplayAlerts = 0
        document = word.Documents.Open(str(source.resolve()), ReadOnly=True)
        document.ExportAsFixedFormat(str(dest.resolve()), 17)
    except Exception as exc:
        raise ValueError("Word could not export the PDF. Close any Word dialogs and try again, or save the downloaded DOCX as PDF in Word.") from exc
    finally:
        if document is not None:
            try: document.Close(False)
            except Exception: pass
        if word is not None:
            try: word.Quit()
            except Exception: pass
        pythoncom.CoUninitialize()
    return dest


def convert(settings, source: Path, folder: Path) -> tuple[Path, str]:
    """Return (pdf_path, engine). `source` must be a real file on local disk."""
    soffice = find_soffice(settings)
    if soffice: return libreoffice_convert(soffice, source, folder, settings.pdf_timeout_seconds), "libreoffice"
    if word_available(): return word_convert(source, folder / "formatted.pdf"), "word"
    raise ValueError("PDF export is not available on this server. Download the DOCX and save it as PDF in Word.")
