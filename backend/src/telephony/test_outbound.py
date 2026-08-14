from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

from src.telephony.outbound import (
    DEFAULT_LINPHONE_DESTINATION,
    SIP_OUTBOUND_TRUNK_ENV,
    create_outbound_sip_participant,
)

logger = logging.getLogger("agent.telephony.test")


def _mask_number(number: str) -> str:
    if not number:
        return ""
    return "*" * max(len(number) - 4, 0) + number[-4:]


async def _verify_trunk(lkapi: api.LiveKitAPI, trunk_id: str) -> bool:
    response = await lkapi.sip.list_outbound_trunk(
        api.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])
    )

    if not response.items:
        print("Stored outbound trunk was not found.")
        return False

    trunk = response.items[0]
    print("Stored outbound trunk found.")
    print(f"Trunk name: {trunk.name}")
    print(f"Trunk address: {trunk.address}")
    print(f"Trunk transport: {api.SIPTransport.Name(trunk.transport)}")
    print(f"Destination country: {trunk.destination_country or '(not set)'}")
    print(f"Caller ID numbers: {[_mask_number(number) for number in trunk.numbers]}")
    print(f"Auth username configured: {bool(trunk.auth_username)}")
    print(f"Auth password configured: {bool(trunk.auth_password)}")
    return True


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

    parser = argparse.ArgumentParser(
        description="Dispatch FinSaathi and start a Day 6 outbound SIP test call."
    )
    parser.add_argument(
        "--destination",
        default=DEFAULT_LINPHONE_DESTINATION,
        help="SIP URI to dial. Defaults to the configured Linphone account.",
    )
    parser.add_argument(
        "--room",
        default=f"finsaathi-outbound-{uuid.uuid4().hex[:8]}",
        help="LiveKit room name to use for the test call.",
    )
    parser.add_argument(
        "--agent-name",
        default=os.getenv("AGENT_NAME", "my-agent"),
        help="LiveKit agent name to dispatch before dialing.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify the stored outbound trunk without placing a SIP call.",
    )
    args = parser.parse_args()

    trunk_id = os.getenv(SIP_OUTBOUND_TRUNK_ENV, "").strip()
    if not trunk_id:
        print(f"{SIP_OUTBOUND_TRUNK_ENV} is not configured.")
        return 1

    async with api.LiveKitAPI() as lkapi:
        if not await _verify_trunk(lkapi, trunk_id):
            return 1

        if args.verify_only:
            return 0

        print(f"Creating room: {args.room}")
        await lkapi.room.create_room(api.CreateRoomRequest(name=args.room))

        print(f"Dispatching agent: {args.agent_name}")
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=args.agent_name, room=args.room)
        )

        print(f"Dialing SIP destination: {args.destination}")
        result = await create_outbound_sip_participant(
            sip_service=lkapi.sip,
            room_name=args.room,
            sip_destination=args.destination,
        )

        if not result["success"]:
            print(result["user_message"])
            print(f"Failure details: {result['error']}")
            with contextlib.suppress(Exception):
                await lkapi.room.delete_room(api.DeleteRoomRequest(room=args.room))
            return 1

        print("Outbound SIP call answered.")
        print(f"Room: {result['room_name']}")
        print(f"Participant identity: {result['participant_identity']}")
        print(f"SIP call ID: {result['sip_call_id']}")
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(main()))
