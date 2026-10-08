import hashlib
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db_models import Team, TeamInvite, TeamMember, Template, User, utcnow
from ..deps import current_user, get_db
from ..models import Profile
from ..plans import effective_plan, lock_user, team_access
from ..security import normalize_email

router = APIRouter(prefix="/api/teams")

class TeamBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
class InviteBody(BaseModel):
    email: str
class AcceptBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)

@router.get("")
def list_teams(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "role": m.role, "active": effective_plan(db, db.get(User, t.owner_id)).id == "team"}
        for t, m in db.execute(select(Team, TeamMember).join(TeamMember).where(TeamMember.user_id == user.id))]

@router.post("", status_code=201)
def create_team(body: TeamBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    if effective_plan(db, user).id != "team": raise HTTPException(403, "Upgrade to Team in Plans & team to create a shared workspace.")
    if db.scalar(select(Team.id).where(Team.owner_id == user.id)): raise HTTPException(409, "Your Team plan includes one workspace.")
    if not body.name.strip(): raise HTTPException(422, "Enter a team name.")
    team = Team(name=body.name.strip(), owner_id=user.id); db.add(team); db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner")); db.commit()
    return {"id": team.id, "name": team.name}

@router.get("/{team_id}/members")
def members(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, paid=False)
    return [{"id": u.id, "email": u.email, "role": m.role} for u, m in db.execute(select(User, TeamMember).join(TeamMember).where(TeamMember.team_id == team_id))]

@router.post("/{team_id}/invites", status_code=201)
def invite(team_id: str, body: InviteBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, owner=True); lock_user(db, user.id)
    team_access(db, user, team_id, owner=True)
    try: email = normalize_email(body.email)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    existing = db.scalar(select(User.id).join(TeamMember).where(TeamMember.team_id == team_id, User.email == email))
    if existing: raise HTTPException(409, "This person is already a member.")
    for old in db.scalars(select(TeamInvite).where(TeamInvite.team_id == team_id, TeamInvite.email == email, TeamInvite.accepted_at.is_(None))): db.delete(old)
    db.flush()
    members = db.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id))
    pending = db.scalar(select(func.count()).select_from(TeamInvite).where(TeamInvite.team_id == team_id, TeamInvite.accepted_at.is_(None), TeamInvite.expires_at > utcnow()))
    if members + pending >= effective_plan(db, user).seats: raise HTTPException(409, "All five seats are occupied or reserved. Remove a member or revoke an invitation.")
    token = secrets.token_urlsafe(32)
    row = TeamInvite(team_id=team_id, email=email, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=utcnow()+timedelta(days=7))
    db.add(row); db.commit()
    return {"id": row.id, "token": token, "expiresAt": row.expires_at.isoformat()+"Z", "message": "Share this one-time code privately with the invited person. It expires in seven days."}

@router.get("/{team_id}/invites")
def invites(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, owner=True, paid=False)
    return [{"id": i.id, "email": i.email, "expiresAt": i.expires_at.isoformat()+"Z"} for i in db.scalars(select(TeamInvite).where(TeamInvite.team_id == team_id, TeamInvite.accepted_at.is_(None), TeamInvite.expires_at > utcnow()))]

@router.delete("/{team_id}/invites/{invite_id}")
def revoke(team_id: str, invite_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, owner=True, paid=False); lock_user(db, user.id)
    row = db.get(TeamInvite, invite_id)
    if not row or row.team_id != team_id: raise HTTPException(404, "Invitation not found.")
    db.delete(row); db.commit(); return {"message": "Invitation revoked."}

@router.post("/accept")
def accept(body: AcceptBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    digest = hashlib.sha256(body.token.encode()).hexdigest()
    row = db.scalar(select(TeamInvite).where(TeamInvite.token_hash == digest))
    if not row: raise HTTPException(404, "Invitation not found.")
    team = db.get(Team, row.team_id); lock_user(db, team.owner_id)
    row = db.scalar(select(TeamInvite).where(TeamInvite.token_hash == digest).execution_options(populate_existing=True))
    if not row: raise HTTPException(404, "Invitation was revoked.")
    if row.accepted_at or row.expires_at <= utcnow() or row.email != user.email:
        raise HTTPException(403, "Use an unexpired invitation for your signed-in email.")
    owner = db.get(User, team.owner_id)
    plan = effective_plan(db, owner)
    if plan.id != "team": raise HTTPException(403, "This team's subscription is not active.")
    if db.get(TeamMember, (team.id, user.id)): raise HTTPException(409, "You are already a member.")
    count = db.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id))
    if count >= plan.seats: raise HTTPException(409, "This team is full.")
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="member")); row.accepted_at = utcnow(); db.commit()
    return {"message": "Team joined.", "teamId": team.id}

@router.delete("/{team_id}/members/{member_id}")
def remove(team_id: str, member_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team = team_access(db, user, team_id, paid=False); lock_user(db, team.owner_id)
    if member_id == team.owner_id: raise HTTPException(400, "The owner cannot leave the team.")
    if user.id not in (team.owner_id, member_id): raise HTTPException(403, "Only the owner can remove another member.")
    row = db.get(TeamMember, (team_id, member_id))
    if not row: raise HTTPException(404, "Member not found.")
    db.delete(row); db.commit(); return {"message": "Member removed."}

@router.get("/{team_id}/profiles")
def profiles(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id)
    return [row.profile_json | {"id": row.id} for row in db.scalars(select(Template).where(Template.team_id == team_id))]

@router.post("/{team_id}/profiles")
def save_profile(team_id: str, profile: Profile, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, owner=True); lock_user(db, user.id); team_access(db, user, team_id, owner=True)
    # Always copy: a personal or other team's template must never be moved or overwritten.
    row = Template(team_id=team_id, owner_user_id=None, name=profile.name, profile_json=profile.model_dump())
    db.add(row); db.commit(); return row.profile_json | {"id": row.id}

@router.delete("/{team_id}/profiles/{profile_id}")
def delete_profile(team_id: str, profile_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_access(db, user, team_id, owner=True, paid=False); lock_user(db, user.id)
    row = db.get(Template, profile_id)
    if not row or row.team_id != team_id: raise HTTPException(404, "Template not found.")
    db.delete(row); db.commit(); return {"message": "Shared template deleted."}
