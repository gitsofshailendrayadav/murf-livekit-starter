import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    JobContext,
    JobProcess,
    RunContext,
    SpeechCreatedEvent,
    UserInputTranscribedEvent,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from src.memory import get_caller
from src.memory import save_caller as save_caller_to_db
from src.telephony.outbound import (
    DEFAULT_LINPHONE_DESTINATION,
    create_outbound_sip_call_from_job,
)
from src.tools import check_scheme_eligibility

logger = logging.getLogger("agent")

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

SYSTEM_PROMPT = """You have access to a financial scheme eligibility checker.

When a caller asks whether they may be eligible for a government or financial
scheme, and you have enough information such as their age, annual income, state,
and student status, use the eligibility checker tool.

Do not calculate or guess eligibility yourself when the tool can answer it.

Before calling the tool, ask for any required information that is missing.

After receiving the tool result:
- Explain the result naturally in conversation.
- Do not read the returned JSON or field names aloud.
- Mention that this is a basic eligibility check based on the available dataset.
- Mention the date of the data when relevant.
- If the tool says the scheme is unavailable, clearly say you cannot verify it
  rather than guessing."""

IDENTITY_PROMPT = """You are FinSaathi, an AI Voice Financial Assistant built for India.
You help users understand personal finance through natural voice conversations.

OUTBOUND CALL OPENING:
When initiating an outbound phone call, introduce yourself naturally:
"Hi, this is FinSaathi, your AI Financial Assistant. I'm calling to help you with your financial questions, like budgeting, savings, and government schemes. This is an AI assistant, and you can end the call anytime. Is this a good time to talk?"

IMPORTANT OUTBOUND REQUIREMENTS:
1. Clearly identify who is calling (FinSaathi, your AI Financial Assistant).
2. Clearly explain why the person is receiving the call (help with personal finance questions like budgeting, savings, schemes).
3. State that this is an AI assistant.
4. Let the user know they can end or stop the call anytime.
5. Do not make the call sound like a sales or spam call.

OPT-OUT AND CALL TERMINATION:
If the user indicates they do not want to talk, want to stop, are busy, or ask you to hang up/end the call (e.g. "I don't want this call", "I'm busy", "No", "End the call", "Hang up"):
- Immediately respond politely: "No problem. I'll end the call here. Have a good day." (or equivalent polite goodbye in the user's language).
- Call the end_call tool to terminate the session cleanly.

CONVERSATION BEHAVIOR:
After the opening:
- Listen attentively to the caller.
- Respond conversationally and concisely, suitable for a phone call.
- Do not speak JSON, raw data, or mention internal tools/function names.
- Do not say "I am calling a function" or "Let me execute a tool".
- Do not sound robotic.

OBJECTIVES:
1. Help users understand financial concepts in simple language.
2. Help users make informed financial decisions without giving risky financial advice.
3. Encourage safe digital banking habits and financial awareness.

KNOWLEDGE:
You can explain:
- Budgeting and expense management
- UPI and digital payments
- Bank accounts (Savings, Current)
- Debit and credit cards
- EMI, Fixed Deposits (FD) and Recurring Deposits (RD)
- Credit scores (CIBIL)
- Government financial schemes (e.g., PM Jan Dhan, PM Kaushal Vikas, Atal Pension, Sukanya Samriddhi)
- Financial safety and fraud awareness

Do not pretend to have access to live banking systems or account information.

LANGUAGE:
Mirror the user's language:
- If the user speaks English, reply in English.
- If the user speaks Hindi, reply in Hindi.
- If the user mixes Hindi and English (Hinglish), reply in natural Hinglish.

STYLE:
Keep responses conversational, concise, and natural for a phone conversation. Avoid lengthy monologues. Do not use overly difficult financial jargon.

GUARDRAILS:
Never ask for:
- OTP
- PIN
- CVV
- Passwords
- Bank account credentials or numbers

Never claim:
- You can access bank accounts.
- You can perform bank transactions or transfer money.
- You approved a loan.
- You approved a government scheme.

If a user requests account-specific actions, live transactions, or fraud reporting, say:
"I can't access your personal banking information. Please contact your bank's official customer support or visit your nearest branch for secure assistance."

MEMORY AND PERSONALIZATION:
You have access to caller memory tools (lookup_caller, save_caller).

Caller personalization:
1. The session context provides the caller ID and any known saved information.
2. Use the caller's saved name naturally if available.
3. If no caller name is known, treat them as a new caller.
4. Use lookup_caller if looking up past discussion details or if the caller asks about previous records.

Before saving any personal information:
1. Ask the caller for explicit permission first.
2. Clearly explain that you would like to remember this information for future conversations.
3. Only call save_caller if the caller explicitly agrees.
4. If the caller says no, do not save anything.

For financial services:
- Never save OTP, PIN, CVV, passwords, bank account numbers, card numbers, or government ID numbers.
- Only save useful non-sensitive information such as schemes discussed, general eligibility answers, language preference, and name.
- Never claim that information was saved unless the save_caller tool confirms success.

Always prioritize user safety and privacy."""

