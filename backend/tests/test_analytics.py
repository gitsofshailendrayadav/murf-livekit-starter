from __future__ import annotations

import re
from pathlib import Path

import pytest

from analytics import (
    finalize_call_record,
    generate_call_id,
    get_analytics_summary,
    get_recent_calls,
    init_analytics_db,
    start_call_record,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_call_analytics.db"
    init_analytics_db(db_file)
    return db_file


def test_empty_db_metrics(temp_db: Path) -> None:
    """Empty database should report exactly 0 for all metrics."""
    metrics = get_analytics_summary(db_path=temp_db)
    assert metrics["total_calls"] == 0
    assert metrics["successful_calls"] == 0
    assert metrics["failed_calls"] == 0

    recent = get_recent_calls(db_path=temp_db)
    assert len(recent) == 0


def test_call_id_format_and_uniqueness(temp_db: Path) -> None:
    """Generated call IDs must be unique and match CALL-YYYYMMDD-XXXX."""
    ids = {generate_call_id(db_path=temp_db) for _ in range(50)}
    assert len(ids) == 50
    for cid in ids:
        assert re.match(r"^CALL-\d{8}-[A-Z0-9]{4}$", cid)


def test_single_call_successful_lifecycle(temp_db: Path) -> None:
    """A single call created and finalized as success should update the same record."""
    call_id = generate_call_id(db_path=temp_db)
    start_call_record(call_id=call_id, channel="browser", db_path=temp_db)

    # In progress, counts as 1 call, 0 success, 1 failed (default before success)
    in_progress_metrics = get_analytics_summary(db_path=temp_db)
    assert in_progress_metrics["total_calls"] == 1
    assert in_progress_metrics["successful_calls"] == 0
    assert in_progress_metrics["failed_calls"] == 1

    # Finalize with success
    finalize_call_record(
        call_id=call_id,
        ended_at="2026-08-15 19:00:45",
        duration_seconds=45,
        outcome="success",
        success_reason="Financial question answered conversationally",
        db_path=temp_db,
    )

    final_metrics = get_analytics_summary(db_path=temp_db)
    assert final_metrics["total_calls"] == 1
    assert final_metrics["successful_calls"] == 1
    assert final_metrics["failed_calls"] == 0

    records = get_recent_calls(db_path=temp_db)
    assert len(records) == 1
    rec = records[0]
    assert rec["call_id"] == call_id
    assert rec["channel"] == "browser"
    assert rec["outcome"] == "success"
    assert rec["duration_seconds"] == 45
    assert rec["success_reason"] == "Financial question answered conversationally"
    assert rec["failure_reason"] is None


def test_multiple_calls_accuracy(temp_db: Path) -> None:
    """Accurately aggregate multiple calls with mixed channels and outcomes."""
    # Call 1: Browser success
    c1 = generate_call_id(db_path=temp_db)
    start_call_record(call_id=c1, channel="browser", db_path=temp_db)
    finalize_call_record(
        call_id=c1,
        ended_at="2026-08-15 19:10:00",
        duration_seconds=30,
        outcome="success",
        success_reason="Eligibility checked",
        db_path=temp_db,
    )

    # Call 2: SIP failed (immediate disconnect)
    c2 = generate_call_id(db_path=temp_db)
    start_call_record(call_id=c2, channel="sip", db_path=temp_db)
    finalize_call_record(
        call_id=c2,
        ended_at="2026-08-15 19:12:00",
        duration_seconds=5,
        outcome="failed",
        failure_reason="Caller disconnected before completing a meaningful financial interaction",
        db_path=temp_db,
    )

    # Call 3: Browser success
    c3 = generate_call_id(db_path=temp_db)
    start_call_record(call_id=c3, channel="browser", db_path=temp_db)
    finalize_call_record(
        call_id=c3,
        ended_at="2026-08-15 19:15:00",
        duration_seconds=60,
        outcome="success",
        success_reason="Budgeting advice provided",
        db_path=temp_db,
    )

    metrics = get_analytics_summary(db_path=temp_db)
    assert metrics["total_calls"] == 3
    assert metrics["successful_calls"] == 2
    assert metrics["failed_calls"] == 1

    records = get_recent_calls(db_path=temp_db)
    assert len(records) == 3


def test_privacy_and_data_fields(temp_db: Path) -> None:
    """Ensure records do not store or expose any sensitive credentials or unauthorized fields."""
    c = generate_call_id(db_path=temp_db)
    start_call_record(call_id=c, channel="browser", db_path=temp_db)
    finalize_call_record(
        call_id=c,
        ended_at="2026-08-15 19:20:00",
        duration_seconds=12,
        outcome="success",
        success_reason="General budgeting concept explained",
        db_path=temp_db,
    )

    records = get_recent_calls(db_path=temp_db)
    assert len(records) == 1
    rec = records[0]

    allowed_keys = {
        "call_id",
        "started_at",
        "ended_at",
        "duration_seconds",
        "channel",
        "outcome",
        "success_reason",
        "failure_reason",
    }
    assert set(rec.keys()) == allowed_keys

    forbidden_tokens = [
        "otp",
        "pin",
        "cvv",
        "password",
        "aadhaar",
        "pan",
        "transcript",
        "card",
        "account",
    ]
    for key in rec:
        for token in forbidden_tokens:
            assert token not in key.lower()
