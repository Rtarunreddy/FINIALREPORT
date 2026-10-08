from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session
from ..plans import effective_plan

from ..db_models import User
from ..deps import current_user, get_db
from ..security import COOKIE, check_password_strength, hash_password, make_session, normalize_email, read_session, verify_password
from ..services import retention_hours

router = APIRouter(prefix="/api/auth")
GOOGLE_AUTH, GOOGLE_TOKEN, GOOGLE_USERINFO = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://openidconnect.googleapis.com/v1/userinfo"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


def attach_session(response, request: Request, user: User):
    s = request.app.state.settings
    response.set_cookie(COOKIE, make_session(s.session_secret, user.id), max_age=s.session_seconds, httponly=True, secure=s.cookie_secure, samesite="lax", path="/")
    return response


def public_user(user: User | None):
    return {"email": user.email, "plan": effective_plan(object_session(user), user).id} if user else None


def session_user(request: Request, db: Session) -> User | None:
    s = request.app.state.settings
    uid = read_session(s.session_secret, request.cookies.get(COOKIE), s.session_seconds) if not s.local_mode else None
    return db.get(User, uid) if uid else None


@router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    s = request.app.state.settings
    user = current_user(request, db) if s.local_mode else session_user(request, db)
    hours = retention_hours(s, user) if user else s.free_retention_hours
    return {"required": not s.local_mode, "authenticated": user is not None, "retentionHours": hours,
            "user": public_user(user) if not s.local_mode else None, "googleEnabled": s.google_enabled}


@router.post("/register")
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if request.app.state.settings.local_mode: raise HTTPException(400, "Sign-in is not used in local mode.")
    try: email = normalize_email(body.email); check_password_strength(body.password)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    user = User(email=email, password_hash=hash_password(body.password), plan_id="free")
    try: db.add(user); db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    return attach_session(JSONResponse({"authenticated": True, "user": public_user(user)}), request, user)


@router.post("/login")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if request.app.state.settings.local_mode: return {"authenticated": True}
    throttle = request.app.state.throttle
    email = (body.email or "").strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    if throttle.blocked(key): raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")
    user = db.scalars(select(User).where(User.email == email)).first()
    if not verify_password(body.password, user.password_hash if user else None):
        throttle.fail(key); raise HTTPException(401, "Incorrect email or password.")
    throttle.reset(key)
    return attach_session(JSONResponse({"authenticated": True, "user": public_user(user)}), request, user)


@router.post("/logout")
def logout():
    response = JSONResponse({"authenticated": False}); response.delete_cookie(COOKIE, path="/"); return response


@router.get("/me")
def me(user: User = Depends(current_user)): return public_user(user)


def exchange_google_code(settings, code: str) -> dict:
    """Trade an authorization code for the verified Google profile. Isolated so tests can replace it."""
    redirect = settings.public_url + "/api/auth/google/callback"
    with httpx.Client(timeout=10) as client:
        token = client.post(GOOGLE_TOKEN, data={"code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                                                "redirect_uri": redirect, "grant_type": "authorization_code"})
        token.raise_for_status()
        info = client.get(GOOGLE_USERINFO, headers={"Authorization": "Bearer " + token.json()["access_token"]})
        info.raise_for_status()
        return info.json()


@router.get("/google/login")
def google_login(request: Request):
    s = request.app.state.settings
    if not s.google_enabled: raise HTTPException(404, "Google sign-in is not configured.")
    state = secrets.token_urlsafe(24)
    query = urlencode({"client_id": s.google_client_id, "redirect_uri": s.public_url + "/api/auth/google/callback", "response_type": "code",
                       "scope": "openid email", "state": state, "prompt": "select_account"})
    response = RedirectResponse(f"{GOOGLE_AUTH}?{query}")
    response.set_cookie("report_ready_oauth_state", state, max_age=600, httponly=True, secure=s.cookie_secure, samesite="lax", path="/api/auth/google")
    return response


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    s = request.app.state.settings
    if not s.google_enabled: raise HTTPException(404, "Google sign-in is not configured.")
    expected = request.cookies.get("report_ready_oauth_state", "")
    if not code or not expected or not hmac.compare_digest(state, expected): raise HTTPException(400, "Google sign-in could not be verified. Please try again.")
    try: info = exchange_google_code(s, code)
    except Exception as exc: raise HTTPException(400, "Google sign-in failed. Please try again.") from exc
    sub, email = str(info.get("sub", "")), str(info.get("email", "")).strip().lower()
    if not sub or not email or info.get("email_verified") is not True: raise HTTPException(400, "Your Google account must have a verified email address.")
    user = db.scalars(select(User).where(User.google_sub == sub)).first()
    if user is None:
        user = db.scalars(select(User).where(User.email == email)).first()  # safe: Google verified this email
        if user is None: user = User(email=email, google_sub=sub, plan_id="free")
        else: user.google_sub = sub
        db.add(user); db.commit()
    response = attach_session(RedirectResponse("/", status_code=303), request, user)
    response.delete_cookie("report_ready_oauth_state", path="/api/auth/google")
    return response
