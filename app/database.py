import logging
from collections.abc import Generator
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def build_database_url() -> str:
    if settings.database_url:
        return settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)

    if not all(
        [
            settings.postgres_host,
            settings.postgres_db,
            settings.postgres_user,
            settings.postgres_password,
        ]
    ):
        logger.warning("PostgreSQL environment is not configured, using SQLite fallback")
        return "sqlite:////tmp/events_aggregator.db"

    return (
        "postgresql+psycopg://"
        f"{quote_plus(settings.postgres_user)}:"
        f"{quote_plus(settings.postgres_password)}@"
        f"{settings.postgres_host}:{settings.postgres_port}/"
        f"{quote_plus(settings.postgres_db)}"
    )


engine = create_engine(build_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
