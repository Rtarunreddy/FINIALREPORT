"""FastAPI dependencies: database session, storage, signed-in user."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import User
from .security import COOKIE, read_session

LOCAL_EMAIL = "local@report-ready.local"


def get_db(request: Request):
    with request.app.state.session_factory() as db: yield db


def get_settings(request: Request): return request.app.state.settings
def get_storage(request: Request): return request.app.state.storage


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = request.app.state.settings
    if settings.local_mode:
        user = db.scalars(select(User).where(User.email == LOCAL_EMAIL)).first()
        if user is None: user = User(email=LOCAL_EMAIL, plan_id="free"); db.add(user); db.commit()
        return user
    user_id = read_session(settings.session_secret, request.cookies.get(COOKIE), settings.session_seconds)
    user = db.get(User, user_id) if user_id else None
    if user is None: raise HTTPException(401, "Sign in to use Report Ready.")
    return user
