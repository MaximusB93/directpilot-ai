from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Base(DeclarativeBase):
    pass


engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True) if settings.database_url else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False) if engine else None


def init_db() -> None:
    if engine is None:
        return
    import app.models  # noqa: F401
    import app.models_workflow  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_mvp_schema()


def ensure_mvp_schema() -> None:
    if engine is None:
        return

    # Temporary MVP schema patch for existing Postgres databases.
    # Replace this with Alembic migrations once migrations are introduced.
    statements = [
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_status VARCHAR(64) NOT NULL DEFAULT 'never_synced'",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_error TEXT",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS yandex_account_id VARCHAR(36)",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS target_cpa INTEGER",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS main_goal_id VARCHAR(64)",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS notes TEXT",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_db() -> Generator[Session | None, None, None]:
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
