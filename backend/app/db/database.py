"""SQLite database setup with SQLAlchemy session management."""

from pathlib import Path
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# Ensure the data directory exists before creating the engine.
settings.ensure_dirs()

engine = create_engine(
    f"sqlite:///{settings.sqlite_path}",
    echo=False,
    connect_args={"check_same_thread": False},
    pool_size=20,
    max_overflow=10,
)

# Enable WAL mode for concurrent read/write (critical for multiple background agents)
with engine.connect() as conn:
    conn.execute(sa_text("PRAGMA journal_mode=WAL"))
    conn.execute(sa_text("PRAGMA busy_timeout=5000"))
    conn.commit()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables defined in ORM models if they don't exist.

    Uses create_all with checkfirst=True so existing data is preserved.
    For schema changes, any new columns will be added by SQLAlchemy's
    create_all (it only creates missing tables/columns).
    """
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine, checkfirst=True)


def get_session() -> Session:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()