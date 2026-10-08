import os
from alembic import context
from sqlalchemy import create_engine

from app.db import make_engine
from app.config import normalize_database_url
from app.db_models import Base

config = context.config
target_metadata = Base.metadata
url = normalize_database_url(config.get_main_option("sqlalchemy.url") if config.attributes.get("explicit_url") else os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url")))


def run_migrations_online():
    engine = make_engine(url)
    with engine.connect() as connection:
        sqlite = url.startswith("sqlite")
        # Batch table rebuilds must not SET NULL/CASCADE existing foreign keys
        # when Alembic drops the old table. Disable only on this migration connection.
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        try:
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=sqlite)
            with context.begin_transaction():
                context.run_migrations()
                if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("Migration left invalid foreign-key references.")
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            if sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    engine.dispose()


def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
