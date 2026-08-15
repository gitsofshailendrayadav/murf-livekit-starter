from __future__ import annotations

import logging
import random
import re
import sqlite3
import string
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.escalation")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "escalations.db"

# Regex patterns for sanitizing sensitive financial information
SENSITIVE_PATTERNS = [
    # 4-6 digit standalone PIN / OTP
    (
        re.compile(r"\b(?:otp|pin|cvv)\s*[:=]?\s*(\d{3,6})\b", re.IGNORECASE),
        r"[REDACTED_CREDENTIAL]",
    ),
    # 12 to 19 digit card numbers or bank account numbers
    (re.compile(r"\b(?:\d[ -]*?){12,19}\b"), r"[REDACTED_NUMBER]"),
    # 12-digit Aadhaar pattern
    (re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), r"[REDACTED_AADHAAR]"),
    # 10-character PAN pattern (5 letters, 4 digits, 1 letter)
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE), r"[REDACTED_PAN]"),
]


def get_db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    target_path = db_path or get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_escalations_db(db_path: Path | None = None) -> None:
    """Initialize the escalations table in SQLite."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS escalations (
                reference_id TEXT PRIMARY KEY,
                caller_name TEXT,
                issue_type TEXT,
                short_summary TEXT,
                what_happened TEXT,
                what_fin_saathi_checked TEXT,
                urgency TEXT,
                caller_language TEXT,
                preferred_follow_up_method TEXT,
                consent_given INTEGER,
                created_at TEXT,
                status TEXT DEFAULT 'open'
            )
            """
        )
    conn.close()


def generate_reference_id(
    existing_conn: sqlite3.Connection | None = None,
    db_path: Path | None = None,
) -> str:
    """Generate a unique human-readable reference ID in format FS-YYYYMMDD-XXXXX."""
    date_str = datetime.now().strftime("%Y%m%d")
    chars = string.ascii_uppercase + string.digits

    if existing_conn is None:
        init_escalations_db(db_path)
    conn = existing_conn or get_connection(db_path)
    should_close = existing_conn is None

    try:
        for _ in range(50):
            suffix = "".join(random.choices(chars, k=5))
            candidate = f"FS-{date_str}-{suffix}"
            try:
                cursor = conn.execute(
                    "SELECT 1 FROM escalations WHERE reference_id = ?",
                    (candidate,),
                )
                if not cursor.fetchone():
                    return candidate
            except sqlite3.OperationalError:
                return candidate
        # Fallback with timestamp microsecond if loop finishes
        micro = datetime.now().strftime("%f")[:5]
        return f"FS-{date_str}-{micro}"
    finally:
        if should_close:
            conn.close()


def sanitize_sensitive_info(text: str) -> str:
    """Sanitize any obvious passwords, OTPs, PINs, bank accounts, card numbers, or IDs."""
    if not text:
        return ""

    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized.strip()


def create_escalation_record(
    *,
    caller_name: str = "",
    issue_type: str = "",
    short_summary: str = "",
    what_happened: str = "",
    what_fin_saathi_checked: str = "",
    urgency: str = "medium",
    caller_language: str = "English",
    preferred_follow_up_method: str = "not specified",
    consent_given: bool = False,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Create and persist a new escalation record in SQLite after verifying consent."""

    if not consent_given:
        logger.warning(
            "Escalation rejected: user consent was not given (consent_given=False)."
        )
        return {
            "success": False,
            "error": "consent_required",
            "message": "Cannot create escalation request without explicit user consent.",
        }

    init_escalations_db(db_path)
    conn = get_connection(db_path)

    try:
        ref_id = generate_reference_id(conn)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Sanitize sensitive fields before storage
        clean_summary = sanitize_sensitive_info(short_summary)
        clean_happened = sanitize_sensitive_info(what_happened)
        clean_checked = sanitize_sensitive_info(what_fin_saathi_checked)
        clean_caller = sanitize_sensitive_info(
            caller_name.strip() if caller_name else "Unknown"
        )
        clean_urgency = urgency.strip().lower() if urgency else "medium"
        if clean_urgency not in ("low", "medium", "high"):
            clean_urgency = "high" if "fraud" in issue_type.lower() else "medium"

        clean_language = caller_language.strip() if caller_language else "English"
        clean_followup = (
            preferred_follow_up_method.strip()
            if preferred_follow_up_method
            else "not specified"
        )

        with conn:
            conn.execute(
                """
                INSERT INTO escalations (
                    reference_id,
                    caller_name,
                    issue_type,
                    short_summary,
                    what_happened,
                    what_fin_saathi_checked,
                    urgency,
                    caller_language,
                    preferred_follow_up_method,
                    consent_given,
                    created_at,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref_id,
                    clean_caller,
                    issue_type.strip(),
                    clean_summary,
                    clean_happened,
                    clean_checked,
                    clean_urgency,
                    clean_language,
                    clean_followup,
                    1 if consent_given else 0,
                    created_at,
                    "open",
                ),
            )

        logger.info(
            "Created escalation record: ref=%s, type=%s, urgency=%s, caller=%s",
            ref_id,
            issue_type,
            clean_urgency,
            clean_caller,
        )

        return {
            "success": True,
            "reference_id": ref_id,
            "caller_name": clean_caller,
            "issue_type": issue_type,
            "short_summary": clean_summary,
            "urgency": clean_urgency,
            "caller_language": clean_language,
            "preferred_follow_up_method": clean_followup,
            "status": "open",
            "created_at": created_at,
            "message": (
                f"Support request created successfully. Reference ID: {ref_id}."
            ),
        }
    finally:
        conn.close()


def get_all_escalations(
    status: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve stored escalation records."""
    init_escalations_db(db_path)
    conn = get_connection(db_path)

    try:
        if status:
            cursor = conn.execute(
                """
                SELECT * FROM escalations
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                (status,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM escalations
                ORDER BY created_at DESC
                """
            )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
