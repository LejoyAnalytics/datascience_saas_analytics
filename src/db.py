"""Database connection — single place that knows how to reach MySQL/MariaDB.

Defaults match a local XAMPP install (root / no password on localhost:3306).
Override via environment variables (or a .env file) for any other setup.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "saas_revenue_forecast")


def _url(database: str | None = None) -> str:
    db = database if database is not None else DB_NAME
    auth = f"{DB_USER}:{DB_PASSWORD}" if DB_PASSWORD else DB_USER
    return f"mysql+pymysql://{auth}@{DB_HOST}:{DB_PORT}/{db}"


def get_server_engine() -> Engine:
    """Engine with no database selected — used only to create the database itself."""
    return create_engine(_url(database=""), isolation_level="AUTOCOMMIT")


def get_engine() -> Engine:
    return create_engine(_url(), pool_pre_ping=True)


def ensure_database_exists() -> None:
    engine = get_server_engine()
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4"))
    engine.dispose()
