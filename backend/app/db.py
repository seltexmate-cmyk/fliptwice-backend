# backend/app/db.py
"""
Database setup for FlipTwice.

- Engine + SessionLocal live here (single source of truth).
- get_db() is the FastAPI dependency for request-scoped sessions.
- Base is used by ORM models and Alembic metadata.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()