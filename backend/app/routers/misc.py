from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .. import pdf_export

from ..db_models import Feedback, User
from ..deps import current_user, get_db
from ..models import Review
from .documents import pdf_conversion_available

router = APIRouter(prefix="/api")
VERSION = "3.3.0"
LOG = logging.getLogger(__name__)


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        LOG.exception("Health check database query failed")
        raise HTTPException(503, "Database is unavailable.") from exc
    return {"status": "ok", "version": VERSION, "pdfConversion": pdf_conversion_available(), "pdfExport": pdf_export.available(request.app.state.settings),
            "retentionHours": request.app.state.settings.free_retention_hours}


@router.post("/reviews")
def save_review(review: Review, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(Feedback(user_id=user.id, rating=review.rating, comment=review.comment.strip())); db.commit()
    return {"message": "Thank you for your feedback."}
