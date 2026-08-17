from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    creator TEXT NOT NULL DEFAULT '',
    theme TEXT NOT NULL DEFAULT '직업·공정',
    status TEXT NOT NULL DEFAULT 'new',
    rights_status TEXT NOT NULL DEFAULT 'unknown',
    hook_score INTEGER NOT NULL DEFAULT 3,
    explainability_score INTEGER NOT NULL DEFAULT 3,
    novelty_score INTEGER NOT NULL DEFAULT 3,
    editability_score INTEGER NOT NULL DEFAULT 3,
    traceability_score INTEGER NOT NULL DEFAULT 3,
    risk_score INTEGER NOT NULL DEFAULT 3,
    total_score REAL NOT NULL DEFAULT 50,
    notes TEXT NOT NULL DEFAULT '',
    rights_evidence TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    analysis_summary TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    analysis_detail TEXT NOT NULL DEFAULT '',
    script_ideas TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_theme ON candidates(theme);
CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(total_score DESC);
CREATE TABLE IF NOT EXISTS mobile_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mobile_tokens_hash ON mobile_tokens(token_hash);
CREATE TABLE IF NOT EXISTS discovery_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    feed_url TEXT NOT NULL UNIQUE,
    theme TEXT NOT NULL DEFAULT '기타',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    last_error TEXT NOT NULL DEFAULT ''
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(candidates)")}
        additions = {
            "source": "TEXT NOT NULL DEFAULT 'manual'",
            "analysis_summary": "TEXT NOT NULL DEFAULT ''",
            "thumbnail_url": "TEXT NOT NULL DEFAULT ''",
            "analysis_status": "TEXT NOT NULL DEFAULT 'pending'",
            "analysis_detail": "TEXT NOT NULL DEFAULT ''",
            "script_ideas": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE candidates ADD COLUMN {name} {definition}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def list_candidates(self, status: str = "", theme: str = "") -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if theme:
            clauses.append("theme = ?")
            params.append(theme)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM candidates {where} ORDER BY total_score DESC, created_at DESC"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_candidate(self, candidate_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
            return dict(row) if row else None

    def create_candidate(self, data: dict) -> dict:
        fields = tuple(data.keys())
        placeholders = ", ".join("?" for _ in fields)
        query = f"INSERT INTO candidates ({', '.join(fields)}) VALUES ({placeholders})"
        with self.connect() as connection:
            cursor = connection.execute(query, tuple(data[field] for field in fields))
            candidate_id = cursor.lastrowid
        return self.get_candidate(candidate_id)  # type: ignore[return-value]

    def update_candidate(self, candidate_id: int, data: dict) -> dict | None:
        if not data:
            return self.get_candidate(candidate_id)
        assignments = ", ".join(f"{field} = ?" for field in data)
        query = f"UPDATE candidates SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        with self.connect() as connection:
            connection.execute(query, (*data.values(), candidate_id))
        return self.get_candidate(candidate_id)

    def delete_candidate(self, candidate_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
            return cursor.rowcount > 0

    def create_mobile_token(self, label: str, token_hash: str) -> dict:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO mobile_tokens (label, token_hash) VALUES (?, ?)", (label, token_hash)
            )
            row = connection.execute(
                "SELECT id, label, created_at, last_used_at, revoked_at FROM mobile_tokens WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def list_mobile_tokens(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, label, created_at, last_used_at, revoked_at FROM mobile_tokens ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def validate_mobile_token(self, token_hash: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM mobile_tokens WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)
            ).fetchone()
            if not row:
                return False
            connection.execute(
                "UPDATE mobile_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],)
            )
            return True

    def revoke_mobile_token(self, token_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE mobile_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE id = ? AND revoked_at IS NULL",
                (token_id,),
            )
            return cursor.rowcount > 0

    def create_discovery_source(self, label: str, feed_url: str, theme: str) -> dict:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO discovery_sources (label, feed_url, theme) VALUES (?, ?, ?)",
                (label, feed_url, theme),
            )
            row = connection.execute("SELECT * FROM discovery_sources WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def list_discovery_sources(self, enabled_only: bool = False) -> list[dict]:
        where = "WHERE enabled = 1" if enabled_only else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM discovery_sources {where} ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_discovery_source(self, source_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM discovery_sources WHERE id = ?", (source_id,)).fetchone()
            return dict(row) if row else None

    def delete_discovery_source(self, source_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM discovery_sources WHERE id = ?", (source_id,))
            return cursor.rowcount > 0

    def mark_discovery_checked(self, source_id: int, error: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE discovery_sources SET last_checked_at = CURRENT_TIMESTAMP, last_error = ? WHERE id = ?",
                (error[:1000], source_id),
            )
