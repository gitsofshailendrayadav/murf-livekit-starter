from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Any

from livekit import api, rtc
from livekit.agents import JobContext

logger = logging.getLogger("agent.telephony")

DEFAULT_LINPHONE_DESTINATION = "sip:shailendraxyadav@sip.linphone.org"
SIP_OUTBOUND_TRUNK_ENV = "LIVEKIT_SIP_OUTBOUND_TRUNK_ID"
SIP_DESTINATION_RE = re.compile(
    r"^(?:sip:)?[A-Za-z0-9_.!~*'()%+-]+(?:@[A-Za-z0-9.-]+(?::[0-9]{1,5})?)?$"
)


def validate_sip_destination(destination: str) -> str:
    """Validate and extract the SIP user or phone number for sip_call_to."""

    normalized = destination.strip()

    if not SIP_DESTINATION_RE.fullmatch(normalized):
        raise ValueError(
            "Outbound calling only accepts SIP URIs like "
            "sip:user@example.com or a SIP username for this Day 6 test."
        )

    user_part = normalized
    if user_part.startswith("sip:"):
        user_part = user_part[4:]
    if "@" in user_part:
        user_part = user_part.split("@", 1)[0]

    if ":" in user_part:
        raise ValueError("SIP URI userinfo must not include credentials.")

    return user_part


def create_participant_identity() -> str:
    return f"phone_user_{uuid.uuid4().hex[:8]}"


def get_outbound_trunk_id() -> str:
    trunk_id = os.getenv(SIP_OUTBOUND_TRUNK_ENV, "").strip()
    if not trunk_id:
        raise RuntimeError(f"{SIP_OUTBOUND_TRUNK_ENV} is not configured.")
    return trunk_id


def _safe_error_details(exc: BaseException) -> dict[str, Any]:
    details: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": str(exc),
    }

    for source_attr, result_key in (
        ("sip_status_code", "sip_status_code"),
        ("sip_status", "sip_status"),
        ("sip_reason", "sip_reason"),
        ("code", "error_code"),
        ("status", "http_status"),
        ("message", "error_message"),
    ):
        value = getattr(exc, source_attr, None)
        if value not in (None, ""):
            details[result_key] = value

    metadata = getattr(exc, "metadata", None)
    if isinstance(metadata, dict):
        safe_metadata = {
            key: value
            for key, value in metadata.items()
            if any(token in key.lower() for token in ("sip", "status", "reason"))
        }
        if safe_metadata:
            details["metadata"] = safe_metadata

    return details


async def create_outbound_sip_participant(
    *,
    sip_service: Any,
    room_name: str,
    sip_destination: str = DEFAULT_LINPHONE_DESTINATION,
    trunk_id: str | None = None,
    participant_name: str = "FinSaathi",
    wait_until_answered: bool = True,
) -> dict[str, Any]:
    """Create a SIP participant using the configured stored outbound trunk."""

    try:
        destination = validate_sip_destination(sip_destination)
        resolved_trunk_id = trunk_id or get_outbound_trunk_id()
    except (RuntimeError, ValueError) as exc:
        logger.warning("Outbound SIP call was not started: %s", exc)
        return {
            "success": False,
            "sip_call_to": sip_destination,
            "error": _safe_error_details(exc),
            "user_message": str(exc),
        }

    participant_identity = create_participant_identity()

    logger.info("Starting outbound SIP call...")
    logger.info("Creating SIP participant...")
    logger.info("Waiting for Linphone to answer...")

    try:
        participant = await sip_service.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=resolved_trunk_id,
                sip_call_to=destination,
                participant_identity=participant_identity,
                participant_name=participant_name,
                wait_until_answered=wait_until_answered,
            )
        )
    except api.TwirpError as exc:
        details = _safe_error_details(exc)
        logger.error("Outbound SIP call failed: %s", details)
        return {
            "success": False,
            "sip_call_to": destination,
            "participant_identity": participant_identity,
            "error": details,
            "user_message": _failure_message(details),
        }
    except Exception as exc:
        details = _safe_error_details(exc)
        logger.error("Outbound SIP call failed: %s", details)
        return {
            "success": False,
            "sip_call_to": destination,
            "participant_identity": participant_identity,
            "error": details,
            "user_message": _failure_message(details),
        }

    logger.info("Outbound SIP participant created.")
    logger.info("Outbound call answered.")

    return {
        "success": True,
        "sip_call_to": destination,
        "room_name": participant.room_name,
        "participant_id": participant.participant_id,
        "participant_identity": participant.participant_identity,
        "sip_call_id": participant.sip_call_id,
        "user_message": "Outbound SIP call was answered and joined the room.",
    }


async def create_outbound_sip_call_from_job(
    *,
    job_ctx: JobContext,
    sip_destination: str = DEFAULT_LINPHONE_DESTINATION,
    shutdown_on_failure: bool = False,
) -> dict[str, Any]:
    result = await create_outbound_sip_participant(
        sip_service=job_ctx.api.sip,
        room_name=job_ctx.room.name,
        sip_destination=sip_destination,
    )

    if not result["success"]:
        if shutdown_on_failure:
            job_ctx.shutdown(reason="outbound SIP call failed")
        return result

    participant_identity = result["participant_identity"]

    try:
        await asyncio.wait_for(
            job_ctx.wait_for_participant(
                identity=participant_identity,
                kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
            ),
            timeout=15,
        )
    except TimeoutError:
        logger.warning(
            "Outbound SIP participant was created but was not observed in the room."
        )
        result["participant_joined"] = False
        result["user_message"] = (
            "The SIP call was answered, but I could not confirm the Linphone "
            "participant in the LiveKit room yet."
        )
        return result

    logger.info("Linphone participant joined the room.")
    result["participant_joined"] = True
    return result


def _failure_message(details: dict[str, Any]) -> str:
    sip_status_code = details.get("sip_status_code")
    sip_status = details.get("sip_status")

    if sip_status_code or sip_status:
        return (
            "The outbound SIP call failed"
            f" with SIP status {sip_status_code or 'unknown'}"
            f" {sip_status or ''}.".strip()
        )

    error_code = details.get("error_code")
    error_message = details.get("error_message") or details.get("message")

    if error_code or error_message:
        return (
            "The outbound SIP call failed"
            f" with error {error_code or 'unknown'}: {error_message or ''}."
        )

    return "The outbound SIP call failed. Check the backend logs for details."
