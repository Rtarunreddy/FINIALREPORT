"""Environment-driven settings. Build one explicitly in tests; the app reads the environment otherwise."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUE = {"1", "true", "yes", "on"}


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in TRUE


def normalize_database_url(url: str) -> str:
    """Hosting providers hand out postgres:// URLs; SQLAlchemy needs an explicit driver."""
    if url.startswith("postgres://"): return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"): return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass
class Settings:
    data_dir: Path = ROOT / "data"
    database_url: str = ""                 # empty -> SQLite file inside data_dir
    storage_backend: str = "local"         # "local" or "s3"
    s3_bucket: str = ""
    s3_endpoint: str = ""                  # set for Cloudflare R2, MinIO and other S3-compatible stores
    s3_region: str = "auto"
    local_mode: bool = False               # single-user desktop mode: no sign-in
    session_secret: str = ""
    cookie_secure: bool = False
    session_seconds: int = 60 * 60 * 24 * 7
    free_retention_hours: int = 24
    paid_retention_hours: int = 24 * 90
    max_upload: int = 25 * 1024 * 1024
    max_unzipped: int = 150 * 1024 * 1024
    auto_migrate: bool = True
    workers: int = 2                       # in-process job workers; 0 when a separate `python -m app.worker` runs them
    job_poll_seconds: float = 1.0
    stale_job_minutes: int = 15            # a job still "running" after this long is marked failed on startup
    max_active_jobs: int = 5               # queued + running jobs one user may have at once
    pdf_timeout_seconds: int = 120
    soffice_path: str = ""                 # LibreOffice executable; auto-detected when empty
    billing_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price: str = ""
    stripe_team_price: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    public_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"])

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        if not self.database_url: self.database_url = f"sqlite:///{(self.data_dir / 'report_ready.db').as_posix()}"
        self.database_url = normalize_database_url(self.database_url)
        self.free_retention_hours = max(1, min(168, int(self.free_retention_hours)))
        if not self.local_mode and len(self.session_secret) < 32:
            raise RuntimeError("REPORT_READY_SESSION_SECRET (32+ characters) is required unless REPORT_READY_LOCAL_MODE=1.")
        if self.storage_backend not in {"local", "s3"}: raise RuntimeError("REPORT_READY_STORAGE must be 'local' or 's3'.")
        if self.storage_backend == "s3" and not self.s3_bucket: raise RuntimeError("REPORT_READY_S3_BUCKET is required for S3 storage.")

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            data_dir=Path(env("REPORT_READY_DATA", ROOT / "data")), database_url=env("DATABASE_URL", ""),
            storage_backend=env("REPORT_READY_STORAGE", "local").lower(), s3_bucket=env("REPORT_READY_S3_BUCKET", ""),
            s3_endpoint=env("REPORT_READY_S3_ENDPOINT", ""), s3_region=env("REPORT_READY_S3_REGION", "auto"),
            local_mode=_flag("REPORT_READY_LOCAL_MODE"), session_secret=env("REPORT_READY_SESSION_SECRET", ""),
            cookie_secure=_flag("REPORT_READY_COOKIE_SECURE"),
            free_retention_hours=int(env("REPORT_READY_RETENTION_HOURS", "24")),
            paid_retention_hours=int(env("REPORT_READY_PAID_RETENTION_HOURS", str(24 * 90))),
            auto_migrate=_flag("REPORT_READY_AUTO_MIGRATE", True), workers=int(env("REPORT_READY_WORKERS", "2")),
            billing_enabled=_flag("REPORT_READY_BILLING_ENABLED"),
            stripe_secret_key=env("STRIPE_SECRET_KEY", ""), stripe_webhook_secret=env("STRIPE_WEBHOOK_SECRET", ""),
            stripe_pro_price=env("STRIPE_PRO_PRICE_ID", ""), stripe_team_price=env("STRIPE_TEAM_PRICE_ID", ""),
            soffice_path=env("REPORT_READY_SOFFICE", ""),
            google_client_id=env("GOOGLE_CLIENT_ID", ""), google_client_secret=env("GOOGLE_CLIENT_SECRET", ""),
            public_url=env("REPORT_READY_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"))
