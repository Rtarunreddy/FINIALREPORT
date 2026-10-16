import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.security import COOKIE, hash_password, make_session, read_session, verify_password
from app.db_models import Document, Feedback, Job, Team, TeamInvite, TeamMember, Template, User
from conftest import SECRET, build, sign_up, stored_files
from test_infra import docx_bytes


def test_register_login_logout_cycle(cloud):
    assert cloud.get("/api/auth/status").json() == {"required": True, "authenticated": False, "retentionHours": 24, "user": None, "googleEnabled": False, "passwordResetEnabled": False}
    r = cloud.post("/api/auth/register", json={"email": "  Ada@Example.COM ", "password": "correct horse battery"})
    assert r.status_code == 200 and r.json()["user"] == {"email": "ada@example.com", "plan": "free"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert cloud.get("/api/auth/status").json()["authenticated"] is True
    cloud.post("/api/auth/logout")
    assert cloud.get("/api/auth/status").json()["authenticated"] is False
    assert cloud.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse battery"}).status_code == 200
    assert cloud.get("/api/auth/me").json()["email"] == "ada@example.com"


@pytest.mark.parametrize("email,password", [("not-an-email", "correct horse battery"), ("a@example.com", "short"), ("a@example.com", "x" * 129)])
def test_registration_validation(cloud, email, password):
    assert cloud.post("/api/auth/register", json={"email": email, "password": password}).status_code == 400


def test_duplicate_email_and_wrong_password(cloud):
    body = {"email": "a@example.com", "password": "correct horse battery"}
    assert cloud.post("/api/auth/register", json=body).status_code == 200
    assert cloud.post("/api/auth/register", json={**body, "email": "A@example.com"}).status_code == 409
    other = TestClient(cloud.app)
    assert other.post("/api/auth/login", json={**body, "password": "wrong password!!"}).status_code == 401
    assert other.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever password"}).status_code == 401


def test_login_throttle(cloud):
    body = {"email": "a@example.com", "password": "wrong password!!"}
    codes = [cloud.post("/api/auth/login", json=body).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


def test_password_reset_is_generic_and_one_time(tmp_path, monkeypatch):
    from app.routers import auth

    delivered = []
    monkeypatch.setattr(auth, "send_password_reset_email", lambda settings, email, token: delivered.append((email, token)))
    app = build(tmp_path, resend_api_key="test-key", email_from="Report Ready <no-reply@example.com>",
                public_url="https://reports.example.com")
    with TestClient(app) as client:
        registered = client.post("/api/auth/register", json={"email": "ada@example.com", "password": "correct horse battery"})
        assert registered.status_code == 200
        unknown = client.post("/api/auth/password-reset/request", json={"email": "unknown@example.com"})
        known = client.post("/api/auth/password-reset/request", json={"email": "ada@example.com"})
        assert unknown.status_code == known.status_code == 200
        assert unknown.json() == known.json()
        assert len(delivered) == 1 and delivered[0][0] == "ada@example.com"
        from app.db_models import PasswordResetToken, utcnow
        token = delivered[0][1]
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with app.state.session_factory() as db:
            assert db.get(PasswordResetToken, token_hash) is not None
            assert db.get(PasswordResetToken, token) is None

        response = client.post("/api/auth/password-reset/confirm", json={"token": token, "password": "a brand new password"})
        assert response.status_code == 200
        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "a brand new password"}).status_code == 200
        reused = client.post("/api/auth/password-reset/confirm", json={"token": token, "password": "another new password"})
        assert reused.status_code == 400 and "invalid or has expired" in reused.json()["detail"]

        client.post("/api/auth/password-reset/request", json={"email": "ada@example.com"})
        expired_hash = hashlib.sha256(delivered[-1][1].encode()).hexdigest()
        with app.state.session_factory() as db:
            expired = db.get(PasswordResetToken, expired_hash)
            expired.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        response = client.post("/api/auth/password-reset/confirm", json={"token": delivered[-1][1], "password": "another new password"})
        assert response.status_code == 400 and "invalid or has expired" in response.json()["detail"]


def test_password_reset_requires_email_configuration(cloud):
    response = cloud.post("/api/auth/password-reset/request", json={"email": "a@example.com"})
    assert response.status_code == 503


def test_session_token_tamper_and_expiry():
    token = make_session(SECRET, "user-1", now=1000)
    assert read_session(SECRET, token, 60, now=1030) == "user-1"
    assert read_session(SECRET, token, 60, now=1100) is None
    assert read_session(SECRET, token, 60, now=900) is None
    assert read_session("y" * 40, token, 60, now=1030) is None
    assert read_session(SECRET, token.replace("user-1", "user-2"), 60, now=1030) is None
    assert read_session(SECRET, "garbage", 60) is None and read_session(SECRET, None, 60) is None


