from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_infra import docx_bytes

POSTGRES_URL = os.environ.get("REPORT_READY_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="PostgreSQL integration URL is not configured")


def test_postgres_migrations_and_concurrent_quota_reservations(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=POSTGRES_URL or "",
        session_secret="x" * 40,
        local_mode=False,
        workers=0,
        max_active_jobs=100,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"email": "postgres-integration@example.test", "password": "correct horse battery"},
        )
        assert registered.status_code == 200
        uploaded = client.post("/api/uploads", files={"file": ("report.docx", docx_bytes())})
        assert uploaded.status_code == 200
        endpoint = f"/api/uploads/{uploaded.json()['id']}/apply"
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: client.post(endpoint, json={}), range(8)))
        assert sorted(response.status_code for response in responses) == [202] * 5 + [402] * 3
        assert client.get("/api/plans/usage").json()["used"] == 5
