import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    ChatMessage,
    ConversationItemAddedEvent,
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

from analytics import (
    finalize_call_record,
    generate_call_id,
    init_analytics_db,
    start_call_record,
)
from escalation import create_escalation_record
from memory import get_caller
from memory import save_caller as save_caller_to_db
from telephony.outbound import (
    DEFAULT_LINPHONE_DESTINATION,
    create_outbound_sip_call_from_job,
)
from tools import check_scheme_eligibility

logger = logging.getLogger("agent")

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

SYSTEM_PROMPT = """You are FinSaathi's main voice assistant for general personal finance.

You help users understand budgeting, expense tracking, savings, UPI, digital banking,
credit scores (CIBIL), loans, and financial safety.

SPECIALIST HANDOFF (GOVERNMENT SCHEMES):
You have a dedicated Government Scheme Specialist on your team.
When a caller asks questions specifically about Indian government financial or welfare schemes
(such as PM-KISAN, PM Jan Dhan Yojana, Atal Pension Yojana, Sukanya Samriddhi, PM Kaushal Vikas,
PM Awas Yojana, MUDRA loans, government subsidies, scheme eligibility, or scheme documents):
- You MUST immediately transfer the user to the specialist by calling the tool transfer_to_government_scheme_specialist.
- Do NOT ask for permission or confirmation before transferring. Connect them directly.
- Say: "I can help with general financial questions, but this is better handled by my Government Scheme Specialist. I'll connect you now, and you won't need to repeat your question."
- And immediately invoke transfer_to_government_scheme_specialist(user_query=...).

DO NOT HAND OFF GENERAL FINANCIAL TOPICS:
Answer general personal finance questions directly yourself without transferring:
- Managing monthly expenses / creating budgets
- Saving money and savings accounts
- UPI payments, debit/credit cards, and digital wallets
- Credit scores and loan basics
- Financial fraud safety and scam awareness"""

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
- Government financial schemes (for detailed scheme questions, eligibility checks, or scheme documents, hand off to the Government Scheme Specialist)
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

If a user requests account-specific actions, live transactions, or fraud reporting, explain that a human specialist should review or contact their bank.

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

