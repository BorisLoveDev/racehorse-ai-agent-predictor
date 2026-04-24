import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.checker import InvariantChecker
from services.stake.pipeline.checkpointer import init_checkpointer, shutdown_checkpointer
from services.stake.pipeline.graph import compile_race_graph
from services.stake.probability.calibration import IdentityCalibrator, CalibratorRegistry


@pytest.fixture(autouse=True)
async def _clean_checkpointer():
    import services.stake.pipeline.checkpointer as cp
    cp._checkpointer = None
    cp._checkpointer_cm = None
    yield
    if cp._checkpointer is not None:
        await shutdown_checkpointer()


async def _make_graph(tmp_path: Path):
    cp = await init_checkpointer(str(tmp_path / "cp.sqlite"))
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    registry = CalibratorRegistry(default=IdentityCalibrator())

    parse_node = AsyncMock(return_value={
        "parsed_race": {"track": "T"},
        "enriched_runners": [],
        "overround_active": 0.0,
        "missing_fields": [],
    })
    research_node = AsyncMock(return_value={"research_results": {}})
    analyst_llm = AsyncMock(return_value={"intents": [], "adjustments": []})
    samples_repo = MagicMock()
    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 100.0
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0
    reflection_writer = MagicMock()
    reflection_writer.run = AsyncMock(return_value={"lessons_appended": 0})
    traces_repo = MagicMock()
    recorder_provider = lambda race_id: None  # Phase 1 tests: no audit recorder

    graph = compile_race_graph(
        settings=settings, checker=checker, checkpointer=cp,
        parse_node=parse_node, research_node=research_node,
        analyst_llm=analyst_llm, samples_repo=samples_repo,
        bankroll_repo=bankroll_repo, results_evaluator=None,
        calibrator_registry=registry,
        reflection_writer=reflection_writer,
        traces_repo=traces_repo,
        recorder_provider=recorder_provider,
    )
    return graph


@pytest.mark.asyncio
async def test_all_expected_nodes_registered(tmp_path: Path):
    graph = await _make_graph(tmp_path)
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "ingest", "parse", "interrupt_gate", "research",
        "probability_model", "analyst", "sizer", "decision_maker",
        "interrupt_approval", "result_recorder", "settlement",
        "reflection_update",
    }
    assert expected.issubset(nodes), f"missing: {expected - nodes}"


@pytest.mark.asyncio
async def test_compile_returns_runnable_with_checkpointer(tmp_path: Path):
    graph = await _make_graph(tmp_path)
    # Compiled graphs expose .ainvoke
    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_ingest_defaults_source_type_to_text(tmp_path: Path):
    # ingest passes-through state but normalises source_type; probe it in isolation.
    from services.stake.pipeline.graph import _ingest_node
    out = await _ingest_node({"raw_input": "x"})
    assert out["source_type"] == "text"


@pytest.mark.asyncio
async def test_ingest_preserves_known_source_type(tmp_path: Path):
    from services.stake.pipeline.graph import _ingest_node
    for st in ("text", "screenshot", "photo", "voice"):
        out = await _ingest_node({"source_type": st})
        assert out["source_type"] == st


@pytest.mark.asyncio
async def test_ingest_rewrites_unknown_source_type(tmp_path: Path):
    from services.stake.pipeline.graph import _ingest_node
    out = await _ingest_node({"source_type": "bogus"})
    assert out["source_type"] == "text"


@pytest.mark.asyncio
async def test_end_to_end_clear_gate_ends_at_skip_tier2(tmp_path: Path):
    """Full run with empty runners -> gate clears -> research -> prob (empty) ->
    analyst (empty intents) -> sizer (no slips) -> decision_maker skips Tier 2."""
    cp = await init_checkpointer(str(tmp_path / "cp.sqlite"))
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    registry = CalibratorRegistry(default=IdentityCalibrator())

    parse_node = AsyncMock(return_value={
        "parsed_race": {"track": "T", "country": "AU"},
        "enriched_runners": [{"number": 1, "win_odds": 2.0}],
        "overround_active": 0.05,  # clear
        "missing_fields": [],
    })
    research_node = AsyncMock(return_value={"research_results": {}})
    analyst_llm = AsyncMock(return_value={"intents": [], "adjustments": []})

    import sqlite3
    from services.stake.bankroll.migrations import apply_migrations
    from services.stake.calibration.samples import CalibrationSamplesRepository
    data_conn = sqlite3.connect(tmp_path / "data.sqlite")
    apply_migrations(data_conn)
    samples_repo = CalibrationSamplesRepository(data_conn)

    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 100.0
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0
    reflection_writer = MagicMock()
    reflection_writer.run = AsyncMock(return_value={"lessons_appended": 0})
    traces_repo = MagicMock()

    graph = compile_race_graph(
        settings=settings, checker=checker, checkpointer=cp,
        parse_node=parse_node, research_node=research_node,
        analyst_llm=analyst_llm, samples_repo=samples_repo,
        bankroll_repo=bankroll_repo, results_evaluator=None,
        calibrator_registry=registry,
        reflection_writer=reflection_writer,
        traces_repo=traces_repo,
        recorder_provider=lambda race_id: None,
    )
    config = {"configurable": {"thread_id": "race:R1:1"}}
    result = await graph.ainvoke({
        "race_id": "R1", "user_id": 1, "raw_input": "x", "source_type": "text",
    }, config=config)

    # No interrupt occurred (gate clear + zero intents -> decision_maker Tier 2)
    assert "__interrupt__" not in result
    assert result.get("skip_signal") is True
    assert result.get("skip_tier") == 2
    # Sample was written for the single runner during probability_model
    rows = data_conn.execute(
        "SELECT COUNT(*) FROM stake_calibration_samples WHERE race_id='R1'"
    ).fetchone()[0]
    assert rows == 1


@pytest.mark.asyncio
async def test_hard_skip_gate_pauses_at_interrupt(tmp_path: Path):
    cp = await init_checkpointer(str(tmp_path / "cp.sqlite"))
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    parse_node = AsyncMock(return_value={
        "parsed_race": {"track": "T"},
        "enriched_runners": [],
        "overround_active": 0.20,  # win.hard_skip = 0.15
        "missing_fields": [],
    })
    samples_repo = MagicMock()
    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 100.0
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0
    reflection_writer = MagicMock(run=AsyncMock(return_value={"lessons_appended": 0}))
    traces_repo = MagicMock()
    graph = compile_race_graph(
        settings=settings, checker=checker, checkpointer=cp,
        parse_node=parse_node,
        research_node=AsyncMock(return_value={}),
        analyst_llm=AsyncMock(return_value={"intents": [], "adjustments": []}),
        samples_repo=samples_repo, bankroll_repo=bankroll_repo, results_evaluator=None,
        calibrator_registry=registry,
        reflection_writer=reflection_writer,
        traces_repo=traces_repo,
        recorder_provider=lambda race_id: None,
    )
    config = {"configurable": {"thread_id": "race:R2:1"}}
    result = await graph.ainvoke({
        "race_id": "R2", "user_id": 1, "raw_input": "x", "source_type": "text",
    }, config=config)
    interrupts = result.get("__interrupt__") or []
    assert len(interrupts) == 1
    payload = interrupts[0].value
    assert payload["kind"] == "gate"
    assert payload["options"] == ["skip"]
