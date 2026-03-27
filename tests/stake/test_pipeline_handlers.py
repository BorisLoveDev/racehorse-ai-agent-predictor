"""
Unit tests for pipeline handler state transitions.

Tests verify FSM state machine behavior for the Stake Advisor pipeline
without making real LLM calls, Telegram API calls, or database writes.

All dependencies (graph, parser, repo, aiogram objects) are mocked.

State transitions tested:
    1. idle + text paste -> parsing -> awaiting_parse_confirm (normal flow)
    2. idle + text paste -> parsing -> awaiting_clarification (ambiguous data, PIPELINE-02)
    3. awaiting_parse_confirm + confirm -> awaiting_bankroll_confirm (bankroll detected)
    4. awaiting_parse_confirm + confirm -> awaiting_bankroll_input (no bankroll)
    5. awaiting_parse_confirm + confirm -> idle (bankroll exists in DB)
    6. awaiting_parse_confirm + reject -> idle
    7. active pipeline + new paste -> warning (PIPELINE-05)
    8. awaiting_clarification + user answer "ok" -> awaiting_parse_confirm
    9. any state + /cancel -> idle (tested in commands; included here for completeness)
"""

import json
import tempfile
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.stake.states import PipelineStates
from services.stake.parser.models import ParsedRace, RunnerInfo


# ── Shared fixtures ──────────────────────────────────────────────────────────

def make_fsm_context(current_state=None, data=None):
    """Create a mock FSMContext with configurable state and data."""
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=current_state)
    ctx.set_state = AsyncMock()
    ctx.get_data = AsyncMock(return_value=data or {})
    ctx.update_data = AsyncMock()
    ctx.clear = AsyncMock()
    return ctx


def make_message(text="Sample race paste text"):
    """Create a mock aiogram Message."""
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def make_parsed_race(with_bankroll=None, ambiguous=False, track="Churchill Downs"):
    """Create a minimal ParsedRace for testing."""
    runners = [
        RunnerInfo(number=1, name="Horse A", win_odds=2.5, win_odds_format="decimal"),
        RunnerInfo(number=2, name="Horse B", win_odds=3.0, win_odds_format="decimal"),
    ]
    if ambiguous:
        # Add runners without odds to trigger ambiguity
        runners += [
            RunnerInfo(number=3, name="Horse C"),
            RunnerInfo(number=4, name="Horse D"),
        ]
    return ParsedRace(
        track=track,
        race_number="5",
        runners=runners,
        detected_bankroll=with_bankroll,
    )


def make_pipeline_result(with_bankroll=None, ambiguous_fields=None, track="Churchill Downs"):
    """Create a fake pipeline result dict."""
    parsed_race = make_parsed_race(with_bankroll=with_bankroll, track=track)
    return {
        "parsed_race": parsed_race,
        "detected_bankroll": with_bankroll,
        "ambiguous_fields": ambiguous_fields or [],
        "enriched_runners": [
            {"number": 1, "name": "Horse A", "decimal_odds": 2.5, "implied_prob": 0.4, "odds_drift": None, "status": "active", "tags": None},
            {"number": 2, "name": "Horse B", "decimal_odds": 3.0, "implied_prob": 0.333, "odds_drift": None, "status": "active", "tags": None},
        ],
        "overround_raw": 1.0733,
        "overround_active": 1.0733,
    }


# ── Test 1: Normal paste flow -> awaiting_parse_confirm ──────────────────────

@pytest.mark.asyncio
async def test_normal_paste_transitions_to_awaiting_parse_confirm():
    """idle + text paste with clean parse -> awaiting_parse_confirm."""
    from services.stake.handlers.pipeline import _run_parse_pipeline

    state = make_fsm_context(current_state=PipelineStates.idle.state)
    message = make_message("Churchill Downs Race 5...")

    pipeline_result = make_pipeline_result(ambiguous_fields=[])

    with patch("services.stake.handlers.pipeline.build_pipeline_graph") as mock_graph, \
         patch("services.stake.handlers.pipeline.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.pipeline.AuditLogger") as mock_audit_cls:

        mock_settings.return_value.database_path = ":memory:"
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value=pipeline_result)
        mock_graph.return_value = compiled
        mock_audit = MagicMock()
        mock_audit.log_entry = MagicMock()
        mock_audit_cls.return_value = mock_audit

        with patch("services.stake.handlers.pipeline.BankrollRepository") as mock_repo_cls, \
             patch("services.stake.handlers.pipeline.balance_header", return_value="Balance: 100 USDT\n"):
            mock_repo_cls.return_value.get_balance = MagicMock(return_value=None)
            await _run_parse_pipeline(message, state, "Churchill Downs Race 5...")

    # Should transition through parsing to awaiting_parse_confirm
    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.parsing in set_state_calls
    assert PipelineStates.awaiting_parse_confirm in set_state_calls