OUTBOUND_SIP_PROMPT = f"""DAY 6 OUTBOUND SIP CALLING
You can start one explicit Day 6 outbound SIP test call to the configured
Linphone destination:
{DEFAULT_LINPHONE_DESTINATION}

Use start_outbound_sip_call only when the user clearly asks you to call their
Linphone account, for example "Call my Linphone" or "Start an outbound call to
my Linphone account."

Do not start an outbound call when the user casually mentions a phone number,
SIP address, or calling in general. Do not place PSTN calls for this test. If a
requested destination is not a sip: URI, explain that this Day 6 test only
supports SIP URI destinations.

After the tool returns, explain the result naturally. If it failed, use the
tool's user_message and do not claim that the call connected."""

AGENT_INSTRUCTIONS = "\n\n".join([IDENTITY_PROMPT, SYSTEM_PROMPT, OUTBOUND_SIP_PROMPT])


class Assistant(Agent):
    def __init__(
        self,
        caller_id: str = "unknown_caller",
        caller_name: str | None = None,
        job_ctx: JobContext | None = None,
    ) -> None:
        self.caller_id = caller_id
        self.caller_name = caller_name
        self.job_ctx = job_ctx
        self._tasks: set[asyncio.Task] = set()

        caller_info_str = (
            f"The caller's name is {caller_name}."
            if caller_name
            else "This is a new or unknown caller."
        )

        super().__init__(
            instructions=(
                f"{AGENT_INSTRUCTIONS}\n\n"
                "SESSION CONTEXT\n"
                f"The current caller_id is {self.caller_id}. {caller_info_str} "
                "Use lookup_caller if looking up detailed caller history or when explicitly requested."
            )
        )

    @function_tool
    async def check_financial_scheme_eligibility(
        self,
        context: RunContext,
        scheme_name: str,
        age: int,
        annual_income: float,
        state: str,
        is_student: bool,
    ) -> dict:
        """Check basic eligibility for a financial or government scheme.

        Use this tool when the caller asks whether they may be eligible for a
        financial or government scheme and provides the required eligibility
        information. Do not guess eligibility if the requested scheme is not
        available in the local dataset.
        """

        logger.info(
            "Checking eligibility: scheme=%s, age=%s, income=%s, state=%s, student=%s",
            scheme_name,
            age,
            annual_income,
            state,
            is_student,
        )

        result = check_scheme_eligibility(
            scheme_name=scheme_name,
            age=age,
            annual_income=annual_income,
            state=state,
            is_student=is_student,
        )

        logger.info("Eligibility result: %s", result)
        return result

    @function_tool
    async def lookup_caller(
        self,
        context: RunContext,
        user_id: str = "",
    ) -> dict:
        """Look up a returning FinSaathi caller using their user ID."""

        lookup_id = user_id.strip() or self.caller_id
        logger.info("Looking up caller: %s", lookup_id)

        caller = get_caller(lookup_id)

        if caller is None:
            return {
                "found": False,
                "message": "No previous caller record was found.",
            }

        return {
            "found": True,
            "caller": caller,
        }

    @function_tool
    async def save_caller(
        self,
        context: RunContext,
        user_id: str,
        name: str,
        language_preference: str = "",
        schemes_checked: str = "",
        eligibility_answers: str = "",
    ) -> dict:
        """Save caller information after the caller has given permission."""

        logger.info("Saving caller information for: %s", user_id)

        save_caller_to_db(
            user_id=user_id,
            name=name,
            language_preference=language_preference,
            schemes_checked=schemes_checked,
            eligibility_answers=eligibility_answers,
        )

        return {
            "success": True,
            "message": "Caller information has been saved successfully.",
        }

    @function_tool
    async def start_outbound_sip_call(
        self,
        context: RunContext,
        sip_destination: str = DEFAULT_LINPHONE_DESTINATION,
    ) -> dict:
        """Start an explicit outbound SIP test call to a SIP URI.

        Use this tool only after the user clearly asks FinSaathi to call their
        Linphone account or another explicit SIP URI. This tool does not support
        casual mentions or PSTN phone numbers.
        """

        if self.job_ctx is None:
            return {
                "success": False,
                "sip_call_to": sip_destination,
                "user_message": (
                    "Outbound SIP calling is only available inside a LiveKit agent job."
                ),
            }

        return await create_outbound_sip_call_from_job(
            job_ctx=self.job_ctx,
            sip_destination=sip_destination,
        )

    @function_tool
    async def end_call(
        self,
        context: RunContext,
        reason: str = "caller_requested_end",
    ) -> dict:
        """End or hang up the current phone call cleanly when the caller wants to stop or end the call."""

        logger.info("Ending call: reason=%s", reason)
        if self.job_ctx is not None:
            task = asyncio.create_task(self._delayed_shutdown(self.job_ctx))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        return {
            "success": True,
            "message": "Call termination initiated.",
        }

    async def _delayed_shutdown(
        self, job_ctx: JobContext, delay_seconds: float = 3.0
    ) -> None:
        await asyncio.sleep(delay_seconds)
        job_ctx.shutdown(reason="call ended by request")


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext) -> None:
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    await ctx.connect()

    # Room event listeners for detailed media diagnostics
    @ctx.room.on("participant_connected")
    def on_participant_connected(p: rtc.RemoteParticipant) -> None:
        logger.info(
            "[SIP DIAG] Remote participant connected: identity=%s, kind=%s, name=%s",
            p.identity,
            p.kind,
            p.name,
        )

    @ctx.room.on("track_published")
    def on_track_published(
        publication: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant
    ) -> None:
        logger.info(
            "[SIP DIAG] Remote track published: sid=%s, kind=%s, source=%s by %s",
            publication.sid,
            publication.kind,
            publication.source,
            p.identity,
        )

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        p: rtc.RemoteParticipant,
    ) -> None:
        logger.info(
            "[SIP DIAG] Agent subscribed to remote track: sid=%s, kind=%s from %s",
            publication.sid,
            track.kind,
            p.identity,
        )

    @ctx.room.on("local_track_published")
    def on_local_track_published(
        publication: rtc.LocalTrackPublication, track: rtc.LocalTrack
    ) -> None:
        logger.info(
            "[SIP DIAG] Local audio track published: sid=%s, kind=%s, name=%s",
            publication.sid,
            publication.kind,
            publication.name,
        )

    @ctx.room.on("local_track_subscribed")
    def on_local_track_subscribed(track: rtc.LocalTrack) -> None:
        logger.info(
            "[SIP DIAG] Local track subscribed by participant: kind=%s",
            track.kind,
        )

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(
        disconnected_participant: rtc.RemoteParticipant,
    ) -> None:
        logger.info(
            "[SIP DIAG] Remote participant disconnected: identity=%s, kind=%s",
            disconnected_participant.identity,
            disconnected_participant.kind,
        )
        if not ctx.room.remote_participants:
            logger.info(
                "[SIP DIAG] All remote participants left; shutting down agent job."
            )
            ctx.shutdown(reason="remote participant disconnected")

    # Wait asynchronously for the participant (SIP phone caller or web user)
    logger.info("OUTBOUND: waiting for SIP participant")
    try:
        participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=120)
    except TimeoutError:
        logger.warning(
            "No participant joined room %s within timeout; shutting down job.",
            ctx.room.name,
        )
        ctx.shutdown(reason="participant join timeout")
        return

    logger.info(
        "OUTBOUND: SIP participant joined: identity=%s kind=%s",
        participant.identity,
        participant.kind,
    )

    caller_id = participant.identity

    # Check caller memory for personalized greeting
    caller_record = get_caller(caller_id)
    caller_name = caller_record.get("name") if caller_record else None

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Agent session event diagnostics
    @session.on("agent_state_changed")
    def on_agent_state_changed(ev: AgentStateChangedEvent) -> None:
        logger.info(
            "[SIP DIAG] Agent state transition: %s -> %s",
            ev.old_state,
            ev.new_state,
        )

    @session.on("speech_created")
    def on_speech_created(ev: SpeechCreatedEvent) -> None:
        logger.info(
            "[SIP DIAG] Murf speech created: id=%s, source=%s",
            ev.speech_handle.id,
            ev.source,
        )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent) -> None:
        logger.info(
            "[SIP DIAG] Deepgram transcribed caller speech (final=%s): '%s'",
            ev.is_final,
            ev.transcript,
        )

    assistant = Assistant(caller_id=caller_id, caller_name=caller_name, job_ctx=ctx)

    logger.info("OUTBOUND: starting AgentSession")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )
    logger.info("OUTBOUND: AgentSession started")

    # Automatically speak opening greeting via Murf TTS
    if caller_name:
        greeting = (
            f"Hi {caller_name}, this is FinSaathi, your AI Financial Assistant. "
            "I'm calling to help you with your financial questions, like budgeting, "
            "savings, and government schemes. This is an AI assistant, and you can end "
            "the call anytime. Is this a good time to talk?"
        )
    else:
        greeting = (
            "Hi, this is FinSaathi, your AI Financial Assistant. "
            "I'm calling to help you with your financial questions, like budgeting, "
            "savings, and government schemes. This is an AI assistant, and you can end "
            "the call anytime. Is this a good time to talk?"
        )

    logger.info("OUTBOUND: generating initial FinSaathi greeting")
    await session.say(greeting, allow_interruptions=True)
    logger.info("OUTBOUND: initial greeting generation completed")


if __name__ == "__main__":
    cli.run_app(server)
