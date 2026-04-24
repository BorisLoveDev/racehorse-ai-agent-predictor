import pytest
from unittest.mock import MagicMock, AsyncMock

from services.stake.handlers.risk_commands import (
    handle_kill, handle_resume, DRAWDOWN_UNLOCK_TOKEN_PREFIX,
)


def _msg(text: str = ""):
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_kill_cancels_all_active_races():
    runner = MagicMock()
    runner.active_races = {"R1", "R2", "R3"}
    runner.cancel_race = AsyncMock()
    msg = _msg("/kill")
    await handle_kill(msg, runner=runner)
    assert runner.cancel_race.await_count == 3
    cancelled = {c.args[0] for c in runner.cancel_race.await_args_list}
    assert cancelled == {"R1", "R2", "R3"}
    msg.answer.assert_awaited_once()
    assert "kill" in msg.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_kill_when_no_active_races_still_replies():
    runner = MagicMock()
    runner.active_races = set()
    runner.cancel_race = AsyncMock()
    msg = _msg("/kill")
    await handle_kill(msg, runner=runner)
    runner.cancel_race.assert_not_awaited()
    msg.answer.assert_awaited_once()  # still confirms to user


@pytest.mark.asyncio
async def test_resume_when_not_locked_reports_so():
    runner = MagicMock()
    runner.drawdown_locked = False
    msg = _msg("/resume")
    await handle_resume(msg, runner=runner)
    runner.unlock = MagicMock()
    runner.unlock.assert_not_called()
    assert "not locked" in msg.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_resume_locked_without_token_rejects():
    runner = MagicMock()
    runner.drawdown_locked = True
    runner.expected_unlock_token = DRAWDOWN_UNLOCK_TOKEN_PREFIX + "abcd1234"
    runner.unlock = MagicMock()
    msg = _msg("/resume")
    await handle_resume(msg, runner=runner)
    runner.unlock.assert_not_called()
    reply = msg.answer.await_args.args[0]
    assert DRAWDOWN_UNLOCK_TOKEN_PREFIX in reply


@pytest.mark.asyncio
async def test_resume_with_valid_token_unlocks():
    token = DRAWDOWN_UNLOCK_TOKEN_PREFIX + "abcd1234"
    runner = MagicMock()
    runner.drawdown_locked = True
    runner.expected_unlock_token = token
    runner.unlock = MagicMock()
    msg = _msg(f"/resume {token}")
    await handle_resume(msg, runner=runner)
    runner.unlock.assert_called_once()
    reply = msg.answer.await_args.args[0]
    assert "unlock" in reply.lower() or "resumed" in reply.lower()


@pytest.mark.asyncio
async def test_resume_with_wrong_token_rejects():
    runner = MagicMock()
    runner.drawdown_locked = True
    runner.expected_unlock_token = DRAWDOWN_UNLOCK_TOKEN_PREFIX + "correct"
    runner.unlock = MagicMock()
    msg = _msg(f"/resume {DRAWDOWN_UNLOCK_TOKEN_PREFIX}wrong")
    await handle_resume(msg, runner=runner)
    runner.unlock.assert_not_called()
    reply = msg.answer.await_args.args[0].lower()
    assert "wrong" in reply or "invalid" in reply or DRAWDOWN_UNLOCK_TOKEN_PREFIX in reply


@pytest.mark.asyncio
async def test_resume_with_empty_expected_token_rejects():
    runner = MagicMock()
    runner.drawdown_locked = True
    runner.expected_unlock_token = None
    runner.unlock = MagicMock()
    msg = _msg("/resume unlock-xyz")
    await handle_resume(msg, runner=runner)
    runner.unlock.assert_not_called()
