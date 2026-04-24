import pytest
from pathlib import Path

from services.stake.main import build_runtime, StakeRuntime
from services.stake.invariants.rules import InvariantViolation


@pytest.fixture(autouse=True)
async def _reset_checkpointer():
    """AsyncSqliteSaver singleton state leaks between tests — reset it."""
    import services.stake.pipeline.checkpointer as cp
    cp._checkpointer = None
    cp._checkpointer_cm = None
    yield
    if cp._checkpointer is not None:
        from services.stake.pipeline.checkpointer import shutdown_checkpointer
        await shutdown_checkpointer()


@pytest.mark.asyncio
async def test_paper_mode_runtime_builds(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: paper\nlive_unlock: false\n")
    monkeypatch.setenv("STAKE_DATABASE_PATH", str(tmp_path / "data.sqlite"))
    monkeypatch.setenv("STAKE_CHECKPOINTER_PATH", str(tmp_path / "cp.sqlite"))
    runtime = await build_runtime(config_path=cfg)
    try:
        assert isinstance(runtime, StakeRuntime)
        assert runtime.settings.mode == "paper"
        assert runtime.checker is not None
        assert runtime.graph is not None
        assert runtime.bankroll_repo is not None
        assert runtime.samples_repo is not None
        assert runtime.traces_repo is not None
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_live_mode_rejected_at_load(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: live\nlive_unlock: true\n")
    # Loader raises InvariantViolation(I1) BEFORE reaching build_runtime's
    # checker, but since build_runtime calls load_config first, the same
    # exception propagates.
    with pytest.raises(InvariantViolation) as exc:
        await build_runtime(config_path=cfg)
    assert exc.value.rule_id == "I1"


@pytest.mark.asyncio
async def test_build_runtime_accepts_injected_callables(tmp_path: Path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: paper\n")
    monkeypatch.setenv("STAKE_DATABASE_PATH", str(tmp_path / "data.sqlite"))
    monkeypatch.setenv("STAKE_CHECKPOINTER_PATH", str(tmp_path / "cp.sqlite"))
    parse_node = AsyncMock(return_value={})
    research_node = AsyncMock(return_value={})
    analyst_llm = AsyncMock(return_value={"intents": [], "adjustments": []})
    reflection_writer = MagicMock()
    reflection_writer.run = AsyncMock(return_value={})
    runtime = await build_runtime(
        config_path=cfg,
        parse_node=parse_node, research_node=research_node,
        analyst_llm=analyst_llm, reflection_writer=reflection_writer,
    )
    try:
        assert runtime.graph is not None
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: paper\n")
    monkeypatch.setenv("STAKE_DATABASE_PATH", str(tmp_path / "data.sqlite"))
    monkeypatch.setenv("STAKE_CHECKPOINTER_PATH", str(tmp_path / "cp.sqlite"))
    runtime = await build_runtime(config_path=cfg)
    await runtime.shutdown()
    await runtime.shutdown()  # must not raise


@pytest.mark.asyncio
async def test_build_runtime_applies_migrations(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mode: paper\n")
    db_path = tmp_path / "data.sqlite"
    monkeypatch.setenv("STAKE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("STAKE_CHECKPOINTER_PATH", str(tmp_path / "cp.sqlite"))
    runtime = await build_runtime(config_path=cfg)
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('stake_bet_slips', 'stake_calibration_samples', 'stake_audit_traces')"
        ).fetchall()
        assert len(rows) == 3
        conn.close()
    finally:
        await runtime.shutdown()
