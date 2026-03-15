from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import pool

from alembic import context

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

# ── DB URL: same absolute path as store.py ────────────────────────────────────
# env.py lives at <project_root>/alembic/env.py
_DB_PATH = Path(__file__).resolve().parent.parent / "gp_triage.db"
_DB_URL = f"sqlite:///{_DB_PATH}"


def run_migrations_offline() -> None:
    context.configure(
        url=_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = sa.create_engine(
        _DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
