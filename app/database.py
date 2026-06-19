import logging
import os
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

    connection_string = os.getenv("POSTGRES_CONNECTION_STRING") or os.getenv("DATABASE_URL")
    if connection_string:
        return connection_string.replace("postgres://", "postgresql+psycopg://", 1)

    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST")
    name = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME")
    user = os.getenv("POSTGRES_USER") or os.getenv("POSTGRES_USERNAME") or os.getenv("DB_USER")
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD")
    if not all([host, name, user, password]):
        logger.warning("PostgreSQL environment is not configured, using SQLite fallback")
        return "sqlite:////tmp/events_aggregator.db"

    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    return (
        "postgresql+psycopg://"
        f"{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(name)}"
    )


engine = create_engine(build_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