# ── Test 2: Ambiguous parse -> awaiting_clarification (PIPELINE-02) ──────────

@pytest.mark.asyncio
async def test_ambiguous_parse_transitions_to_awaiting_clarification():
    """idle + text paste with ambiguous parse -> awaiting_clarification."""
    from services.stake.handlers.pipeline import _run_parse_pipeline

    state = make_fsm_context(current_state=PipelineStates.idle.state)
    message = make_message("Some ambiguous race text...")

    pipeline_result = make_pipeline_result(ambiguous_fields=["track", "missing_odds"])

    with patch("services.stake.handlers.pipeline.build_pipeline_graph") as mock_graph, \
         patch("services.stake.handlers.pipeline.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.pipeline.AuditLogger") as mock_audit_cls:

        mock_settings.return_value.database_path = ":memory:"
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value=pipeline_result)
        mock_graph.return_value = compiled
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())

        with patch("services.stake.handlers.pipeline.balance_header", return_value=""):
            await _run_parse_pipeline(message, state, "Some ambiguous race text...")

    # Should transition to awaiting_clarification
    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.awaiting_clarification in set_state_calls
    assert PipelineStates.awaiting_parse_confirm not in set_state_calls


# ── Test 3: Confirm -> awaiting_bankroll_confirm (bankroll in paste) ─────────

@pytest.mark.asyncio
async def test_confirm_with_detected_bankroll_triggers_bankroll_confirm():
    """awaiting_parse_confirm + confirm + detected bankroll -> awaiting_bankroll_confirm."""
    from services.stake.handlers.callbacks import handle_parse_confirm

    pipeline_result = make_pipeline_result(with_bankroll=150.0)
    state = make_fsm_context(
        current_state=PipelineStates.awaiting_parse_confirm.state,
        data={"pipeline_result": pipeline_result},
    )

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "yes"

    with patch("services.stake.handlers.callbacks.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.callbacks.BankrollRepository") as mock_repo_cls, \
         patch("services.stake.handlers.callbacks.AuditLogger") as mock_audit_cls, \
         patch("services.stake.handlers.callbacks.balance_header", return_value=""):

        mock_settings.return_value.database_path = ":memory:"
        mock_repo = MagicMock()
        mock_repo.get_balance = MagicMock(return_value=None)
        mock_repo.get_stake_pct = MagicMock(return_value=0.02)
        mock_repo_cls.return_value = mock_repo
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())

        await handle_parse_confirm(callback, callback_data, state)

    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.awaiting_bankroll_confirm in set_state_calls


# ── Test 4: Confirm -> awaiting_bankroll_input (no bankroll anywhere) ─────────

@pytest.mark.asyncio
async def test_confirm_without_bankroll_triggers_bankroll_input():
    """awaiting_parse_confirm + confirm + no bankroll -> awaiting_bankroll_input."""
    from services.stake.handlers.callbacks import handle_parse_confirm

    pipeline_result = make_pipeline_result(with_bankroll=None)
    state = make_fsm_context(
        current_state=PipelineStates.awaiting_parse_confirm.state,
        data={"pipeline_result": pipeline_result},
    )

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "yes"

    with patch("services.stake.handlers.callbacks.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.callbacks.BankrollRepository") as mock_repo_cls, \
         patch("services.stake.handlers.callbacks.AuditLogger") as mock_audit_cls, \
         patch("services.stake.handlers.callbacks.balance_header", return_value=""):

        mock_settings.return_value.database_path = ":memory:"
        mock_repo = MagicMock()
        mock_repo.get_balance = MagicMock(return_value=None)  # No bankroll in DB either
        mock_repo.get_stake_pct = MagicMock(return_value=0.02)
        mock_repo_cls.return_value = mock_repo
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())

        await handle_parse_confirm(callback, callback_data, state)

    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.awaiting_bankroll_input in set_state_calls


# ── Test 5: Confirm -> idle (bankroll already in DB) ─────────────────────────

