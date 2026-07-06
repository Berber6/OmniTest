"""SQLite database setup with SQLAlchemy session management."""

import logging

from sqlalchemy import create_engine, text as sa_text

logger = logging.getLogger(__name__)
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
    Also auto-migrates: adds any new columns that exist in ORM models
    but are missing from the actual SQLite table.
    """
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine, checkfirst=True)

    # Auto-migrate: add columns defined in ORM but missing from SQLite tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing_cols:
                col_type = column.type.compile(dialect=engine.dialect)
                default = ""
                if column.default is not None:
                    default = f" DEFAULT {column.default.arg}"
                elif column.server_default is not None:
                    default = f" DEFAULT {column.server_default.arg}"
                alter_sql = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{default}"
                with engine.connect() as conn:
                    conn.execute(sa_text(alter_sql))
                    conn.commit()
                logger.info("Auto-migrated: added column '%s' to table '%s'", column.name, table.name)


def get_session() -> Session:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()