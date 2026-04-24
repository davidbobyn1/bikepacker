"""
Database session factory.

All DB access across the application must go through get_db().
Never create raw connections outside this module.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from backend.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and ensures cleanup.
    Yields None if the database is unreachable so routes degrade gracefully."""
    db = SessionLocal()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        yield db
    except Exception:
        db.close()
        yield None
        return
    finally:
        try:
            db.close()
        except Exception:
            pass
