from __future__ import annotations

import importlib.util
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import Document, Job, User, utcnow
from ..deps import current_user, get_db, get_settings, get_storage
from ..formatting import metrics
from ..services import get_owned_doc, remove_document, store_document
from ..validation import safe_docx, safe_pdf

router = APIRouter(prefix="/api/uploads")


def pdf_conversion_available() -> bool:
    return importlib.util.find_spec("pdf2docx") is not None


@router.post("")
def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db),
           settings=Depends(get_settings), storage=Depends(get_storage)):
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name.lower().endswith((".docx", ".pdf")): raise HTTPException(400, "Please choose a DOCX Word document or PDF.")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[-160:]
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(suffix=Path(name).suffix.lower(), dir=settings.data_dir); os.close(handle)
    temp = Path(temp_name); size = 0
    try:
        with temp.open("wb") as stream:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload: raise ValueError("That file exceeds 25 MB. Please use a smaller file.")
                stream.write(chunk)
        safe_pdf(temp) if temp.suffix == ".pdf" else safe_docx(temp, settings.max_unzipped)
        measured = metrics(temp)
        doc = store_document(db, storage, settings, user, temp, name, "upload")
    except Exception as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else "We could not read this document. Please save a new copy and try again.") from exc
    finally:
        file.file.close(); temp.unlink(missing_ok=True)
    return {"id": doc.id, "name": name, "size": size, "metrics": measured}


@router.post("/{id}/convert-to-docx")
def convert_to_docx(id: str, user: User = Depends(current_user), db: Session = Depends(get_db), settings=Depends(get_settings), storage=Depends(get_storage)):
    source = get_owned_doc(db, user, id, "upload")
    if not source.original_name.lower().endswith(".pdf"): raise HTTPException(400, "This conversion is only for PDF uploads.")
    if not pdf_conversion_available(): raise HTTPException(400, "PDF conversion is optional. Run enable-pdf.bat once, then restart Report Ready.")
    name = source.original_name[:-4] + "-converted.docx"
    with tempfile.TemporaryDirectory(dir=settings.data_dir) as folder, storage.local_copy(source.storage_key) as pdf_path:
        dest = Path(folder) / "converted.docx"
        try:
            import fitz
            from pdf2docx import Converter
            with fitz.open(pdf_path) as pdf:
                if not any(page.get_text().strip() for page in pdf): raise ValueError("This is a scanned PDF. OCR is needed first.")
            converter = Converter(str(pdf_path))
            try: converter.convert(str(dest))
            finally: converter.close()
            safe_docx(dest, settings.max_unzipped); measured = metrics(dest)
            doc = store_document(db, storage, settings, user, dest, name, "upload")
        except Exception as exc:
            raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else "This PDF could not be converted. Try saving it as DOCX in Word.") from exc
    return {"id": doc.id, "name": name, "convertedFrom": id, "metrics": measured, "warning": "Conversion can alter layout. Check tables, equations and page breaks in Word."}


@router.delete("/{id}")
def delete_upload(id: str, user: User = Depends(current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
    doc = get_owned_doc(db, user, id, "upload")
    frontier, seen = [doc.id], {doc.id}
    while frontier:  # the upload, its formatted outputs, and PDFs made from those outputs
        for job in db.scalars(select(Job).where(Job.source_doc_id.in_(frontier), Job.user_id == user.id)).all():
            if job.status == "queued": job.status, job.error, job.finished_at = "failed", "Cancelled because the uploaded copy was deleted.", utcnow()
            output = db.get(Document, job.output_doc_id) if job.output_doc_id else None
            if output and output.owner_user_id == user.id and output.deleted_at is None: remove_document(db, storage, output)
        frontier = [j.output_doc_id for j in db.scalars(select(Job).where(Job.source_doc_id.in_(frontier), Job.user_id == user.id)) if j.output_doc_id and j.output_doc_id not in seen]
        seen.update(frontier)
    remove_document(db, storage, doc); db.commit()
    return {"message": "This uploaded copy and its formatted outputs were deleted."}
