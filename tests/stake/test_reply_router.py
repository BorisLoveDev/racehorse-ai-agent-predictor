"""Tests for reply_router — maps replies to bot cards back to their run."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.stake.bankroll.migrations import apply_migrations
from services.stake.handlers.reply_router import (
    _looks_like_bot_card, _lookup_run_by_message_id, _mark_run_result,
    handle_reply,
)
from services.stake.states import PipelineStates


# ---------- pure helpers ----------

@pytest.mark.parametrize("text,expected", [
    ("Bet Recommendations\nSwift Star (#3)", True),
    ("No +EV bets\nBookmaker margin 17.9%", True),
    ("AI Ranking (no bet placed):", True),
    ("Exotic Ideas (not sized...)", True),
    ("SKIP — margin too high", True),
    ("", False),
    (None, False),
    ("Just some other bot text about balance", False),
])
def test_looks_like_bot_card_markers(text, expected):
    assert _looks_like_bot_card(text) is expected


def test_lookup_run_by_message_id_missing_returns_none(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.close()
    assert _lookup_run_by_message_id(str(db), 12345) is None


def test_lookup_run_by_message_id_finds_row(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO stake_pipeline_runs (raw_input, parsed_race_json, user_confirmed, message_id) "
        "VALUES ('paste', '{}', 1, 555)"
    )
    conn.commit()
    conn.close()
    row = _lookup_run_by_message_id(str(db), 555)
    assert row is not None
    assert row["raw_input"] == "paste"


def test_mark_run_result_writes_positions(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO stake_pipeline_runs (run_id, raw_input, parsed_race_json, user_confirmed, message_id) "
        "VALUES (7, 'paste', '{}', 1, 555)"
    )
    conn.commit()
    conn.close()

    _mark_run_result(str(db), run_id=7, positions_text="1 3 5 2 4")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT result_positions, result_reported_at FROM stake_pipeline_runs WHERE run_id=7"
    ).fetchone()
    conn.close()
    assert row[0] == "1 3 5 2 4"
    assert row[1] is not None  # datetime stamped


# ---------- handler behaviour ----------

def _reply_msg(*, text: str, replied_text: str, replied_from_bot: bool = True,
               replied_msg_id: int = 555):
    replied = MagicMock()
    replied.text = replied_text
    replied.caption = None
    replied.message_id = replied_msg_id
    replied_from_user = MagicMock()
    replied_from_user.is_bot = replied_from_bot
    replied.from_user = replied_from_user

    msg = MagicMock()
    msg.text = text
    msg.reply_to_message = replied
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=42)
    msg.chat = MagicMock(id=111)
    return msg


def _state_mock():
    s = MagicMock()
    s.update_data = AsyncMock()
    s.set_state = AsyncMock()
    return s


def test_filter_rejects_non_bot_reply():
    """Non-bot replies must NOT match the router's filter — otherwise the
    handler would consume the update and the paste flow would never see it.

    The filter is `F.reply_to_message.from_user.is_bot`; we probe it by
    resolving the magic filter against a fake Message-shaped object.
    """
    from services.stake.handlers import reply_router as mod
    # Find the handler's filter chain. We resolve the F filter manually.
    from aiogram import F
    filter_expr = F.reply_to_message.from_user.is_bot

    # Non-bot reply — filter must evaluate falsy
    replied = MagicMock()
    replied.from_user = MagicMock(is_bot=False)
    msg_non_bot = MagicMock(reply_to_message=replied)
    assert not bool(filter_expr.resolve(msg_non_bot))

    # Bot reply — filter must evaluate truthy
    replied2 = MagicMock()
    replied2.from_user = MagicMock(is_bot=True)
    msg_bot = MagicMock(reply_to_message=replied2)
    assert bool(filter_expr.resolve(msg_bot))

    # No reply at all — filter falsy
    msg_no_reply = MagicMock(reply_to_message=None)
    assert not bool(filter_expr.resolve(msg_no_reply))


@pytest.mark.asyncio
async def test_reply_to_unknown_bot_card_with_markers_warns_couldnt_find(tmp_path: Path, monkeypatch):
    """Reply whose replied-to text looks like a pipeline card but has no
    DB row (e.g. pre-hotfix) — user is told explicitly, not silently dropped.
    """
    db = tmp_path / "data.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.close()
    monkeypatch.setattr(
        "services.stake.handlers.reply_router.get_stake_settings",
        lambda: MagicMock(database_path=str(db)),
    )
    msg = _reply_msg(
        text="1 3 5",
        replied_text="Bet Recommendations\nSwift Star",
        replied_msg_id=9999,
    )
    state = _state_mock()
    await handle_reply(msg, state)
    msg.answer.assert_awaited()
    reply_text = msg.answer.await_args.args[0].lower()
    assert "couldn" in reply_text
    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_reply_to_non_pipeline_bot_message_answers_guidance(tmp_path: Path, monkeypatch):
    """Reply to a bot message that ISN'T a recommendation card (e.g. a
    /start greeting): we still respond, so the user knows their reply was
    seen but the feature only handles race-card replies. No silent drop."""
    db = tmp_path / "data.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.close()
    monkeypatch.setattr(
        "services.stake.handlers.reply_router.get_stake_settings",
        lambda: MagicMock(database_path=str(db)),
    )
    msg = _reply_msg(
        text="what about this",
        replied_text="Welcome to the Stake racing advisor. Paste a race to begin.",
        replied_msg_id=1,
    )
    state = _state_mock()
    await handle_reply(msg, state)
    msg.answer.assert_awaited_once()
    reply_text = msg.answer.await_args.args[0].lower()
    # Informative guidance, not a silent drop
    assert "new (non-reply) message" in reply_text or "non-reply" in reply_text
    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_reply_parses_result_and_stores(tmp_path: Path, monkeypatch):
    db = tmp_path / "data.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO stake_pipeline_runs (run_id, raw_input, parsed_race_json, user_confirmed, message_id) "
        "VALUES (7, 'paste', '{}', 1, 555)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "services.stake.handlers.reply_router.get_stake_settings",
        lambda: MagicMock(database_path=str(db)),
    )

    # Mock ResultParser to return a canned ParsedResult without real LLM call
    from services.stake.results.models import ParsedResult
    parsed = ParsedResult(
        finishing_order=[1, 3, 5, 2, 4],
        finishing_names=[],
        confidence="high",
        raw_text="1 3 5 2 4",
    )

    with patch("services.stake.handlers.reply_router.ResultParser") as MockParser:
        MockParser.return_value.parse = AsyncMock(return_value=parsed)

        msg = _reply_msg(
            text="1 3 5 2 4",
            replied_text="No +EV bets\nBookmaker margin 17.9%",
            replied_msg_id=555,
        )
        # Status-msg returned by msg.answer is another MagicMock
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        msg.answer = AsyncMock(return_value=status_msg)
        state = _state_mock()

        await handle_reply(msg, state)

    # Processing indicator shown first
    first_call_text = msg.answer.await_args_list[0].args[0]
    assert "parsing" in first_call_text.lower() or "⏳" in first_call_text

    # Result persisted
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT result_positions, result_reported_at FROM stake_pipeline_runs WHERE run_id=7"
    ).fetchone()
    conn.close()
    assert row[0] == "1 3 5 2 4"
    assert row[1] is not None

    # FSM gets parsed_result and transitions to confirming_result
    state.update_data.assert_awaited_once()
    ud_kwargs = state.update_data.await_args.kwargs
    assert ud_kwargs["run_id"] == 7
    assert ud_kwargs["is_placed"] is False
    state.set_state.assert_awaited_once_with(PipelineStates.confirming_result)


@pytest.mark.asyncio
async def test_reply_double_submit_warns_before_overwrite(tmp_path: Path, monkeypatch):
    db = tmp_path / "data.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO stake_pipeline_runs (run_id, raw_input, parsed_race_json, user_confirmed, message_id, result_reported_at) "
        "VALUES (9, 'paste', '{}', 1, 777, '2026-04-24T20:00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "services.stake.handlers.reply_router.get_stake_settings",
        lambda: MagicMock(database_path=str(db)),
    )
    from services.stake.results.models import ParsedResult
    parsed = ParsedResult(finishing_order=[1], finishing_names=[], confidence="high", raw_text="1")

    with patch("services.stake.handlers.reply_router.ResultParser") as MockParser:
        MockParser.return_value.parse = AsyncMock(return_value=parsed)

        msg = _reply_msg(text="1", replied_text="Bet Recommendations",
                         replied_msg_id=777)
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        msg.answer = AsyncMock(return_value=status_msg)
        await handle_reply(msg, _state_mock())

    # Expect at least 2 answer calls: the warning + the "Parsing result" status
    # (plus possibly the confirm card if edit_text path fails)
    warning_calls = [
        c for c in msg.answer.await_args_list
        if "already submitted" in (c.args[0] if c.args else "").lower()
    ]
    assert warning_calls, "Expected double-submit warning message"


@pytest.mark.asyncio
async def test_reply_with_empty_text_returns(tmp_path: Path, monkeypatch):
    db = tmp_path / "data.sqlite"
    conn = sqlite3.connect(db)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO stake_pipeline_runs (run_id, raw_input, parsed_race_json, user_confirmed, message_id) "
        "VALUES (1, 'paste', '{}', 1, 100)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "services.stake.handlers.reply_router.get_stake_settings",
        lambda: MagicMock(database_path=str(db)),
    )

    msg = _reply_msg(text="", replied_text="Bet Recommendations", replied_msg_id=100)
    await handle_reply(msg, _state_mock())
    msg.answer.assert_not_called()
