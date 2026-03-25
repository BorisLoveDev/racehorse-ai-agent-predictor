"""
Pipeline handlers for the Stake Advisor Bot.

Handler registration order matters in aiogram — more specific state filters
must come BEFORE the catch-all F.text handler.

Order: clarification → bankroll_input → paste (idle) → document (idle) → catch-all
"""

import io
import logging
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

logger = logging.getLogger("stake")
router = Router(name="pipeline")


async def _run_parse_pipeline(message: Message, state: FSMContext, raw_text: str) -> None:
    """Run LLM parse pipeline on raw text. Handles progressive updates,
    ambiguous data, and formatted summary display."""
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

    await state.set_state(PipelineStates.parsing)
    await state.update_data(raw_input=raw_text)
    audit.log_entry("pipeline_start", {"raw_input": raw_text[:500]})
    await message.answer(f"{header}Parsing race data...")

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
        await message.answer(f"{header}Parse error: {result['error']}\n\nPlease try again.")
        audit.log_entry("parse_error", {"error": result["error"]})
        return

    # Store pipeline result (must be JSON-serializable for Redis)
    parsed_race = result.get("parsed_race")
    serializable_result = {
        k: (v.model_dump() if hasattr(v, "model_dump") else v)
        for k, v in result.items()
    }
    await state.update_data(
        pipeline_result=serializable_result,
        parsed_race_json=parsed_race.model_dump_json() if parsed_race else None,
    )

    audit.log_entry("parse_complete", {
        "parsed_race": parsed_race.model_dump() if parsed_race else None,
        "overround_raw": result.get("overround_raw"),
        "overround_active": result.get("overround_active"),
        "ambiguous_fields": result.get("ambiguous_fields"),
    })

    summary = format_race_summary(result)

    # PIPELINE-02: ambiguous data → clarifying question
    ambiguous = result.get("ambiguous_fields") or []
    if ambiguous:
        await state.set_state(PipelineStates.awaiting_clarification)
        await state.update_data(ambiguous_fields=ambiguous)

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

    # Normal flow: show summary with confirm buttons
    await state.set_state(PipelineStates.awaiting_parse_confirm)
    await message.answer(
        f"{header}{summary}\n\n"
        "Please confirm this race data is correct:",
        reply_markup=confirm_parse_kb(),
    )


# ── Handlers with SPECIFIC state filters FIRST ──────────────────────────

# PIPELINE-02: clarification response (MUST be before catch-all)
@router.message(PipelineStates.awaiting_clarification, F.text)
async def handle_clarification(message: Message, state: FSMContext) -> None:
    """Handle user's response to clarifying question about ambiguous data."""
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    data = await state.get_data()
    user_response = (message.text or "").strip()
    audit.log_entry("clarification_received", {"response": user_response})

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

    original_input = data.get("raw_input", "")
    augmented_input = f"{original_input}\n\n[User clarification: {user_response}]"
    await state.set_state(PipelineStates.idle)
    await _run_parse_pipeline(message, state, augmented_input)


# BANK-03: bankroll manual input (MUST be before catch-all)
@router.message(PipelineStates.awaiting_bankroll_input, F.text)
async def handle_bankroll_input(message: Message, state: FSMContext) -> None:
    """Handle user's manual bankroll entry."""
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
            f"To adjust stake %: /stake 3\n\n"
            "Pipeline complete. Paste new race data when ready."
        )
    except ValueError:
        await message.answer(
            f"{header}"
            "Invalid amount. Please enter a number (e.g., 150):",
            reply_markup=bankroll_input_kb(),
        )


# ── General handlers AFTER specific ones ─────────────────────────────────

# INPUT-01: text paste in idle state
@router.message(PipelineStates.idle, F.text)
async def handle_paste(message: Message, state: FSMContext) -> None:
    """Handle raw text paste in idle state."""
    if message.text and message.text.startswith("/"):
        return
    await _run_parse_pipeline(message, state, message.text or "")


# INPUT-02: .txt file upload in idle state
@router.message(PipelineStates.idle, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot) -> None:
    """Handle .txt file upload in idle state."""
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


# Catch-all: text when no state set or active pipeline (MUST BE LAST)
@router.message(F.text)
async def handle_text_fallback(message: Message, state: FSMContext) -> None:
    """Catch-all for text when no specific state handler matched."""
    if message.text and message.text.startswith("/"):
        return

    current = await state.get_state()
    if current is None or current == PipelineStates.idle.state:
        if current is None:
            await state.set_state(PipelineStates.idle)
        await _run_parse_pipeline(message, state, message.text or "")
    else:
        # PIPELINE-05: active pipeline warning
        settings = get_stake_settings()
        header = balance_header(settings.database_path)
        await message.answer(
            f"{header}"
            "A pipeline is already active. Use /cancel first."
        )
