from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db_models import Feedback, User
from ..deps import current_user, get_db
from ..models import Review
from .documents import pdf_conversion_available
from .. import pdf_export

router = APIRouter(prefix="/api")
VERSION = "3.2.0"


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "version": VERSION, "pdfConversion": pdf_conversion_available(), "pdfExport": pdf_export.available(request.app.state.settings),
            "retentionHours": request.app.state.settings.free_retention_hours}


@router.post("/reviews")
def save_review(review: Review, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(Feedback(user_id=user.id, rating=review.rating, comment=review.comment.strip())); db.commit()
    return {"message": "Thank you for your feedback."}