HUMAN_ESCALATION_PROMPT = """DAY 7 HUMAN ESCALATION GUIDELINES:
You have access to a human support escalation tool: create_escalation.

FinSaathi must recognize when it should STOP trying to solve a problem itself and ask for HUMAN HELP.

USE EXACTLY TWO ESCALATION TRIGGERS:

TRIGGER 1: POSSIBLE FINANCIAL FRAUD
Recognize situations where the caller reports or strongly indicates:
- UPI fraud or unauthorized UPI transactions
- Unauthorized bank or card transactions
- Suspicious account transactions
- Stolen money, scams, phishing resulting in financial loss
- Account compromise involving financial loss

Examples:
- "I think someone has stolen money from my UPI."
- "There is a transaction in my account that I didn't make."
- "I got scammed and lost money."
- "My bank account has an unauthorized transaction."

In these fraud situations:
1. Do NOT pretend you can investigate, cancel, or reverse the transaction.
2. Clearly explain: "This sounds like something a human support specialist should review. I can create a support request with a short summary of what you've told me. Would you like me to share that information with our support team?"
3. WAIT FOR EXPLICIT PERMISSION before calling create_escalation.
4. Default urgency is "high".

TRIGGER 2: FINANCIAL DECISION OUTSIDE FINSAATHI'S SAFE SCOPE
Recognize situations where the caller asks FinSaathi to make a final personalized financial decision requiring human judgment or professional review:
- "Which loan should I definitely take?"
- "Can you approve my loan?"
- "Should I invest all my savings in this?"
- "Tell me exactly which investment I should buy."
- "Can you guarantee that I will get this loan?"
- "Can you decide which financial product is best for me?"

In these unsafe decision situations:
1. Do NOT pretend to be a financial advisor, bank employee, loan officer, or investment professional.
2. Clearly explain: "That's a decision where I shouldn't make the final call for you. I can create a request for a human financial support specialist to review your situation. Would you like me to share a short summary with them?"
3. WAIT FOR EXPLICIT PERMISSION before calling create_escalation.
4. Default urgency is "medium".

DO NOT ESCALATE NORMAL CONVERSATIONS:
Normal educational questions must NOT create escalations:
- "What is UPI?"
- "How can I make a budget?" / "How can I manage my monthly expenses?"
- "What is a credit score?"
- "How can I save money?"
- "What is a government financial scheme?"
- "How does a savings account work?"
- "What is PM Kaushal Vikas Yojana?"
Answer normal questions directly, conversationally, and helpfully.

CONSENT WORKFLOW (CRITICAL):
1. Detect Trigger 1 or Trigger 2.
2. Explain why human help is needed and ask for permission to create a support request.
3. NEVER call create_escalation BEFORE the user explicitly gives permission.
4. If the user says YES / agrees (e.g., "Yes", "Please do", "Sure", "Create the request"):
   - Call create_escalation with consent_given=True and relevant summary.
   - When the tool returns reference_id (e.g. FS-YYYYMMDD-XXXXX), tell the caller:
     "I've created the request. Your reference ID is [reference_id]. It's currently open for review. A human support specialist will follow up through your preferred method. I can't promise an immediate response."
   - Do NOT promise unrealistic resolution times (e.g., do not say "someone will call in 5 minutes").
5. If the user says NO / refuses consent (e.g., "No", "Don't share my information", "I don't want that"):
   - Do NOT call create_escalation.
   - Respond politely: "Understood. I won't create or share a support request. I can still help with general information if you'd like."
   - Continue the conversation normally.

PRIVACY & SENSITIVE DATA GUARDRAILS:
- NEVER ask for or include in escalation summaries: OTP, UPI PIN, ATM PIN, CVV, passwords, bank account numbers, card numbers, Aadhaar, or PAN.
- If the user starts reciting an OTP, PIN, password, CVV, account number, or card number, interrupt politely and state that you do not need that sensitive information.
- Keep the escalation summary short, concise, and focused on the core issue."""

AGENT_INSTRUCTIONS = "\n\n".join(
    [IDENTITY_PROMPT, SYSTEM_PROMPT, OUTBOUND_SIP_PROMPT, HUMAN_ESCALATION_PROMPT]
)


class CallTracker:
    def __init__(self, call_id: str, channel: str = "browser") -> None:
        self.call_id = call_id
        self.channel = channel
        self.start_timestamp = time.time()
        self.success_achieved = False
        self.success_reason: str | None = None
        self.failure_reason: str | None = None
        self.user_message_count = 0
        self.greeting_done = False

    def mark_success(self, reason: str) -> None:
        self.success_achieved = True
        self.success_reason = reason
        self.failure_reason = None
        logger.info("[ANALYTICS] Call %s marked SUCCESS: %s", self.call_id, reason)

    def mark_failure_reason(self, reason: str) -> None:
        if not self.success_achieved:
            self.failure_reason = reason
            logger.info(
                "[ANALYTICS] Call %s failure reason recorded: %s",
                self.call_id,
                reason,
            )


