from __future__ import annotations

import logging
import random
import sqlite3
import string
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.analytics")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "call_analytics.db"


def get_db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    target_path = db_path or get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_analytics_db(db_path: Path | None = None) -> None:
    """Initialize the calls analytics table in SQLite."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                call_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds INTEGER DEFAULT 0,
                channel TEXT NOT NULL,
                outcome TEXT NOT NULL,
                success_reason TEXT,
                failure_reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
    conn.close()


def generate_call_id(
    existing_conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
) -> str:
    """Generate a unique human-readable call ID in format CALL-YYYYMMDD-XXXX."""
    date_str = datetime.now().strftime("%Y%m%d")
    chars = string.ascii_uppercase + string.digits

    if existing_conn is None:
        init_analytics_db(db_path)
    conn = existing_conn or get_connection(db_path)
    should_close = existing_conn is None

    try:
        for _ in range(50):
            suffix = "".join(random.choices(chars, k=4))
            candidate = f"CALL-{date_str}-{suffix}"
            try:
                cursor = conn.execute(
                    "SELECT 1 FROM calls WHERE call_id = ?",
                    (candidate,),
                )
                if not cursor.fetchone():
                    return candidate
            except sqlite3.OperationalError:
                return candidate
        # Fallback with timestamp microsecond
        micro = datetime.now().strftime("%f")[:4]
        return f"CALL-{date_str}-{micro}"
    finally:
        if should_close:
            conn.close()


def start_call_record(
    call_id: str,
    channel: str = "browser",
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Create initial persistent call record when session starts."""
    init_analytics_db(db_path)
    conn = get_connection(db_path)

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_channel = "sip" if "sip" in channel.lower() else "browser"

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO calls (
                    call_id,
                    started_at,
                    ended_at,
                    duration_seconds,
                    channel,
                    outcome,
                    success_reason,
                    failure_reason,
                    created_at
                )
                VALUES (?, ?, NULL, 0, ?, 'failed', NULL, 'Call in progress or ended before completion', ?)
                """,
                (call_id, started_at, normalized_channel, started_at),
            )
        logger.info(
            "Created initial call record: call_id=%s, channel=%s",
            call_id,
            normalized_channel,
        )
        return {
            "call_id": call_id,
            "started_at": started_at,
            "channel": normalized_channel,
            "outcome": "failed",
        }
    finally:
        conn.close()


def finalize_call_record(
    call_id: str,
    ended_at: str,
    duration_seconds: int,
    outcome: str,
    success_reason: str | None = None,
    failure_reason: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Update the same call record when the call session ends."""
    init_analytics_db(db_path)
    conn = get_connection(db_path)

    clean_outcome = "success" if outcome.lower() == "success" else "failed"
    clean_duration = max(0, int(duration_seconds))

    try:
        with conn:
            conn.execute(
                """
                UPDATE calls
                SET ended_at = ?,
                    duration_seconds = ?,
                    outcome = ?,
                    success_reason = ?,
                    failure_reason = ?
                WHERE call_id = ?
                """,
                (
                    ended_at,
                    clean_duration,
                    clean_outcome,
                    success_reason if clean_outcome == "success" else None,
                    failure_reason if clean_outcome == "failed" else None,
                    call_id,
                ),
            )
        logger.info(
            "Finalized call record: call_id=%s, outcome=%s, duration=%ds",
            call_id,
            clean_outcome,
            clean_duration,
        )
        return {
            "call_id": call_id,
            "ended_at": ended_at,
            "duration_seconds": clean_duration,
            "outcome": clean_outcome,
            "success_reason": success_reason,
            "failure_reason": failure_reason,
        }
    finally:
        conn.close()


def get_analytics_summary(db_path: Path | None = None) -> dict[str, int]:
    """Query the persistent database and return exact real-time call counts."""
    init_analytics_db(db_path)
    conn = get_connection(db_path)

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM calls")
        total_row = cursor.fetchone()
        total_calls = total_row[0] if total_row else 0

        cursor.execute("SELECT COUNT(*) FROM calls WHERE outcome = 'success'")
        success_row = cursor.fetchone()
        successful_calls = success_row[0] if success_row else 0

        cursor.execute("SELECT COUNT(*) FROM calls WHERE outcome = 'failed'")
        failed_row = cursor.fetchone()
        failed_calls = failed_row[0] if failed_row else 0

        return {
            "total_calls": int(total_calls),
            "successful_calls": int(successful_calls),
            "failed_calls": int(failed_calls),
        }
    finally:
        conn.close()


def get_recent_calls(
    limit: int = 50,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve sanitized recent call records without any sensitive data."""
    init_analytics_db(db_path)
    conn = get_connection(db_path)

    try:
        cursor = conn.execute(
            """
            SELECT
                call_id,
                started_at,
                ended_at,
                duration_seconds,
                channel,
                outcome,
                success_reason,
                failure_reason
            FROM calls
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
