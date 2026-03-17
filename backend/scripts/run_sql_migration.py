import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from dotenv import load_dotenv


def load_environment():
    """
    Loads .env from:
    - backend/.env
    - project root .env
    Automatically.
    Prints which file was loaded.
    """
    base_dir = Path(__file__).resolve().parent.parent

    backend_env = base_dir / ".env"
    root_env = base_dir.parent / ".env"

    if backend_env.exists():
        load_dotenv(backend_env)
        print(f"Loaded environment from: {backend_env}")
    elif root_env.exists():
        load_dotenv(root_env)
        print(f"Loaded environment from: {root_env}")
    else:
        print("WARNING: No .env file found. Using system environment variables.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_sql_migration.py <path_to_sql_file>")
        sys.exit(1)

    load_environment()

    path = sys.argv[1]
    db_url = os.getenv("DATABASE_URL", "").strip()

    if not db_url:
        print("ERROR: DATABASE_URL is not set (even after loading .env).")
        sys.exit(2)

    sql_path = Path(path)
    if not sql_path.exists():
        print(f"ERROR: SQL file not found: {path}")
        sys.exit(3)

    sql = sql_path.read_text(encoding="utf-8").strip()
    if not sql:
        print("ERROR: SQL file is empty.")
        sys.exit(4)

    engine = create_engine(db_url, future=True)

    print(f"Applying migration: {path}")
    with engine.begin() as conn:
        conn.execute(text(sql))

    print("Migration applied successfully.")


if __name__ == "__main__":
    main()
