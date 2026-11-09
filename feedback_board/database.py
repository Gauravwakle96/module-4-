import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import Settings

Connection = sqlite3.Connection | psycopg.Connection[dict[str, Any]]
DATABASE_ERRORS = (sqlite3.Error, psycopg.Error, OSError)

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS module3_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 60),
    message TEXT NOT NULL CHECK (length(trim(message)) BETWEEN 1 AND 500),
    created_at TEXT NOT NULL
);
"""


class FeedbackQuotaReached(Exception):
    """The configured storage quota has been reached."""


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.postgres = settings.database_url is not None

    @property
    def kind(self) -> str:
        return "postgresql" if self.postgres else "sqlite-local"

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        if self.settings.database_url:
            with psycopg.connect(
                self.settings.database_url.get_secret_value(),
                connect_timeout=5,
                sslmode=self.settings.database_sslmode,
                prepare_threshold=None,
                row_factory=dict_row,
            ) as connection:
                connection.execute("SET statement_timeout = '5s'")
                yield connection
        else:
            local = sqlite3.connect(self.settings.local_db_path, timeout=5)
            local.row_factory = sqlite3.Row
            try:
                with local:
                    yield local
            finally:
                local.close()

    def initialize(self) -> None:
        if not self.postgres:
            self.settings.local_db_path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.execute(SQLITE_SCHEMA)
        self.check()

    def check(self) -> None:
        with self.connect() as connection:
            connection.execute("SELECT id FROM module3_feedback LIMIT 1")

    def recent(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, message, created_at, COUNT(*) OVER () AS total "
                "FROM module3_feedback ORDER BY id DESC LIMIT 10"
            ).fetchall()
            return {
                "total": int(rows[0]["total"]) if rows else 0,
                "items": [
                    {key: row[key] for key in ("id", "name", "message", "created_at")}
                    for row in rows
                ],
            }

    def add(self, name: str, message: str) -> dict[str, Any]:
        with self.connect() as connection:
            # Serialize the count and insert so concurrent writes cannot exceed the quota.
            connection.execute(
                "LOCK TABLE module3_feedback IN EXCLUSIVE MODE"
                if self.postgres
                else "BEGIN IMMEDIATE"
            )
            count = connection.execute("SELECT COUNT(*) AS total FROM module3_feedback").fetchone()
            if count is not None and count["total"] >= self.settings.feedback_limit:
                raise FeedbackQuotaReached
            created_at = datetime.now(UTC).isoformat()
            row = connection.execute(
                (
                    "INSERT INTO module3_feedback (name, message, created_at) "
                    "VALUES (%s, %s, %s) RETURNING id, name, message, created_at"
                    if self.postgres
                    else "INSERT INTO module3_feedback (name, message, created_at) "
                    "VALUES (?, ?, ?) RETURNING id, name, message, created_at"
                ),
                (name, message, created_at),
            ).fetchone()
            if row is None:
                raise RuntimeError("Database did not return the saved feedback.")
            return dict(row)