def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery")
    assert stored != hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored) and not verify_password("nope nope nope", stored)
    assert not verify_password("anything", None)


def test_forged_cookie_is_rejected(cloud):
    cloud.cookies.set(COOKIE, make_session("z" * 40, "someone"))
    assert cloud.get("/api/profiles").status_code == 401


def test_secret_is_required_outside_local_mode(tmp_path):
    from app.config import Settings
    with pytest.raises(RuntimeError): Settings(data_dir=tmp_path, session_secret="short")
    Settings(data_dir=tmp_path, local_mode=True)


def test_local_mode_needs_no_sign_in(client):
    assert client.get("/api/auth/status").json()["required"] is False
    assert client.get("/api/profiles").status_code == 200
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse battery"}).status_code == 400


def test_account_deletion_removes_files_records_and_owned_team(cloud):
    owner = sign_up(cloud.app)
    member = sign_up(cloud.app, "member@example.com")
    team_id = owner.post("/api/teams", json={"name": "Research"}).json()["id"]
    member_team_id = member.post("/api/teams", json={"name": "Member workspace"}).json()["id"]
    invite = owner.post(f"/api/teams/{team_id}/invites", json={"email": "member@example.com"}).json()
    assert member.post("/api/teams/accept", json={"token": invite["token"]}).status_code == 200
    incoming_invite = member.post(f"/api/teams/{member_team_id}/invites", json={"email": "a@example.com"})
    assert incoming_invite.status_code == 201
    profile = owner.get("/api/profiles").json()[0]
    assert owner.post(f"/api/teams/{team_id}/profiles", json=profile).status_code == 200
    upload = owner.post("/api/uploads", files={"file": ("report.docx", docx_bytes())})
    assert upload.status_code == 200
    assert owner.post(f"/api/uploads/{upload.json()['id']}/apply", json={}).status_code == 202
    assert stored_files(owner)
    with cloud.app.state.session_factory() as db:
        owner_row = db.scalar(select(User).where(User.email == "a@example.com"))
        db.add(Feedback(user_id=owner_row.id, rating=5, comment="private test comment"))
        db.commit()

    denied = owner.request("DELETE", "/api/auth/account", json={"email": "a@example.com", "password": "wrong password"})
    assert denied.status_code == 401
    mismatch = owner.request("DELETE", "/api/auth/account", json={"email": "other@example.com", "password": "correct horse battery"})
    assert mismatch.status_code == 400

    deleted = owner.request("DELETE", "/api/auth/account", json={"email": "a@example.com", "password": "correct horse battery"})
    assert deleted.status_code == 200
    assert "Max-Age=0" in deleted.headers["set-cookie"]
    assert owner.get("/api/auth/status").json()["authenticated"] is False
    assert [team["id"] for team in member.get("/api/teams").json()] == [member_team_id]
    assert stored_files(owner) == []
    with cloud.app.state.session_factory() as db:
        assert db.query(User).filter(User.email == "a@example.com").count() == 0
        assert db.query(Team).filter(Team.id == team_id).count() == 0
        assert db.query(TeamMember).filter(TeamMember.team_id == team_id).count() == 0
        assert db.query(TeamInvite).filter(TeamInvite.team_id == team_id).count() == 0
        assert db.query(Template).filter(Template.team_id == team_id).count() == 0
        assert db.query(Document).count() == 0
        assert db.query(Job).count() == 0
        assert db.query(TeamInvite).filter(TeamInvite.email == "a@example.com").count() == 0
        assert db.query(Feedback).count() == 0


def test_account_deletion_requires_password_for_password_accounts(cloud):
    owner = sign_up(cloud.app)
    response = owner.request("DELETE", "/api/auth/account", json={"email": "a@example.com"})
    assert response.status_code == 401
    assert owner.get("/api/auth/status").json()["authenticated"] is True


def test_every_api_route_requires_sign_in(cloud):
    public = {("GET", "/api/plans"), ("GET", "/api/health"), ("GET", "/api/auth/status"), ("POST", "/api/auth/register"), ("POST", "/api/auth/login"),
              ("POST", "/api/auth/logout"), ("GET", "/api/auth/google/login"), ("GET", "/api/auth/google/callback"),
              ("POST", "/api/auth/password-reset/request"), ("POST", "/api/auth/password-reset/confirm")}
    ident = "00000000-0000-4000-8000-000000000000"
    checked = 0
    for path, methods in cloud.app.openapi()["paths"].items():
        if not path.startswith("/api"): continue
        for method in (m.upper() for m in methods):
            if (method, path) in public: continue
            response = cloud.request(method, path.replace("{id}", ident))
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"; checked += 1
    assert checked >= 10