GOVERNMENT_SCHEME_SPECIALIST_INSTRUCTIONS = """You are FinSaathi's Government Scheme Specialist.

Your job is to help users understand Indian government financial and welfare schemes.

You handle:
- Scheme information (e.g., PM-KISAN, Pradhan Mantri Jan Dhan Yojana, Atal Pension Yojana, Sukanya Samriddhi Yojana, PM Kaushal Vikas Yojana, PM Awas Yojana, MUDRA loans, etc.)
- Scheme requirements and criteria
- Eligibility questions (using the check_financial_scheme_eligibility tool when information is provided)
- Required documents for schemes
- Application-related general guidance
- Explaining scheme benefits, subsidies, and conditions

TAKING OVER THE CONVERSATION (CRITICAL):
When you first respond after taking over from the main agent, introduce yourself briefly:
"Hi, I'm FinSaathi's Government Scheme Specialist. I understand you're asking about [the user's topic or question]. Let's check what information we need." (or equivalent in Hindi/Hinglish if the user spoke Hindi/Hinglish).
Then immediately continue addressing the user's specific request using the context passed to you.
Do NOT ask the user to repeat their question.

ELIGIBILITY CHECKING:
When a user asks if they qualify or are eligible for a scheme:
- If you have enough information (scheme name, age, annual income, state, student status), use the check_financial_scheme_eligibility tool.
- If required information is missing, ask for it politely (age, annual income, state, student status).
- After receiving the tool result, explain the result naturally and conversationally without reading raw JSON.
- Never invent eligibility results or scheme rules.

SAFETY & PRIVACY GUARDRAILS:
You must not:
- Guarantee approval or claim that an application is approved/submitted.
- Claim to be a government employee or official representative.
- Invent scheme rules or statistics not in verified knowledge.
- Request OTPs, PINs, passwords, CVVs, bank account numbers, card credentials, or Aadhaar numbers.

If information is unavailable or uncertain, say so clearly.
Stay within the scope of government schemes.

If the user changes to a general personal finance question (such as general monthly budgeting, savings tips, UPI, or banking basics), use transfer_to_main_agent to hand the conversation back to the main FinSaathi agent."""


