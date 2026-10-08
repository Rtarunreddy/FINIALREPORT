"""SQLAlchemy tables. All timestamps are naive UTC so SQLite and Postgres behave the same."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    plan_id: Mapped[str] = mapped_column(String(32), default="free")
    checkout_session_id: Mapped[str | None] = mapped_column(String(100))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[str] = mapped_column(String(32), default="team")
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # owner | admin | member


class Template(Base):
    """A saved formatting profile. Built-in templates live in code, not here."""
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    profile_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # upload | output | reference
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_doc_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="format", server_default="format")  # format | pdf
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    params_json: Mapped[dict | None] = mapped_column(JSON)  # the profile a queued format job will apply
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    output_doc_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    report_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(32))  # format | learn | export
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("ix_usage_user_created", "user_id", "created_at"),)


class Subscription(Base):
    """Filled by the Stripe webhook in the billing phase."""
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_type: Mapped[str] = mapped_column(String(8))  # user | team
    owner_id: Mapped[str] = mapped_column(String(36))
    stripe_sub_id: Mapped[str] = mapped_column(String(64), unique=True)
    plan: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "stripe_sub_id"),)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TeamInvite(Base):
    __tablename__ = "team_invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
