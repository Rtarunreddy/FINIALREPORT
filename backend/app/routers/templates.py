from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import Template, User
from ..deps import current_user, get_db, get_storage
from ..formatting import (APA_PROFILE, BUSINESS_PROFILE, CHICAGO_PROFILE, DEFAULT_PROFILE,
                          HARVARD_PROFILE, IEEE_PROFILE, MLA_PROFILE, TECHNICAL_PROFILE,
                          style_profile)
from ..models import Profile
from ..services import get_owned_doc, record_usage, valid_id

router = APIRouter(prefix="/api")
BUILTINS = [
    {"id": "generic", **DEFAULT_PROFILE},
    {"id": "technical", **TECHNICAL_PROFILE},
    {"id": "apa7", **APA_PROFILE},
    {"id": "mla9", **MLA_PROFILE},
    {"id": "chicago", **CHICAGO_PROFILE},
    {"id": "harvard", **HARVARD_PROFILE},
    {"id": "ieee", **IEEE_PROFILE},
    {"id": "business", **BUSINESS_PROFILE},
]
BUILTIN_IDS = {item["id"] for item in BUILTINS}


def save_template(db: Session, user: User, profile: Profile) -> dict:
    item = profile.model_dump()
    existing = db.get(Template, item["id"]) if item["id"] and item["id"] not in BUILTIN_IDS else None
    if existing is not None and existing.owner_user_id != user.id: existing = None  # never overwrite someone else's template
    if existing is None:
        existing = Template(id=str(uuid.uuid4()), owner_user_id=user.id)
    item["id"] = existing.id
    existing.name, existing.profile_json = item["name"], item
    db.add(existing); db.commit()
    return item


@router.get("/profiles")
def list_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    mine = []
    for row in db.scalars(select(Template).where(Template.owner_user_id == user.id).order_by(Template.created_at)):
        try: mine.append(Profile.model_validate(row.profile_json | {"id": row.id}).model_dump())
        except ValueError: continue
    return BUILTINS + mine


@router.post("/profiles")
def create_profile(profile: Profile, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return save_template(db, user, profile)


@router.delete("/profiles/{id}")
def delete_profile(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if id in BUILTIN_IDS: raise HTTPException(400, "Built-in templates cannot be deleted.")
    row = db.get(Template, valid_id(id))
    if row is None or row.owner_user_id != user.id: raise HTTPException(404, "That template could not be found.")
    db.delete(row); db.commit()
    return {"message": "Template deleted."}


@router.post("/uploads/{id}/learn-profile")
def learn_profile(id: str, user: User = Depends(current_user), db: Session = Depends(get_db), storage=Depends(get_storage)):
    doc = get_owned_doc(db, user, id, "upload")
    if not doc.original_name.lower().endswith(".docx"): raise HTTPException(400, "Convert this PDF to DOCX before formatting or learning its format.")
    try:
        with storage.local_copy(doc.storage_key) as path:
            learned = Profile.model_validate(style_profile(path, f"Learned: {Path(doc.original_name).stem[-60:]}"))
        saved = save_template(db, user, learned)
    except Exception as exc:
        raise HTTPException(400, "We could not learn a usable format. Use a report with standard Word styles, or edit a built-in template.") from exc
    record_usage(db, user, "learn")
    return {"profile": saved, "message": "Saved margins and observed body and heading settings. Review them before using the template."}
