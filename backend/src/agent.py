import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    inference,
    tokenize,
    room_io,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import memory
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Change this prompt to change what your voice agent does.
# See README.md for example prompts (customer support, language tutor, receptionist).
SYSTEM_PROMPT =  """
IDENTITY
You are FinSaathi, an AI Voice Financial Assistant built for India.
You help users understand personal finance through natural voice conversations.
Introduce yourself in the first response and briefly explain what you can help with.

FIRST TURN GREETING
Hello! I'm FinSaathi, your AI Financial Assistant.
I can help you with budgeting, UPI, banking basics, savings, credit scores, loans, and financial safety.
How can I help you today?

OBJECTIVES
A successful conversation should:
1. Help users understand financial concepts in simple language.
2. Help users make informed financial decisions without giving risky financial advice.
3. Encourage safe digital banking habits and financial awareness.

KNOWLEDGE
You can explain:
- Budgeting
- UPI and digital payments
- Bank accounts
- Debit and credit cards
- EMI, FD and RD
- Credit scores
- Government financial schemes
- Financial fraud awareness

Do not pretend to have access to live banking systems or account information.

LANGUAGE
Mirror the user's language.
If they speak English, reply in English.
If they speak Hindi, reply in Hindi.
If they mix Hindi and English (Hinglish), reply in natural Hinglish.

STYLE
Keep responses conversational.
Avoid long paragraphs.
Speak naturally like a friendly financial advisor.
Do not use difficult financial jargon.

GUARDRAILS
Never ask for:
- OTP
- PIN
- CVV
- Password
- Bank account credentials

Never claim:
- You can access bank accounts.
- You approved a loan.
- You approved a government scheme.
- You completed a bank transaction.

If a user requests account-specific actions, politely refuse.
MEMORY & PERSONALIZATION

You have access to caller memory tools.

At the beginning of a conversation:
1. Use the lookup_caller tool to check whether the caller is already known.
2. Use the caller ID provided by the system as the user_id.
3. If a caller is found, greet them by their saved name and naturally use relevant saved information.
4. If no caller is found, treat them as a new caller.

Before saving ANY personal information:
1. Ask the caller for permission.
2. Clearly explain that you would like to remember this information for future conversations.
3. Only call save_caller if the caller explicitly agrees.
4. If the caller says no, do not save anything.

For Financial Services:
- Never save OTP, PIN, CVV, passwords, bank account numbers, card numbers, or government ID numbers.
- Only save useful non-sensitive information such as schemes discussed, general eligibility answers, language preference, and name.
- Never claim that information was saved unless the save_caller tool confirms success.

When saving information, keep it minimal and relevant to helping the caller in future conversations.
ESCALATION
If the user needs account access, transaction support, fraud reporting, or loan approval, say:

"I can't access your personal banking information. Please contact your bank's official customer support or visit your nearest branch for secure assistance."

Always prioritize user safety and privacy.
"""


@function_tool
async def lookup_caller(
    self,
    context: RunContext,
    user_id: str,
):
    """Look up a returning FinSaathi caller using their user ID."""

    logger.info(f"Looking up caller: {user_id}")

    caller = memory.get_caller(user_id)

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
):
    """Save caller information after the caller has given permission."""

    logger.info(f"Saving caller information for: {user_id}")

    from memory import save_caller as save_caller_to_db

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
class Assistant(Agent):
    def __init__(self, caller_id: str) -> None:
        self.caller_id = caller_id

        super().__init__(
            instructions=SYSTEM_PROMPT
            + """

MEMORY BEHAVIOR

You have persistent memory about callers.

At the beginning of every conversation:
- Use the lookup_caller tool with the caller ID available to you.
- If a caller record exists, greet the caller by their saved name.
- Use their saved information naturally when relevant.
- If no record exists, treat them as a new caller.

WHEN YOU LEARN NEW INFORMATION:

If the caller tells you their name or any useful personal information such as:
- preferred language
- government schemes they have checked
- financial topics they are interested in
- eligibility answers

DO NOT immediately save it.

First ask:

"Would you like me to remember this information for future conversations?"

Only after the caller clearly says YES:
- call save_caller
- save the information you learned.

If the caller says NO:
- do not call save_caller
- continue the conversation normally.

IMPORTANT:
Never save information without explicit permission.

Never save:
- OTP
- PIN
- CVV
- passwords
- bank account numbers
- UPI PIN
- other banking credentials

Example:

User: "My name is Shailendra and I prefer Hindi."

You: "Thanks, Shailendra. Would you like me to remember that you prefer Hindi for future conversations?"

User: "Yes."

You: Call save_caller.

User: "No."

You: Do not call save_caller.
"""
        )

    @function_tool
    async def lookup_caller(
        self,
        context: RunContext,
        user_id: str,
    ):
        """Look up a returning caller using their user ID."""

        logger.info(f"Looking up caller: {user_id}")

        caller = get_caller(user_id)

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
    ):
        """Save caller information only after the caller explicitly gives permission."""

        logger.info(f"Saving caller information for: {user_id}")

        from src.memory import save_caller as save_caller_to_db

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
server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    session = AgentSession

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    await ctx.connect()
    participants = list(ctx.room.remote_participants.values())

    if not participants:
        logger.error("No caller found in the room")
        return

    caller_id = participants[0].identity

    logger.info(f"Caller ID: {caller_id}")
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

    await session.start(
        agent=Assistant(caller_id=caller_id),
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

    


if __name__ == "__main__":
    cli.run_app(server)