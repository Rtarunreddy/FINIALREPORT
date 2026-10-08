from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import Document, Job, Template, User
from ..deps import current_user, get_db, get_storage
from ..formatting import audit
from ..models import ApplyRequest, Profile
from ..services import get_owned_doc, valid_id
from ..plans import reserve_job, quota_scope, team_access
from .. import pdf_export
from .templates import BUILTINS

router = APIRouter(prefix="/api")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ACTIVE = ("queued", "running")


def source_docx(db, user, id):
    doc = get_owned_doc(db, user, id, "upload")
    if not doc.original_name.lower().endswith(".docx"): raise HTTPException(400, "Convert this PDF to DOCX before formatting or learning its format.")
    return doc


def resolve_profile(db: Session, user: User, req: ApplyRequest) -> dict:
    """An explicit profile wins; otherwise a template id; otherwise the built-in default (one-click formatting)."""
    if req.profile is not None: return req.profile.model_dump()
    tid = req.templateId or "generic"
    builtin = next((b for b in BUILTINS if b["id"] == tid), None)
    if builtin: return Profile.model_validate(builtin).model_dump()
    row = db.get(Template, valid_id(tid))
    if row is None: raise HTTPException(404, "That template could not be found.")
    if row.team_id:
        if req.teamId != row.team_id: raise HTTPException(403, "Select this template’s team workspace first.")
        team_access(db, user, row.team_id)
    elif row.owner_user_id != user.id: raise HTTPException(404, "That template could not be found.")
    return Profile.model_validate(row.profile_json | {"id": row.id}).model_dump()


def job_view(job: Job) -> dict:
    return {"id": job.id, "kind": job.kind, "status": job.status, "error": job.error, "outputId": job.output_doc_id,
            "report": job.report_json if job.status == "done" else None, "createdAt": job.created_at.isoformat() + "Z",
            "finishedAt": job.finished_at.isoformat() + "Z" if job.finished_at else None}


def enqueue(request: Request, db: Session, user: User, **fields) -> Job:
    team_id = fields.get("team_id")
    quota_scope(db, user, team_id, lock=True)
    active = db.scalar(select(func.count()).select_from(Job).where(Job.user_id == user.id, Job.status.in_(ACTIVE)))
    if active >= request.app.state.settings.max_active_jobs:
        raise HTTPException(429, "You already have several reports in progress. Wait for one to finish and try again.")
    job = Job(user_id=user.id, status="queued", **fields)
    if request.app.state.settings.local_mode:
        db.add(job)
    else: reserve_job(db, user, job, team_id)
    db.commit()
    request.app.state.runner.notify()
    return job


@router.post("/uploads/{id}/audit")
def do_audit(id: str, req: ApplyRequest, user: User = Depends(current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
    doc = source_docx(db, user, id); profile = resolve_profile(db, user, req)
    with storage.local_copy(doc.storage_key) as path: return audit(path, profile)


@router.post("/uploads/{id}/apply", status_code=202)
def do_apply(id: str, req: ApplyRequest, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = source_docx(db, user, id); profile = resolve_profile(db, user, req)
    template = db.get(Template, profile["id"]) if profile.get("id") and len(profile["id"]) == 36 else None
    job = enqueue(request, db, user, kind="format", source_doc_id=source.id, params_json={"profile": profile},
                  template_id=template.id if template and (template.owner_user_id == user.id or (req.teamId and template.team_id == req.teamId)) else None, team_id=req.teamId)
    return job_view(job)


@router.get("/jobs")
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db), limit: int = 25):
    rows = db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(max(1, min(limit, 100)))).all()
    return [job_view(job) | {"report": None} for job in rows]


@router.get("/jobs/{id}")
def get_job(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, valid_id(id))
    if job is None or job.user_id != user.id: raise HTTPException(404, "That job could not be found.")
    return job_view(job)


@router.get("/outputs/{id}/document")
def download_doc(id: str, user: User = Depends(current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
    doc = get_owned_doc(db, user, id, "output")
    try: data = storage.read_bytes(doc.storage_key)
    except KeyError: raise HTTPException(404, "That output is no longer available. Format the report again.")
    pdf = doc.original_name.lower().endswith(".pdf")
    return Response(data, media_type="application/pdf" if pdf else DOCX,
                    headers={"Content-Disposition": f'attachment; filename="formatted-report.{"pdf" if pdf else "docx"}"'})


@router.get("/outputs/{id}/report")
def download_report(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = get_owned_doc(db, user, id, "output")
    job = db.scalars(select(Job).where(Job.output_doc_id == doc.id, Job.user_id == user.id)).first()
    if job is None or job.report_json is None: raise HTTPException(404, "That output is no longer available. Format the report again.")
    return JSONResponse(job.report_json, headers={"Content-Disposition": 'attachment; filename="formatting-change-report.json"'})


@router.post("/outputs/{id}/pdf", status_code=202)
def request_pdf(id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Queue a PDF export of a formatted DOCX. Repeat requests reuse a finished or in-progress export."""
    source = get_owned_doc(db, user, id, "output")
    if source.original_name.lower().endswith(".pdf"): raise HTTPException(400, "This output is already a PDF.")
    if not pdf_export.available(request.app.state.settings):
        raise HTTPException(400, "PDF export is not available on this server. Download the DOCX and use Word's Save as PDF.")
    for job in db.scalars(select(Job).where(Job.user_id == user.id, Job.kind == "pdf", Job.source_doc_id == source.id).order_by(Job.created_at.desc())):
        if job.status in ACTIVE: return job_view(job)
        if job.status == "done" and job.output_doc_id:
            out = db.get(Document, job.output_doc_id)
            if out is not None and out.deleted_at is None: return job_view(job)
    origin = db.scalar(select(Job).where(Job.output_doc_id == source.id, Job.user_id == user.id))
    return job_view(enqueue(request, db, user, kind="pdf", source_doc_id=source.id, team_id=origin.team_id if origin else None))
