import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from app.config import Settings
from app.main import create_app

SECRET = "x" * 40


def build(tmp_path, **overrides):
    values = dict(data_dir=tmp_path / "data", session_secret=SECRET, local_mode=False, workers=0); values.update(overrides)
    return create_app(Settings(**values))


def stored_files(client):
    root = client.app.state.settings.data_dir / "files"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


@pytest.fixture
def client(tmp_path):
    """Single-user local mode, as used by the desktop launcher."""
    with TestClient(build(tmp_path, local_mode=True)) as c: yield c


@pytest.fixture
def cloud(tmp_path):
    """Multi-user mode: every request needs a signed-in account."""
    with TestClient(build(tmp_path)) as c: yield c


def sign_up(app, email="a@example.com", password="correct horse battery"):
    c = TestClient(app)
    response = c.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return c


def run_apply(client, doc, profile=None, **extra):
    """Queue a format job, run the queue to completion in-process, and return {id, jobId, status, error, report}."""
    body = ({} if profile is None else {"profile": profile}) | extra
    response = client.post(f"/api/uploads/{doc}/apply", json=body)
    assert response.status_code == 202, response.text
    client.app.state.runner.run_pending()
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    return {"id": job["outputId"], "jobId": job["id"], "status": job["status"], "error": job["error"], "report": job["report"]}