class GovernmentSchemeSpecialist(Agent):
    def __init__(
        self,
        caller_id: str = "unknown_caller",
        caller_name: str | None = None,
        job_ctx: JobContext | None = None,
        call_tracker: CallTracker | None = None,
        initial_user_query: str = "",
    ) -> None:
        self.caller_id = caller_id
        self.caller_name = caller_name
        self.job_ctx = job_ctx
        self.call_tracker = call_tracker
        self.initial_user_query = initial_user_query
        self._tasks: set[asyncio.Task] = set()

        caller_info_str = (
            f"The caller's name is {caller_name}."
            if caller_name
            else "This is a new or unknown caller."
        )

        query_context = (
            f"\n\nCURRENT ACTIVE REQUEST:\nThe caller previously asked: '{initial_user_query}'. "
            "Address this request immediately without asking them to repeat it."
            if initial_user_query
            else ""
        )

        super().__init__(
            instructions=(
                f"{GOVERNMENT_SCHEME_SPECIALIST_INSTRUCTIONS}\n\n"
                "SESSION CONTEXT:\n"
                f"The current caller_id is {self.caller_id}. {caller_info_str}"
                f"{query_context}"
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
            "[SPECIALIST] Checking eligibility: scheme=%s, age=%s, income=%s, state=%s, student=%s",
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
        if self.call_tracker is not None:
            self.call_tracker.mark_success(
                f"Specialist checked eligibility for {scheme_name}"
            )
        logger.info("[SPECIALIST] Eligibility result: %s", result)
        return result

    @function_tool
    async def lookup_caller(
        self,
        context: RunContext,
        user_id: str = "",
    ) -> dict:
        """Look up a returning FinSaathi caller using their user ID."""
        lookup_id = user_id.strip() or self.caller_id
        logger.info("[SPECIALIST] Looking up caller: %s", lookup_id)
        caller = get_caller(lookup_id)
        if self.call_tracker is not None:
            self.call_tracker.mark_success("Caller profile memory lookup completed")
        if caller is None:
            return {"found": False, "message": "No previous caller record was found."}
        return {"found": True, "caller": caller}

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
        logger.info("[SPECIALIST] Saving caller information for: %s", user_id)
        save_caller_to_db(
            user_id=user_id,
            name=name,
            language_preference=language_preference,
            schemes_checked=schemes_checked,
            eligibility_answers=eligibility_answers,
        )
        if self.call_tracker is not None:
            self.call_tracker.mark_success("Caller information saved with consent")
        return {
            "success": True,
            "message": "Caller information has been saved successfully.",
        }

    @function_tool
    async def create_escalation(
        self,
        context: RunContext,
        caller_name: str = "",
        issue_type: str = "",
        short_summary: str = "",
        what_happened: str = "",
        what_fin_saathi_checked: str = "",
        urgency: str = "medium",
        caller_language: str = "English",
        preferred_follow_up_method: str = "not specified",
        consent_given: bool = False,
    ) -> dict:
        """Create a human support escalation for FinSaathi only when the user has explicitly consented to sharing a short summary and either reports possible financial fraud or requests an unsafe financial decision."""
        resolved_name = caller_name.strip() or self.caller_name or "Unknown"
        result = create_escalation_record(
            caller_name=resolved_name,
            issue_type=issue_type,
            short_summary=short_summary,
            what_happened=what_happened,
            what_fin_saathi_checked=what_fin_saathi_checked,
            urgency=urgency,
            caller_language=caller_language,
            preferred_follow_up_method=preferred_follow_up_method,
            consent_given=consent_given,
        )
        if result.get("success") and self.call_tracker is not None:
            self.call_tracker.mark_success(
                "Human escalation request created with consent"
            )
        return result

    @function_tool
    async def transfer_to_main_agent(
        self,
        context: RunContext,
        reason: str = "user requested general financial guidance",
    ) -> dict:
        """Transfer the conversation back to the main FinSaathi agent when the user asks general personal finance questions unrelated to government schemes."""
        logger.info("[SPECIALIST] Transferring back to main Assistant: %s", reason)
        try:
            main_assistant = Assistant(
                caller_id=self.caller_id,
                caller_name=self.caller_name,
                job_ctx=self.job_ctx,
                call_tracker=self.call_tracker,
            )
            context.session.update_agent(main_assistant)
            return {
                "success": True,
                "status": "transferred_to_main",
                "message": "Connected back to main FinSaathi financial assistant.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @function_tool
    async def end_call(
        self,
        context: RunContext,
        reason: str = "caller_requested_end",
    ) -> dict:
        """End or hang up the current phone call cleanly when the caller wants to stop or end the call."""
        logger.info("[SPECIALIST] Ending call: reason=%s", reason)
        if self.job_ctx is not None:
            task = asyncio.create_task(self._delayed_shutdown(self.job_ctx))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return {"success": True, "message": "Call termination initiated."}

    async def _delayed_shutdown(
        self, job_ctx: JobContext, delay_seconds: float = 3.0
    ) -> None:
        await asyncio.sleep(delay_seconds)
        job_ctx.shutdown(reason="call ended by request")


class Assistant(Agent):
    def __init__(
        self,
        caller_id: str = "unknown_caller",
        caller_name: str | None = None,
        job_ctx: JobContext | None = None,
        call_tracker: CallTracker | None = None,
    ) -> None:
        self.caller_id = caller_id
        self.caller_name = caller_name
        self.job_ctx = job_ctx
        self.call_tracker = call_tracker
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
    async def transfer_to_government_scheme_specialist(
        self,
        context: RunContext,
        user_query: str,
    ) -> dict:
        """Transfer the conversation to FinSaathi's Government Scheme Specialist when the user asks for detailed information about an Indian government financial or welfare scheme, asks whether they qualify for a government scheme, asks about scheme-specific documents, benefits, eligibility criteria, or application requirements. Do not use this tool for ordinary budgeting, savings, UPI, credit score, banking, or general financial questions."""
        logger.info(
            "Transferring to GovernmentSchemeSpecialist with context: %s",
            user_query,
        )
        try:
            specialist = GovernmentSchemeSpecialist(
                caller_id=self.caller_id,
                caller_name=self.caller_name,
                job_ctx=self.job_ctx,
                call_tracker=self.call_tracker,
                initial_user_query=user_query,
            )
            context.session.update_agent(specialist)
            if self.call_tracker is not None:
                self.call_tracker.mark_success(
                    f"Transferred to Government Scheme Specialist: {user_query[:40]}"
                )
            return {
                "success": True,
                "status": "transferred",
                "specialist": "GovernmentSchemeSpecialist",
                "message": (
                    f"Connected to Government Scheme Specialist. The specialist has received the question: '{user_query}'."
                ),
            }
        except Exception as e:
            logger.error("Failed to transfer to GovernmentSchemeSpecialist: %s", e)
            return {
                "success": False,
                "status": "failed",
                "error": str(e),
                "message": (
                    "I couldn't connect you to the specialist right now, but I can still help with general information."
                ),
            }

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

        if self.call_tracker is not None:
            self.call_tracker.mark_success("Caller profile memory lookup completed")

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

        if self.call_tracker is not None:
            self.call_tracker.mark_success("Caller information saved with consent")

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

        result = await create_outbound_sip_call_from_job(
            job_ctx=self.job_ctx,
            sip_destination=sip_destination,
        )

        if result.get("success") and self.call_tracker is not None:
            self.call_tracker.mark_success("Outbound SIP call initiated")

        return result

    @function_tool
    async def create_escalation(
        self,
        context: RunContext,
        caller_name: str = "",
        issue_type: str = "",
        short_summary: str = "",
        what_happened: str = "",
        what_fin_saathi_checked: str = "",
        urgency: str = "medium",
        caller_language: str = "English",
        preferred_follow_up_method: str = "not specified",
        consent_given: bool = False,
    ) -> dict:
        """Create a human support escalation for FinSaathi only when the user has explicitly consented to sharing a short summary and either reports possible financial fraud/unauthorized financial activity or requests a personalized financial decision that FinSaathi cannot safely make. Do not use this tool for normal financial questions. Never include OTPs, PINs, CVVs, passwords, bank account numbers, card numbers, Aadhaar numbers, PAN numbers, or other sensitive credentials."""

        resolved_name = caller_name.strip() or self.caller_name or "Unknown"
        logger.info(
            "create_escalation called: caller=%s, issue=%s, urgency=%s, consent=%s",
            resolved_name,
            issue_type,
            urgency,
            consent_given,
        )

        result = create_escalation_record(
            caller_name=resolved_name,
            issue_type=issue_type,
            short_summary=short_summary,
            what_happened=what_happened,
            what_fin_saathi_checked=what_fin_saathi_checked,
            urgency=urgency,
            caller_language=caller_language,
            preferred_follow_up_method=preferred_follow_up_method,
            consent_given=consent_given,
        )

        if result.get("success") and self.call_tracker is not None:
            self.call_tracker.mark_success(
                "Human escalation request created with consent"
            )

        return result

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
    init_analytics_db()
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

    # Initialize Day 8 persistent Call Tracker and create start record in DB
    channel = (
        "sip"
        if (
            participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            or "phone" in participant.identity.lower()
            or "sip" in participant.identity.lower()
        )
        else "browser"
    )
    call_id = generate_call_id()
    start_call_record(call_id=call_id, channel=channel)
    tracker = CallTracker(call_id=call_id, channel=channel)

    async def _finalize_analytics(reason: str = "") -> None:
        ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration_seconds = max(0, round(time.time() - tracker.start_timestamp))
        if tracker.success_achieved:
            outcome = "success"
            success_reason = (
                tracker.success_reason or "Meaningful financial interaction completed"
            )
            failure_reason = None
        else:
            outcome = "failed"
            failure_reason = (
                tracker.failure_reason
                or "Caller disconnected before completing a meaningful financial interaction"
            )
            success_reason = None

        finalize_call_record(
            call_id=tracker.call_id,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            outcome=outcome,
            success_reason=success_reason,
            failure_reason=failure_reason,
        )

    ctx.add_shutdown_callback(_finalize_analytics)

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
        if ev.is_final and ev.transcript and ev.transcript.strip():
            tracker.user_message_count += 1

    @session.on("conversation_item_added")
    def on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if (
            isinstance(item, ChatMessage)
            and item.role == "assistant"
            and tracker.greeting_done
            and tracker.user_message_count > 0
        ):
            content = item.text_content or ""
            if len(content.strip()) > 5:
                tracker.mark_success("Financial question answered conversationally")

    assistant = Assistant(
        caller_id=caller_id,
        caller_name=caller_name,
        job_ctx=ctx,
        call_tracker=tracker,
    )

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
    tracker.greeting_done = True
    logger.info("OUTBOUND: initial greeting generation completed")


if __name__ == "__main__":
    cli.run_app(server)
