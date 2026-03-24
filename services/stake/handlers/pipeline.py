"""
Pipeline handlers for the Stake Advisor Bot.

Handles text paste (INPUT-01) and .txt document (INPUT-02) in idle state.
Per PIPELINE-01 (progressive updates), PIPELINE-02 (clarifying question for
ambiguous data), PIPELINE-05 (duplicate warning).

Handlers:
    handle_paste             — INPUT-01: raw text paste in idle state
    handle_paste_no_state    — handles first message before any state is set
    handle_document          — INPUT-02: .txt file upload in idle state
    handle_clarification     — PIPELINE-02: user response to ambiguous data question
    handle_bankroll_input    — awaiting_bankroll_input: user types USDT amount
"""

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from services.stake.states import PipelineStates
from services.stake.settings import get_stake_settings
from services.stake.handlers.commands import balance_header
from services.stake.pipeline.graph import build_pipeline_graph
from services.stake.pipeline.formatter import format_race_summary
from services.stake.keyboards.stake_kb import confirm_parse_kb, bankroll_confirm_kb, bankroll_input_kb
from services.stake.bankroll.repository import BankrollRepository
from services.stake.audit.logger import AuditLogger

router = Router(name="pipeline")


async def _run_parse_pipeline(message: Message, state: FSMContext, raw_text: str) -> None:
    """Common pipeline logic for both paste and document input.

    Checks for active pipeline (PIPELINE-05), sets parsing state,
    runs LangGraph pipeline, handles ambiguous data (PIPELINE-02),
    and shows formatted race summary for confirmation (PARSE-04 / D-22).

    All events are logged to the JSONL audit log (AUDIT-01 / D-27).

    Args:
        message: Incoming aiogram Message to reply to.
        state: FSMContext for state transitions and data storage.
        raw_text: Raw text to parse (from paste or .txt file).
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    # PIPELINE-05: check for active pipeline
    current_state = await state.get_state()
    if current_state and current_state != PipelineStates.idle.state:
        await message.answer(
            f"{header}"
            "A pipeline is already active. Use /cancel first, "
            "or wait for it to complete."
        )
        return

    # Set state to parsing
    await state.set_state(PipelineStates.parsing)
    await state.update_data(raw_input=raw_text)

    # AUDIT-01: log pipeline start
    audit.log_entry("pipeline_start", {"raw_input": raw_text[:500]})

    # PIPELINE-01: progressive update — parsing step
    await message.answer(f"{header}Parsing race data...")

    # Run LangGraph pipeline
    try:
        graph = build_pipeline_graph()
        result = await graph.ainvoke({"raw_input": raw_text})
    except Exception as e:
        await state.set_state(PipelineStates.idle)
        await message.answer(f"{header}Parse error: {str(e)}\n\nPlease try again.")
        audit.log_entry("parse_error", {"error": str(e)})
        return

    if result.get("error"):
        await state.set_state(PipelineStates.idle)
        await message.answer(
            f"{header}Parse error: {result['error']}\n\nPlease try again."
        )
        audit.log_entry("parse_error", {"error": result["error"]})
        return

    # Store pipeline result in FSM data (must be JSON-serializable for Redis)
    parsed_race = result.get("parsed_race")
    serializable_result = {
        k: (v.model_dump() if hasattr(v, "model_dump") else v)
        for k, v in result.items()
    }
    await state.update_data(
        pipeline_result=serializable_result,
        parsed_race_json=parsed_race.model_dump_json() if parsed_race else None,
    )

    # AUDIT-01: log parse result
    audit.log_entry("parse_complete", {
        "parsed_race": parsed_race.model_dump() if parsed_race else None,
        "overround_raw": result.get("overround_raw"),
        "overround_active": result.get("overround_active"),
        "ambiguous_fields": result.get("ambiguous_fields"),
    })

    # PIPELINE-01: format and display race summary
    summary = format_race_summary(result)

    # PIPELINE-02: Check for ambiguous data — non-empty ambiguous_fields
    # triggers clarifying question before confirmation
    ambiguous = result.get("ambiguous_fields") or []
    if ambiguous:
        await state.set_state(PipelineStates.awaiting_clarification)
        await state.update_data(ambiguous_fields=ambiguous)

        # Build specific questions about the ambiguous fields
        question_parts: list[str] = []
        if "track" in ambiguous:
            question_parts.append("What is the track/venue name?")
        if "runner_count_mismatch" in ambiguous:
            expected = parsed_race.runner_count if parsed_race else "?"
            actual = len(parsed_race.runners) if parsed_race else "?"
            question_parts.append(
                f"The paste mentions {expected} runners but only {actual} were extracted. "
                "Is this correct, or should there be more?"
            )
        if "missing_odds" in ambiguous:
            if parsed_race:
                runners_no_odds = [
                    r.name for r in parsed_race.runners
                    if r.win_odds is None and r.status == "active"
                ]
                question_parts.append(
                    f"These runners are missing odds: {', '.join(runners_no_odds[:5])}. "
                    "Are they scratched, or do they have odds?"
                )
        if not question_parts:
            question_parts.append(
                f"Some data appears incomplete ({', '.join(ambiguous)}). "
                "Can you clarify or confirm this is correct?"
            )

        audit.log_entry("clarification_asked", {
            "ambiguous_fields": ambiguous,
            "questions": question_parts,
        })
        await message.answer(
            f"{header}{summary}\n\n"
            "<b>Clarification needed:</b>\n"
            + "\n".join(f"- {q}" for q in question_parts)
            + "\n\nPlease reply with the missing info, or type 'ok' to proceed as-is."
        )
        return

    # PARSE-04 / D-22: display summary and ask for confirmation
    await state.set_state(PipelineStates.awaiting_parse_confirm)
    await message.answer(
        f"{header}{summary}\n\n"
        "Please confirm this race data is correct:",
        reply_markup=confirm_parse_kb(),
    )


# INPUT-01: raw text paste in idle state
@router.message(PipelineStates.idle, F.text)
async def handle_paste(message: Message, state: FSMContext) -> None:
    """Handle raw text paste in idle state.

    Skips if the text looks like a command (starts with /).
    """
    import logging
    logging.getLogger("stake").info(f"handle_paste FIRED, state={await state.get_state()}, text_len={len(message.text or '')}")
    if message.text and message.text.startswith("/"):
        return
    await _run_parse_pipeline(message, state, message.text or "")


# Also handle text when no state is set (very first message)
@router.message(F.text)
async def handle_paste_no_state(message: Message, state: FSMContext) -> None:
    """Handle text messages when FSM state is not set or is idle.

    For first-ever message (no state), initialises to idle then runs pipeline.
    For active pipeline state, shows PIPELINE-05 duplicate warning.
    Skips commands.
    """
    import logging
    logging.getLogger("stake").info(f"handle_paste_no_state FIRED, state={await state.get_state()}, text_len={len(message.text or '')}")
    if message.text and message.text.startswith("/"):
        return

    current = await state.get_state()
    if current is None:
        await state.set_state(PipelineStates.idle)
        await _run_parse_pipeline(message, state, message.text or "")
    elif current == PipelineStates.idle.state:
        await _run_parse_pipeline(message, state, message.text or "")
    elif current in (
        PipelineStates.awaiting_clarification.state,
        PipelineStates.awaiting_bankroll_input.state,
    ):
        # Let specific handlers deal with these states — do not intercept
        pass
    else:
        # PIPELINE-05: active pipeline warning
        settings = get_stake_settings()
        header = balance_header(settings.database_path)
        await message.answer(
            f"{header}"
            "A pipeline is already active. Use /cancel first."
        )


# INPUT-02: .txt file upload in idle state
@router.message(PipelineStates.idle, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot) -> None:
    """Handle .txt file upload in idle state (INPUT-02).

    Validates mime type or file extension, downloads content,
    then runs the same pipeline as a text paste.
    """
    doc = message.document
    if doc is None:
        return
    if (
        doc.mime_type not in ("text/plain",)
        and not (doc.file_name and doc.file_name.endswith(".txt"))
    ):
        await message.answer("Please send a .txt file with race data.")
        return

    buf = io.BytesIO()
    await bot.download(doc.file_id, destination=buf)
    raw_text = buf.getvalue().decode("utf-8")
    await _run_parse_pipeline(message, state, raw_text)


# PIPELINE-02: Handle clarification response
@router.message(PipelineStates.awaiting_clarification, F.text)
async def handle_clarification(message: Message, state: FSMContext) -> None:
    """Handle user's response to clarifying question about ambiguous data.

    If user responds with 'ok' or equivalent, proceeds with current parse.
    Otherwise, re-runs the pipeline with original text augmented by
    the user's clarification.

    Per PIPELINE-02.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    data = await state.get_data()
    user_response = (message.text or "").strip()

    audit.log_entry("clarification_received", {"response": user_response})

    # If user accepts current parse as-is
    if user_response.lower() in ("ok", "okay", "yes", "proceed", "confirm", "y"):
        result = data.get("pipeline_result", {})
        summary = format_race_summary(result)
        await state.set_state(PipelineStates.awaiting_parse_confirm)
        await message.answer(
            f"{header}{summary}\n\n"
            "Please confirm this race data is correct:",
            reply_markup=confirm_parse_kb(),
        )
        return

    # Re-run pipeline with original text + user clarification appended
    original_input = data.get("raw_input", "")
    augmented_input = f"{original_input}\n\n[User clarification: {user_response}]"

    await state.set_state(PipelineStates.idle)
    await _run_parse_pipeline(message, state, augmented_input)


