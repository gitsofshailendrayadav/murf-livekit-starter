from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    from escalation import (
        create_escalation_record,
        generate_reference_id,
        get_all_escalations,
        init_escalations_db,
        sanitize_sensitive_info,
    )
except ImportError:
    from src.escalation import (
        create_escalation_record,
        generate_reference_id,
        get_all_escalations,
        init_escalations_db,
        sanitize_sensitive_info,
    )


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_escalations.db"
    init_escalations_db(db_file)
    return db_file


def test_consent_rejection(temp_db: Path) -> None:
    """Escalation tool must reject creation if consent_given is False."""
    result = create_escalation_record(
        caller_name="Shailendra",
        issue_type="unauthorized_transaction",
        short_summary="Unauthorized UPI charge",
        what_happened="User saw ₹5000 debited without doing transaction",
        urgency="high",
        consent_given=False,
        db_path=temp_db,
    )

    assert result["success"] is False
    assert result["error"] == "consent_required"

    all_records = get_all_escalations(db_path=temp_db)
    assert len(all_records) == 0


def test_successful_escalation_creation(temp_db: Path) -> None:
    """Escalation tool creates a persistent record with valid reference ID when consent is True."""
    result = create_escalation_record(
        caller_name="Pooja",
        issue_type="possible_financial_fraud",
        short_summary="Suspicious UPI withdrawal",
        what_happened="Received fake SMS and money deducted",
        what_fin_saathi_checked="Informed user about banking support and fraud reporting",
        urgency="high",
        caller_language="Hindi",
        preferred_follow_up_method="phone",
        consent_given=True,
        db_path=temp_db,
    )

    assert result["success"] is True
    ref_id = result["reference_id"]
    assert ref_id.startswith("FS-")
    assert re.match(r"^FS-\d{8}-[A-Z0-9]{5}$", ref_id)

    records = get_all_escalations(db_path=temp_db)
    assert len(records) == 1
    rec = records[0]
    assert rec["reference_id"] == ref_id
    assert rec["caller_name"] == "Pooja"
    assert rec["urgency"] == "high"
    assert rec["caller_language"] == "Hindi"
    assert rec["status"] == "open"


def test_sensitive_info_sanitization() -> None:
    """Ensure sensitive credentials like OTP, PIN, card numbers, Aadhaar, PAN are redacted."""
    raw_text = (
        "My card number 4111 2222 3333 4444 was charged. "
        "The otp: 123456 was received. "
        "My pin 9876 was entered. "
        "Aadhaar is 1234 5678 9012 and PAN is ABCDE1234F."
    )

    sanitized = sanitize_sensitive_info(raw_text)
    assert "4111 2222 3333 4444" not in sanitized
    assert "123456" not in sanitized
    assert "9876" not in sanitized
    assert "1234 5678 9012" not in sanitized
    assert "ABCDE1234F" not in sanitized
    assert "[REDACTED" in sanitized


def test_reference_id_uniqueness(temp_db: Path) -> None:
    """Generate multiple reference IDs and verify format and uniqueness."""
    ids = {generate_reference_id(db_path=temp_db) for _ in range(50)}
    assert len(ids) == 50
    for rid in ids:
        assert re.match(r"^FS-\d{8}-[A-Z0-9]{5}$", rid)
