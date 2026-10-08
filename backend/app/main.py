from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import make_engine, make_session_factory, run_migrations
from .routers import auth, documents, jobs, misc, templates, billing, teams
from .security import LoginThrottle
from .worker import JobRunner
from .services import Cleaner
from .storage import make_storage

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def create_app(settings: Settings | None = None, storage=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        if settings.auto_migrate: run_migrations(settings.database_url)
        app.state.engine = make_engine(settings.database_url)
        app.state.session_factory = make_session_factory(app.state.engine)
        app.state.storage = storage or make_storage(settings)
        app.state.runner = JobRunner(settings, app.state.session_factory, app.state.storage); app.state.runner.start()
        await run_in_threadpool(app.state.cleaner.run, app.state.session_factory, app.state.storage, True)
        yield
        await run_in_threadpool(app.state.runner.stop)
        app.state.engine.dispose()

    app = FastAPI(title="Report Ready", version=misc.VERSION, lifespan=lifespan)
    app.state.settings, app.state.cleaner, app.state.throttle = settings, Cleaner(), LoginThrottle()
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def clean_up_expired(request: Request, call_next):
        if request.url.path.startswith("/api"):
            try: await run_in_threadpool(request.app.state.cleaner.run, request.app.state.session_factory, request.app.state.storage)
            except Exception: LOG.exception("Expired-document cleanup failed")
        return await call_next(request)

    for module in (auth, misc, documents, templates, jobs, billing, teams): app.include_router(module.router)
    dist = ROOT.parent / "frontend" / "dist"
    if dist.is_dir(): app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def __getattr__(name):
    """uvicorn app.main:app builds the app lazily, so importing this module never needs production secrets."""
    if name == "app":
        global _app
        if _app is None: _app = create_app()
        return _app
    raise AttributeError(name)


_app = None
