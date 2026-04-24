"""Phase 1 migrations: calibration_samples, bet_slips, lessons pnl_track, audit_traces."""
import sqlite3
from pathlib import Path

import pytest

from services.stake.bankroll.migrations import apply_migrations


def _apply(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    apply_migrations(conn)
    return conn


def test_phase1_tables_created(tmp_path: Path):
    conn = _apply(tmp_path)
    cur = conn.cursor()

    # Existing tables still created
    for t in ("stake_bankroll", "stake_pipeline_runs",
              "stake_bet_outcomes", "stake_lessons"):
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
        assert cur.fetchone() is not None, f"{t} missing"

    # New Phase 1 tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stake_calibration_samples'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stake_audit_traces'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stake_bet_slips'")
    assert cur.fetchone() is not None


def test_stake_bet_slips_columns(tmp_path: Path):
    conn = _apply(tmp_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stake_bet_slips)").fetchall()}
    expected = {
        "id", "race_id", "user_id", "market", "selections", "stake",
        "confidence", "idempotency_key", "status", "mode",
        "max_loss", "profit_if_win", "portfolio_var_95",
        "caps_applied", "sizing_params", "user_edits",
        "confirmed_at", "created_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_stake_lessons_extended(tmp_path: Path):
    conn = _apply(tmp_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stake_lessons)").fetchall()}
    expected = {"pnl_track", "evidence_bet_ids", "status", "confidence",
                "tag", "lesson_id", "condition", "action"}
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_calibration_samples_columns(tmp_path: Path):
    conn = _apply(tmp_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stake_calibration_samples)").fetchall()}
    expected = {"id", "race_id", "horse_no", "market", "track", "jurisdiction",
                "p_model_raw", "p_model_calibrated", "p_market",
                "outcome", "placed_bet", "ts"}
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_audit_traces_columns(tmp_path: Path):
    conn = _apply(tmp_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stake_audit_traces)").fetchall()}
    expected = {"race_id", "schema_version", "thread_id",
                "started_at", "finished_at", "reproducible",
                "steps_json", "total_cost_usd"}
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_migrations_idempotent(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.db")
    apply_migrations(conn)
    apply_migrations(conn)  # must not raise


def test_bet_slips_idempotency_key_unique(tmp_path: Path):
    conn = _apply(tmp_path)
    conn.execute(
        "INSERT INTO stake_bet_slips (id, race_id, user_id, market, selections, stake, idempotency_key) "
        "VALUES ('b1','R1',1,'win','[3]',2.0,'key1')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO stake_bet_slips (id, race_id, user_id, market, selections, stake, idempotency_key) "
            "VALUES ('b2','R1',1,'win','[3]',2.0,'key1')"
        )


def test_run_stake_migrations_still_works(tmp_path: Path):
    # Backwards compatibility for existing callers.
    from services.stake.bankroll.migrations import run_stake_migrations
    db = tmp_path / "legacy.db"
    run_stake_migrations(str(db))
    # Calling twice must not raise (idempotent)
    run_stake_migrations(str(db))
    # And the new tables are there too
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='stake_calibration_samples'"
    ).fetchone()[0]
    assert n == 1