@pytest.mark.asyncio
async def test_confirm_with_db_bankroll_transitions_to_idle():
    """awaiting_parse_confirm + confirm + bankroll in DB -> idle."""
    from services.stake.handlers.callbacks import handle_parse_confirm

    pipeline_result = make_pipeline_result(with_bankroll=None)
    state = make_fsm_context(
        current_state=PipelineStates.awaiting_parse_confirm.state,
        data={"pipeline_result": pipeline_result},
    )

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "yes"

    with patch("services.stake.handlers.callbacks.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.callbacks.BankrollRepository") as mock_repo_cls, \
         patch("services.stake.handlers.callbacks.AuditLogger") as mock_audit_cls, \
         patch("services.stake.handlers.callbacks.balance_header", return_value=""), \
         patch("services.stake.handlers.callbacks.build_analysis_graph") as mock_graph:

        mock_settings.return_value.database_path = ":memory:"
        mock_settings.return_value.sizing.skip_overround_threshold = 15.0
        mock_repo = MagicMock()
        mock_repo.get_balance = MagicMock(return_value=200.0)  # Has balance in DB
        mock_repo_cls.return_value = mock_repo
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value={"recommendation_text": "test", "skip_signal": False})
        mock_graph.return_value = compiled

        await handle_parse_confirm(callback, callback_data, state)

    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.idle in set_state_calls


# ── Test 6: Reject parse -> idle ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_parse_transitions_to_idle():
    """awaiting_parse_confirm + reject -> idle."""
    from services.stake.handlers.callbacks import handle_parse_confirm

    state = make_fsm_context(current_state=PipelineStates.awaiting_parse_confirm.state)

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()

    callback_data = MagicMock()
    callback_data.action = "no"

    with patch("services.stake.handlers.callbacks.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.callbacks.AuditLogger") as mock_audit_cls, \
         patch("services.stake.handlers.callbacks.balance_header", return_value=""):

        mock_settings.return_value.database_path = ":memory:"
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())

        await handle_parse_confirm(callback, callback_data, state)

    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.idle in set_state_calls


# ── Test 7: Active pipeline + new paste -> warning (PIPELINE-05) ─────────────

@pytest.mark.asyncio
async def test_active_pipeline_returns_warning_on_new_paste():
    """Non-idle state + new paste -> warning message, no state transition."""
    from services.stake.handlers.pipeline import _run_parse_pipeline

    state = make_fsm_context(current_state=PipelineStates.parsing.state)
    message = make_message("Another race paste...")

    with patch("services.stake.handlers.pipeline.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.pipeline.balance_header", return_value=""):

        mock_settings.return_value.database_path = ":memory:"
        await _run_parse_pipeline(message, state, "Another race paste...")

    # Should NOT have called set_state (no transition) except possibly early check
    # The warning message should be sent
    message.answer.assert_called_once()
    warning_text = message.answer.call_args.args[0]
    assert "already active" in warning_text or "cancel" in warning_text.lower()


# ── Test 8: awaiting_clarification + "ok" -> awaiting_parse_confirm ──────────

@pytest.mark.asyncio
async def test_clarification_ok_transitions_to_awaiting_parse_confirm():
    """awaiting_clarification + 'ok' response -> awaiting_parse_confirm."""
    from services.stake.handlers.pipeline import handle_clarification

    pipeline_result = make_pipeline_result(ambiguous_fields=["track"])
    state = make_fsm_context(
        current_state=PipelineStates.awaiting_clarification.state,
        data={"pipeline_result": pipeline_result, "raw_input": "original text"},
    )

    message = make_message("ok")

    with patch("services.stake.handlers.pipeline.get_stake_settings") as mock_settings, \
         patch("services.stake.handlers.pipeline.AuditLogger") as mock_audit_cls, \
         patch("services.stake.handlers.pipeline.balance_header", return_value=""):

        mock_settings.return_value.database_path = ":memory:"
        mock_audit_cls.return_value = MagicMock(log_entry=MagicMock())

        await handle_clarification(message, state)

    set_state_calls = [call.args[0] for call in state.set_state.call_args_list]
    assert PipelineStates.awaiting_parse_confirm in set_state_calls


# ── Test 9: AuditLogger writes JSONL correctly ───────────────────────────────

def test_audit_logger_writes_jsonl():
    """AuditLogger.log_entry writes valid JSON lines to the file."""
    from services.stake.audit.logger import AuditLogger

    with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as f:
        tmp_path = f.name

    try:
        audit = AuditLogger(log_path=tmp_path)
        audit.log_entry("pipeline_start", {"raw_input": "test text"})
        audit.log_entry("parse_complete", {"overround": 1.05})

        with open(tmp_path) as f:
            lines = f.readlines()

        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        assert entry1["event"] == "pipeline_start"
        assert entry1["raw_input"] == "test text"
        assert "timestamp" in entry1

        entry2 = json.loads(lines[1])
        assert entry2["event"] == "parse_complete"
        assert entry2["overround"] == 1.05
    finally:
        os.unlink(tmp_path)
