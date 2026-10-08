"""Provisional product limits; UTC calendar months, not Stripe invoice periods."""
from dataclasses import asdict, dataclass
from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from .db_models import Job, Subscription, Team, TeamMember, UsageEvent, User, utcnow

@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    monthly_jobs: int
    seats: int

PLANS = {p.id: p for p in (Plan("free", "Free", 5, 1), Plan("pro", "Pro", 100, 1), Plan("team", "Team", 500, 5))}

def effective_plan(db, user):
    # Re-check the paid period so a missing renewal webhook cannot grant indefinite access.
    rows = db.scalars(select(Subscription).where(Subscription.owner_type == "user", Subscription.owner_id == user.id,
        Subscription.status.in_(("active", "trialing")), Subscription.current_period_end > utcnow())).all()
    return max((PLANS[s.plan] for s in rows if s.plan in PLANS), key=lambda p: p.monthly_jobs, default=PLANS["free"])

def lock_user(db, user_id):
    # A no-op UPDATE obtains a write lock on SQLite and a row lock on PostgreSQL.
    db.execute(update(User).where(User.id == user_id).values(plan_id=User.plan_id))

def team_access(db, user, team_id, owner=False, paid=True):
    team = db.get(Team, team_id)
    member = db.get(TeamMember, (team_id, user.id), populate_existing=True)
    if not team or not member: raise HTTPException(404, "Team not found.")
    if owner and team.owner_id != user.id: raise HTTPException(403, "Only the team owner can do this.")
    if paid and effective_plan(db, db.get(User, team.owner_id)).id != "team":
        raise HTTPException(403, "The team owner needs an active Team plan. Open Plans & team to upgrade.")
    return team

def quota_scope(db, user, team_id=None, lock=False):
    # Team plan has one pooled allowance, including the owner's personal jobs.
    if team_id:
        team = team_access(db, user, team_id)
        owner_id = team.owner_id
    else: owner_id = user.id
    if lock: lock_user(db, owner_id)
    owner = db.get(User, owner_id)
    plan = effective_plan(db, owner)
    if team_id: team_access(db, user, team_id)  # recheck after locking
    return owner, plan

def usage_count(db, owner):
    start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    owned_teams = select(Team.id).where(Team.owner_id == owner.id)
    return db.scalar(select(func.count()).select_from(UsageEvent).join(Job, Job.id == UsageEvent.job_id).where(
        UsageEvent.created_at >= start, UsageEvent.event.in_(("format", "export")), Job.status != "failed",
        or_(UsageEvent.team_id.in_(owned_teams), (UsageEvent.team_id.is_(None)) & (UsageEvent.user_id == owner.id)))) or 0

def quota_view(db, user, team_id=None):
    owner, plan = quota_scope(db, user, team_id)
    used = usage_count(db, owner)
    return {"plan": asdict(plan), "used": used, "remaining": max(0, plan.monthly_jobs-used), "period": "UTC calendar month"}

def reserve_job(db, user, job, team_id=None):
    owner, plan = quota_scope(db, user, team_id, lock=True)
    used = usage_count(db, owner)
    if used >= plan.monthly_jobs:
        raise HTTPException(402, {"code": "quota_exceeded", "message": f"Monthly job limit reached ({used}/{plan.monthly_jobs}). Open Plans & team to upgrade or wait for next month.", "upgradeUrl": "/#plans", "limit": plan.monthly_jobs, "used": used})
    db.add(job); db.flush()
    db.add(UsageEvent(user_id=user.id, team_id=team_id, job_id=job.id, event="export" if job.kind == "pdf" else "format"))
