"""Document ownership, retention and storage helpers shared by the routers."""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .db_models import Document, UsageEvent, User, utcnow

LOG = logging.getLogger(__name__)
PAID_PLANS = {"pro", "team", "institutional"}


def valid_id(ident) -> str:
    try:
        if str(uuid.UUID(ident)) != ident: raise ValueError()
    except (ValueError, AttributeError, TypeError): raise HTTPException(404, "That file could not be found.")
    return ident


def retention_hours(settings, user: User) -> int:
    from .plans import effective_plan
    from .db_models import Team, TeamMember
    db = object_session(user)
    paid = False
    if db is not None:
        paid = effective_plan(db, user).id != "free"
        if not paid:
            owners = db.scalars(select(User).join(Team, Team.owner_id == User.id).join(TeamMember, TeamMember.team_id == Team.id).where(TeamMember.user_id == user.id))
            paid = any(effective_plan(db, owner).id == "team" for owner in owners)
    return settings.paid_retention_hours if paid else settings.free_retention_hours


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def store_document(db: Session, storage, settings, user: User, source: Path, name: str, kind: str) -> Document:
    ident, now = str(uuid.uuid4()), utcnow()
    doc = Document(id=ident, owner_user_id=user.id, original_name=name[:255], storage_key=f"{user.id}/{ident}",
                   size=source.stat().st_size, sha256=sha256_of(source), kind=kind, created_at=now,
                   expires_at=now + timedelta(hours=retention_hours(settings, user)))
    storage.put_file(doc.storage_key, source)
    try:
        db.add(doc); db.commit()
    except Exception:
        db.rollback(); storage.delete(doc.storage_key); raise
    return doc


def get_owned_doc(db: Session, user: User, ident: str, kind: str | tuple[str, ...] | None = None) -> Document:
    """The only way routes load a document: it must belong to the signed-in user and still exist."""
    kinds = (kind,) if isinstance(kind, str) else kind
    query = select(Document).where(Document.id == valid_id(ident), Document.owner_user_id == user.id, Document.deleted_at.is_(None))
    if kinds: query = query.where(Document.kind.in_(kinds))
    doc = db.scalars(query).first()
    if doc is None or (doc.expires_at and doc.expires_at < utcnow()): raise HTTPException(404, "That file is no longer available. Please upload it again.")
    return doc


def remove_document(db: Session, storage, doc: Document):
    """Delete the stored bytes first; the row stays (without a file) so history and usage keep their references."""
    try: storage.delete(doc.storage_key)
    except Exception: LOG.warning("Could not remove stored file %s", doc.storage_key); return False
    doc.deleted_at = utcnow(); db.add(doc)
    return True


def record_usage(db: Session, user: User, event: str, job_id: str | None = None):
    if job_id and db.scalar(select(UsageEvent.id).where(UsageEvent.job_id == job_id, UsageEvent.event == event)):
        return  # already reserved when enqueued
    db.add(UsageEvent(user_id=user.id, event=event, job_id=job_id)); db.commit()


class Cleaner:
    def __init__(self, interval: int = 300): self.interval, self.last = interval, 0.0

    def run(self, session_factory, storage, force: bool = False) -> int:
        now = time.time()
        if not force and now - self.last < self.interval: return 0
        self.last = now; removed = 0
        with session_factory() as db:
            expired = db.scalars(select(Document).where(Document.deleted_at.is_(None), Document.expires_at < utcnow()).limit(500)).all()
            for doc in expired: removed += remove_document(db, storage, doc)
            db.commit()
        return removed
