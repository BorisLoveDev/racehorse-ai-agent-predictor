import pytest
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from services.stake.bankroll.migrations import apply_migrations
from services.stake.calibration.samples import CalibrationSamplesRepository
from services.stake.probability.calibration import IdentityCalibrator, CalibratorRegistry
from services.stake.pipeline.nodes.probability_model import make_probability_model_node


def _make_samples_repo(tmp_path: Path) -> tuple[sqlite3.Connection, CalibrationSamplesRepository]:
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    apply_migrations(conn)
    return conn, CalibrationSamplesRepository(conn)


def _base_state(extras: dict | None = None) -> dict:
    state = {
        "race_id": "R1",
        "enriched_runners": [
            {"number": 1, "win_odds": 2.0},
            {"number": 2, "win_odds": 3.0},
            {"number": 3, "win_odds": 6.0},
        ],
        "parsed_race": {"track": "Sandown", "country": "AUS"},
        "llm_adjustments": [],
    }
    if extras:
        state.update(extras)
    return state


@pytest.mark.asyncio
async def test_populates_probabilities_identity_case(tmp_path: Path):
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)

    out = await node(_base_state())
    probs = out["probabilities"]
    assert len(probs) == 3
    for p in probs:
        assert p["p_raw"] == p["p_market"]
        assert p["p_calibrated"] == p["p_raw"]
        assert p["applied_adjustment_pp"] == 0.0
    s = sum(p["p_market"] for p in probs)
    assert abs(s - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_samples_written_one_per_runner(tmp_path: Path):
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)
    await node(_base_state())

    count = conn.execute(
        "SELECT COUNT(*) FROM stake_calibration_samples WHERE race_id='R1'"
    ).fetchone()[0]
    assert count == 3

    # Outcome NULL, placed_bet=0
    rows = conn.execute(
        "SELECT outcome, placed_bet, track, jurisdiction FROM stake_calibration_samples "
        "WHERE race_id='R1' ORDER BY horse_no"
    ).fetchall()
    assert all(r[0] is None for r in rows)
    assert all(r[1] == 0 for r in rows)
    assert all(r[2] == "Sandown" for r in rows)
    assert all(r[3] == "AUS" for r in rows)


@pytest.mark.asyncio
async def test_llm_adjustment_applied(tmp_path: Path):
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)
    state = _base_state({
        "llm_adjustments": [
            {"target_horse_no": 1, "direction": "up",
             "magnitude": "medium", "rationale": "form trend"},
        ],
    })
    out = await node(state)
    p1 = next(p for p in out["probabilities"] if p["horse_no"] == 1)
    assert p1["applied_adjustment_pp"] == 2.0
    assert p1["p_calibrated"] > p1["p_market"]


@pytest.mark.asyncio
async def test_missing_parsed_race_ok(tmp_path: Path):
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)
    state = {
        "race_id": "R1",
        "enriched_runners": [{"number": 1, "win_odds": 2.0}],
        "llm_adjustments": [],
    }
    out = await node(state)
    assert len(out["probabilities"]) == 1
    row = conn.execute(
        "SELECT track, jurisdiction FROM stake_calibration_samples WHERE race_id='R1'"
    ).fetchone()
    assert row == (None, None)


@pytest.mark.asyncio
async def test_empty_runners_no_samples(tmp_path: Path):
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)
    state = {
        "race_id": "R1",
        "enriched_runners": [],
        "parsed_race": {},
        "llm_adjustments": [],
    }
    out = await node(state)
    assert out["probabilities"] == []
    count = conn.execute(
        "SELECT COUNT(*) FROM stake_calibration_samples"
    ).fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_adjustments_validated_before_use(tmp_path: Path):
    """If LLM somehow slipped a probability field, LLMAdjustment Pydantic
    validator will raise — the node must propagate that (don't swallow)."""
    import pytest as _pt
    conn, repo = _make_samples_repo(tmp_path)
    registry = CalibratorRegistry(default=IdentityCalibrator())
    node = make_probability_model_node(registry=registry, samples_repo=repo)
    state = _base_state({
        "llm_adjustments": [
            {"target_horse_no": 1, "direction": "up", "magnitude": "small",
             "rationale": "x", "probability": 0.42},
        ],
    })
    from pydantic import ValidationError
    with _pt.raises(ValidationError):
        await node(state)
