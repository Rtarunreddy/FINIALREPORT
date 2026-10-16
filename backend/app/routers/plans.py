from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db_models import User
from ..deps import current_user, get_db
from ..plans import PLANS, quota_view

router = APIRouter(prefix="/api/plans")


@router.get("")
def plans():
    return {"plans": [asdict(plan) for plan in PLANS.values()]}


@router.get("/usage")
def usage(team_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return quota_view(db, user, team_id)
