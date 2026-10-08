"""Upload safety checks: archive limits for DOCX, readable unlocked PDFs."""
from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

from docx import Document


def safe_docx(path: Path, max_unzipped: int):
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist(); names = [i.filename for i in infos]
            unsafe = any(".." in PurePosixPath(n.replace("\\", "/")).parts or n.startswith(("/", "\\")) or ":" in n for n in names)
            if unsafe or len(infos) > 3000 or len(set(names)) != len(names) or sum(i.file_size for i in infos) > max_unzipped:
                raise ValueError("The document archive exceeds safety limits or contains unsafe paths.")
            if "word/document.xml" not in names or "[Content_Types].xml" not in names: raise ValueError("This file is not a valid Word document.")
            if any("vbaProject" in n for n in names): raise ValueError("Please save a macro-free DOCX copy first.")
        Document(path)
    except ValueError: raise
    except Exception as exc: raise ValueError("This DOCX is damaged or unsupported. Open it in Word and save a new DOCX copy.") from exc


def safe_pdf(path: Path):
    try:
        import fitz
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-": raise ValueError()
        with fitz.open(path) as pdf:
            if pdf.needs_pass or len(pdf) == 0: raise ValueError()
    except Exception as exc: raise ValueError("Please use a valid, unlocked PDF document.") from exc
