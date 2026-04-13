import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    settings = get_settings()
    db_url = settings.DATABASE_URL

    # Ensure the data directory exists for SQLite
    if db_url.startswith("sqlite"):
        # Extract the file path from the URL
        db_path = db_url.replace("sqlite:///", "")
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        echo=False,
    )
    return engine


engine = get_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    # Import all models so SQLAlchemy registers them before creating tables
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def run_migrations() -> None:
    """Apply Alembic migrations (creates or upgrades schema)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    alembic_ini = backend_root / "alembic.ini"
    cfg = Config(str(alembic_ini))
    command.upgrade(cfg, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
