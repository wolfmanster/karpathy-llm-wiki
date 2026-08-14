"""Idempotent SQLite state for attachment versions."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS attachment_state (
              library_id TEXT NOT NULL,
              parent_item_key TEXT NOT NULL,
              attachment_key TEXT NOT NULL,
              attachment_version INTEGER NOT NULL,
              status TEXT NOT NULL,
              successful_version INTEGER,
              artifact_path TEXT,
              error_summary TEXT,
              last_request_id TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (library_id, attachment_key)
            );
            CREATE INDEX IF NOT EXISTS idx_attachment_parent
              ON attachment_state(library_id, parent_item_key);
            """
        )
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(attachment_state)")}
        if "successful_version" not in columns:
            self.db.execute("ALTER TABLE attachment_state ADD COLUMN successful_version INTEGER")
            self.db.execute(
                "UPDATE attachment_state SET successful_version=attachment_version WHERE status='SUCCESS'"
            )
        self.db.commit()

    def get(self, library_id: str, attachment_key: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM attachment_state WHERE library_id=? AND attachment_key=?",
            (library_id, attachment_key),
        ).fetchone()

    def remove_attachment(self, library_id: str, parent_item_key: str, attachment_key: str) -> bool:
        cursor = self.db.execute(
            "DELETE FROM attachment_state WHERE library_id=? AND parent_item_key=? AND attachment_key=?",
            (library_id, parent_item_key, attachment_key),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def record(self, *, library_id: str, parent_item_key: str, attachment_key: str, attachment_version: int,
               status: str, request_id: str, updated_at: str, artifact_path: str | None = None,
               error_summary: str | None = None, successful_version: int | None = None) -> None:
        self.db.execute(
            """
            INSERT INTO attachment_state(library_id,parent_item_key,attachment_key,attachment_version,status,
              successful_version,artifact_path,error_summary,last_request_id,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(library_id,attachment_key) DO UPDATE SET
              parent_item_key=excluded.parent_item_key, attachment_version=excluded.attachment_version,
              status=excluded.status,
              successful_version=COALESCE(excluded.successful_version, attachment_state.successful_version),
              artifact_path=CASE
                WHEN excluded.successful_version IS NOT NULL THEN excluded.artifact_path
                WHEN attachment_state.successful_version IS NULL THEN excluded.artifact_path
                ELSE attachment_state.artifact_path
              END,
              error_summary=excluded.error_summary, last_request_id=excluded.last_request_id,
              updated_at=excluded.updated_at
            """,
            (library_id, parent_item_key, attachment_key, attachment_version, status,
             successful_version, artifact_path, error_summary, request_id, updated_at),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
