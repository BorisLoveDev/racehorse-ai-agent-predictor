"""Shared fixtures for Phase 1 E2E pipeline scenarios.

Each test compiles a fresh `compile_race_graph(...)` wired to:
  - a per-test SQLite data DB (bankroll, bet_slips, calibration_samples,
    audit_traces) via `tmp_path / "data.sqlite"`,
  - a per-test AsyncSqliteSaver checkpointer via `tmp_path / "cp.sqlite"`,
  - AsyncMock parse/research/analyst nodes (no network, deterministic),
  - a real `BankrollRepository` seeded with 100 USDT,
  - a MagicMock reflection_writer so we can assert it was called.

`_reset_checkpointer` is autouse: it clears the module-level checkpointer
singleton between tests so each test opens its own AsyncSqliteSaver.
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.stake.audit.traces_repo import AuditTracesRepository
from services.stake.bankroll.migrations import apply_migrations
from services.stake.bankroll.repository import BankrollRepository
from services.stake.calibration.samples import CalibrationSamplesRepository
from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.checker import InvariantChecker
from services.stake.pipeline.checkpointer import (
    init_checkpointer, shutdown_checkpointer,
)
from services.stake.pipeline.graph import compile_race_graph
from services.stake.probability.calibration import (
    CalibratorRegistry, IdentityCalibrator,
)


@pytest.fixture(autouse=True)
async def _reset_checkpointer():
    """Ensure each test opens its own checkpointer singleton."""
    import services.stake.pipeline.checkpointer as cp
    cp._checkpointer = None
    cp._checkpointer_cm = None
    yield
    if cp._checkpointer is not None:
        await shutdown_checkpointer()


@pytest.fixture
def scenario_factory(tmp_path: Path):
    """Return an async factory that builds a fresh graph + repos per call.

    Args passed to the factory shape the mocked parse_node output and which
    calibrator the ProbabilityModel runs through. Everything else is real:
    the bankroll repository, the samples repository, the traces repository,
    the checkpointer, and the graph topology.
    """

    async def _factory(
        *,
        overround: float = 0.05,
        runners: list[dict] | None = None,
        calibrator=None,
        parse_state_override: dict | None = None,
        bankroll: float = 100.0,
        analyst_output: dict | None = None,
    ):
        data_db = tmp_path / "data.sqlite"
        # Open a long-lived connection for the repositories whose API expects
        # a handle (samples, traces). BankrollRepository manages its own
        # connections per-call but reads/writes to the same DB file.
        conn = sqlite3.connect(str(data_db))
        apply_migrations(conn)
        samples_repo = CalibrationSamplesRepository(conn)
        traces_repo = AuditTracesRepository(conn)

        settings = PhaseOneSettings(mode="paper")
        checker = InvariantChecker(settings)
        cp = await init_checkpointer(str(tmp_path / "cp.sqlite"))

        runners = runners if runners is not None else [
            {"number": 1, "win_odds": 4.0},
            {"number": 2, "win_odds": 3.0},
            {"number": 3, "win_odds": 2.0},
        ]
        parse_state = {
            "parsed_race": {"track": "Sandown", "country": "AUS"},
            "enriched_runners": runners,
            "overround_active": overround,
            "missing_fields": [],
        }
        if parse_state_override:
            parse_state.update(parse_state_override)

        parse_node = AsyncMock(return_value=parse_state)
        research_node = AsyncMock(return_value={"research_results": {}})
        default_analyst = {
            "intents": [{
                "market": "win",
                "selections": [3],
                "confidence": 0.6,
                "rationale_id": "r",
                "edge_source": "p_model",
            }],
            "adjustments": [],
        }
        analyst_llm = AsyncMock(return_value=analyst_output or default_analyst)

        bankroll_repo = BankrollRepository(str(data_db))
        # Fresh DB -> set_balance() also initialises peak_balance_usdt.
        bankroll_repo.set_balance(bankroll)

        registry = CalibratorRegistry(
            default=calibrator or IdentityCalibrator(),
        )
        reflection_writer = MagicMock()
        reflection_writer.run = AsyncMock(return_value={"lessons_appended": 0})

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
        return {
            "graph": graph,
            "conn": conn,
            "bankroll_repo": bankroll_repo,
            "samples_repo": samples_repo,
            "reflection_writer": reflection_writer,
            "analyst_llm": analyst_llm,
            "parse_node": parse_node,
            "settings": settings,
        }

    return _factory
