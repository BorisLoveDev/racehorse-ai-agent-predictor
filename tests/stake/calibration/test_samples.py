import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.stake.bankroll.migrations import apply_migrations
from services.stake.calibration.samples import CalibrationSamplesRepository


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    apply_migrations(conn)
    return conn


def test_insert_returns_id_and_persists(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = CalibrationSamplesRepository(conn)
    sid = repo.insert(
        race_id="R1", horse_no=3, market="win",
        track="Sandown", jurisdiction="AUS",
        p_model_raw=0.25, p_model_calibrated=0.25, p_market=0.25,
        placed_bet=False, ts=datetime.now(timezone.utc),
    )
    assert sid > 0
    row = conn.execute(
        "SELECT outcome, placed_bet, p_model_raw FROM stake_calibration_samples WHERE id=?",
        (sid,),
    ).fetchone()
    assert row[0] is None            # outcome NULL until settlement
    assert row[1] == 0               # placed_bet False
    assert abs(row[2] - 0.25) < 1e-9


def test_insert_placed_bet_true(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = CalibrationSamplesRepository(conn)
    sid = repo.insert(
        race_id="R1", horse_no=3, market="win",
        track="T", jurisdiction="J",
        p_model_raw=0.3, p_model_calibrated=0.3, p_market=0.3,
        placed_bet=True, ts=datetime.now(timezone.utc),
    )
    row = conn.execute(
        "SELECT placed_bet FROM stake_calibration_samples WHERE id=?", (sid,),
    ).fetchone()
    assert row[0] == 1


def test_set_outcome_updates_row(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = CalibrationSamplesRepository(conn)
    repo.insert(race_id="R1", horse_no=3, market="win",
                track="T", jurisdiction="J",
                p_model_raw=0.25, p_model_calibrated=0.25, p_market=0.25,
                placed_bet=False, ts=datetime.now(timezone.utc))
    repo.set_outcome(race_id="R1", horse_no=3, market="win", outcome=1)
    row = conn.execute(
        "SELECT outcome FROM stake_calibration_samples "
        "WHERE race_id=? AND horse_no=? AND market=?",
        ("R1", 3, "win"),
    ).fetchone()
    assert row[0] == 1


def test_set_outcome_scoped_by_race_horse_market(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = CalibrationSamplesRepository(conn)
    for h in (1, 2, 3):
        repo.insert(race_id="R1", horse_no=h, market="win",
                    track=None, jurisdiction=None,
                    p_model_raw=0.33, p_model_calibrated=0.33, p_market=0.33,
                    placed_bet=False, ts=datetime.now(timezone.utc))
    repo.set_outcome(race_id="R1", horse_no=2, market="win", outcome=1)
    rows = conn.execute(
        "SELECT horse_no, outcome FROM stake_calibration_samples "
        "WHERE race_id='R1' ORDER BY horse_no"
    ).fetchall()
    assert rows == [(1, None), (2, 1), (3, None)]


def test_pending_settlement_returns_distinct_races(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = CalibrationSamplesRepository(conn)
    for h in (1, 2):
        repo.insert(race_id="R1", horse_no=h, market="win",
                    track=None, jurisdiction=None,
                    p_model_raw=0.5, p_model_calibrated=0.5, p_market=0.5,
                    placed_bet=False, ts=datetime.now(timezone.utc))
    repo.insert(race_id="R2", horse_no=1, market="win",
                track=None, jurisdiction=None,
                p_model_raw=1.0, p_model_calibrated=1.0, p_market=1.0,
                placed_bet=False, ts=datetime.now(timezone.utc))
    pending = set(repo.races_pending_settlement())
    assert pending == {"R1", "R2"}
    # Settle R1 (both horses)
    repo.set_outcome(race_id="R1", horse_no=1, market="win", outcome=0)
    repo.set_outcome(race_id="R1", horse_no=2, market="win", outcome=1)
    pending = set(repo.races_pending_settlement())
    assert pending == {"R2"}
