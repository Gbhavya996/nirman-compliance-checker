"""
history_service.py
──────────────────
SQLite-backed scan history for the Nirman compliance system.

DB file: backend/nirman_history.db  (auto-created on first use)
Auto-purge: records older than 30 days are deleted on each save.

Schema
------
inspections(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,      -- ISO-8601 timestamp
    mode        TEXT    NOT NULL,      -- 'image' | 'url' | 'both'
    url         TEXT,                  -- product URL (if provided)
    overall     TEXT,                  -- summary.overall
    pass_count  INTEGER,
    fail_count  INTEGER,
    warning_count INTEGER,
    image_b64   TEXT,                  -- base64 encoded image (nullable)
    image_mime  TEXT,
    result_json TEXT NOT NULL          -- full JSON result
)
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# DB path: same directory as this file's parent (backend/)
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nirman_history.db")

# Auto-purge records older than this many days
_PURGE_DAYS = 30


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    """Create table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT NOT NULL,
                mode          TEXT NOT NULL,
                url           TEXT,
                overall       TEXT,
                pass_count    INTEGER DEFAULT 0,
                fail_count    INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                image_b64     TEXT,
                image_mime    TEXT,
                result_json   TEXT NOT NULL
            )
        """)
        conn.commit()


# Initialise on import
try:
    _init_db()
    logger.info("History DB initialised at %s", os.path.abspath(_DB_PATH))
except Exception as _e:
    logger.error("Failed to initialise history DB: %s", _e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_inspection(
    mode: str,
    result: dict,
    url: Optional[str] = None,
    image_b64: Optional[str] = None,
    image_mime: Optional[str] = None,
) -> Optional[int]:
    """
    Persist a completed inspection to the DB.

    Parameters
    ----------
    mode      : 'image' | 'url' | 'both'
    result    : full JSON-serialisable result dict from the analyze endpoint
    url       : product URL (if provided)
    image_b64 : base64 image (stored for history re-display)
    image_mime: MIME type of image

    Returns
    -------
    int  – new record ID, or None on failure
    """
    summary = result.get("summary", {})
    ts = datetime.now(timezone.utc).isoformat()

    try:
        with _get_conn() as conn:
            # Auto-purge old records
            cutoff = (datetime.now(timezone.utc) - timedelta(days=_PURGE_DAYS)).isoformat()
            conn.execute("DELETE FROM inspections WHERE ts < ?", (cutoff,))

            cur = conn.execute(
                """
                INSERT INTO inspections
                    (ts, mode, url, overall, pass_count, fail_count, warning_count,
                     image_b64, image_mime, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    mode,
                    url,
                    summary.get("overall"),
                    summary.get("pass_count", 0),
                    summary.get("fail_count", 0),
                    summary.get("warning_count", 0),
                    image_b64,
                    image_mime,
                    json.dumps(result, default=str),
                ),
            )
            conn.commit()
            record_id = cur.lastrowid
            logger.info("Saved inspection #%d (mode=%s, overall=%s)", record_id, mode, summary.get("overall"))
            return record_id
    except Exception as exc:
        logger.error("Failed to save inspection: %s", exc, exc_info=True)
        return None


def list_inspections(limit: int = 50) -> list:
    """
    Return the most recent *limit* inspections (lightweight — no result_json).

    Returns
    -------
    List of dicts: { id, ts, mode, url, overall, pass_count, fail_count, warning_count }
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, mode, url, overall, pass_count, fail_count, warning_count
                FROM inspections
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("Failed to list inspections: %s", exc)
        return []


def get_inspection(record_id: int) -> Optional[dict]:
    """
    Return a single inspection record including the full result JSON.

    Returns
    -------
    dict | None
    """
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM inspections WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            d["result"] = json.loads(d.pop("result_json"))
            return d
    except Exception as exc:
        logger.error("Failed to get inspection %d: %s", record_id, exc)
        return None


def delete_all() -> bool:
    """Clear the entire history. Returns True on success."""
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM inspections")
            conn.commit()
        return True
    except Exception as exc:
        logger.error("Failed to clear history: %s", exc)
        return False
