import sqlite3
from datetime import datetime
from pathlib import Path


# Database will be created inside the backend folder
DB_PATH = Path(__file__).resolve().parent.parent / "finsaathi_memory.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS callers (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            language_preference TEXT,
            schemes_checked TEXT,
            eligibility_answers TEXT,
            last_interaction TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def get_caller(user_id: str):
    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT
            user_id,
            name,
            language_preference,
            schemes_checked,
            eligibility_answers,
            last_interaction
        FROM callers
        WHERE user_id = ?
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "name": row[1],
        "language_preference": row[2],
        "schemes_checked": row[3],
        "eligibility_answers": row[4],
        "last_interaction": row[5],
    }


def save_caller(
    user_id: str,
    name: str,
    language_preference: str = "",
    schemes_checked: str = "",
    eligibility_answers: str = "",
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO callers (
            user_id,
            name,
            language_preference,
            schemes_checked,
            eligibility_answers,
            last_interaction
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            language_preference = excluded.language_preference,
            schemes_checked = excluded.schemes_checked,
            eligibility_answers = excluded.eligibility_answers,
            last_interaction = excluded.last_interaction
        """,
        (
            user_id,
            name,
            language_preference,
            schemes_checked,
            eligibility_answers,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()


init_db()