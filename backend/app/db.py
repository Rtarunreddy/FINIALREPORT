"""Engine, sessions and programmatic Alembic migrations."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(connection, _record):
            cursor = connection.cursor(); cursor.execute("PRAGMA foreign_keys=ON"); cursor.execute("PRAGMA journal_mode=WAL"); cursor.close()
        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine):
    return sessionmaker(engine, expire_on_commit=False)


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["explicit_url"] = True
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def run_migrations(url: str):
    command.upgrade(alembic_config(url), "head")