# Handle bankroll text input when waiting for manual entry
@router.message(PipelineStates.awaiting_bankroll_input, F.text)
async def handle_bankroll_input(message: Message, state: FSMContext) -> None:
    """Handle user's manual bankroll entry.

    Parses first number found in user's text as USDT balance.
    Sets balance in DB and transitions back to idle.

    Per BANK-03 / D-12.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    text = (message.text or "").strip()
    match = re.search(r"[\d.]+", text)
    if not match:
        await message.answer(
            f"{header}"
            "Please enter a valid USDT amount (e.g., 150):",
            reply_markup=bankroll_input_kb(),
        )
        return

    try:
        amount = float(match.group())
        repo = BankrollRepository(db_path=settings.database_path)
        repo.set_balance(amount)
        stake_pct = repo.get_stake_pct()
        audit.log_entry("bankroll_set", {"balance": amount, "source": "manual_input"})

        await state.set_state(PipelineStates.idle)
        await message.answer(
            f"Balance set to {amount:.2f} USDT.\n"
            f"Stake size: {stake_pct*100:.1f}% ({amount * stake_pct:.2f} USDT per bet)\n"
            f"To adjust stake %: /stake <number>\n\n"
            "Pipeline complete. Paste new race data when ready."
        )
    except ValueError:
        await message.answer(
            f"{header}"
            "Invalid amount. Please enter a number (e.g., 150):",
            reply_markup=bankroll_input_kb(),
        )
