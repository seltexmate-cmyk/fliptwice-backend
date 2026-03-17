# backend/app/config.py
"""
Central configuration for FlipTwice.

Goals:
- Load .env exactly once (no scattered load_dotenv calls).
- Keep configuration in one place for maintainability.
- Avoid magic numbers by documenting defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


def _load_env_once() -> None:
    """
    Loads environment variables from backend/.env if present.

    We do this once at import time so all modules can rely on os.getenv().
    """
    backend_dir = Path(__file__).resolve().parents[1]  # .../backend/app -> .../backend
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)


_load_env_once()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Check backend/.env or your environment variables.")
    return value


# --- Database ---
DATABASE_URL: str = require_env("DATABASE_URL")

# --- Auth / JWT ---
SECRET_KEY: str = require_env("SECRET_KEY")
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

# Token expiration (minutes). Default is reasonable for a private SaaS.
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))