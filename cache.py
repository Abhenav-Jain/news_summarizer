"""
Lightweight SQLite cache + history store.

Two purposes:
1. Cache search/summary results so repeated queries don't re-hit the paid APIs
   (keeps usage on the free tier).
2. Persist a history of every summary so the UI can show past results.

A single SQLite file (`news_cache.db`) is used. No external services needed.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

DB_PATH = "news_cache.db"

# How long a cached result stays "fresh" (seconds). News goes stale fast,
# so default to 6 hours. Repeated identical queries within this window are free.
CACHE_TTL_SECONDS = 6 * 60 * 60


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key   TEXT UNIQUE,
                topic       TEXT NOT NULL,
                model       TEXT NOT NULL,
                payload     TEXT NOT NULL,   -- full JSON result
                created_at  REAL NOT NULL
            )
            """
        )


def _make_key(topic: str, model: str, max_results: int) -> str:
    raw = f"{topic.strip().lower()}|{model}|{max_results}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached(
    topic: str, model: str, max_results: int, ttl: int = CACHE_TTL_SECONDS
) -> Optional[Dict[str, Any]]:
    """Return a cached result if a fresh one exists, else None."""
    key = _make_key(topic, model, max_results)
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload, created_at FROM history WHERE cache_key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    if time.time() - row["created_at"] > ttl:
        return None  # stale
    return json.loads(row["payload"])


def save_result(
    topic: str, model: str, max_results: int, payload: Dict[str, Any]
) -> None:
    """Insert or replace a result in the history/cache table."""
    key = _make_key(topic, model, max_results)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO history (cache_key, topic, model, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload = excluded.payload,
                created_at = excluded.created_at
            """,
            (key, topic, model, json.dumps(payload), time.time()),
        )


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent summaries, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT topic, model, payload, created_at FROM history "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        item = json.loads(r["payload"])
        item["_topic"] = r["topic"]
        item["_model"] = r["model"]
        item["_created_at"] = r["created_at"]
        out.append(item)
    return out


def clear_history() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM history")