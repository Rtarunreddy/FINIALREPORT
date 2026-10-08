import pytest
from fastapi.testclient import TestClient

from app.security import COOKIE, hash_password, make_session, read_session, verify_password
from conftest import SECRET, build, sign_up


def test_register_login_logout_cycle(cloud):
    assert cloud.get("/api/auth/status").json() == {"required": True, "authenticated": False, "retentionHours": 24, "user": None, "googleEnabled": False}
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


def test_every_api_route_requires_sign_in(cloud):
    public = {("GET", "/api/billing/plans"), ("POST", "/api/billing/webhook"), ("GET", "/api/health"), ("GET", "/api/auth/status"), ("POST", "/api/auth/register"), ("POST", "/api/auth/login"),
              ("POST", "/api/auth/logout"), ("GET", "/api/auth/google/login"), ("GET", "/api/auth/google/callback")}
    ident = "00000000-0000-4000-8000-000000000000"
    checked = 0
    for path, methods in cloud.app.openapi()["paths"].items():
        if not path.startswith("/api"): continue
        for method in (m.upper() for m in methods):
            if (method, path) in public: continue
            response = cloud.request(method, path.replace("{id}", ident))
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"; checked += 1
    assert checked >= 10
