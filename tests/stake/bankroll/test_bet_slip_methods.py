import json
from pathlib import Path

import pytest

from services.stake.bankroll.repository import BankrollRepository


def _repo(tmp_path: Path) -> BankrollRepository:
    db = tmp_path / "br.sqlite"
    return BankrollRepository(str(db))


def _sample_slip(bet_id: str, stake: float = 2.0, status: str = "draft") -> dict:
    return {
        "id": bet_id,
        "race_id": "R1",
        "user_id": 42,
        "idempotency_key": f"key-{bet_id}",
        "status": status,
        "proposed": {
            "intent": {
                "market": "win",
                "selections": [3],
                "confidence": 0.6,
                "rationale_id": "r1",
                "edge_source": "paper_only",
            },
            "stake": stake,
            "kelly_fraction_used": 0.25,
            "expected_return": 3.0,
            "expected_value": 0.2,
            "max_loss": stake,
            "profit_if_win": stake * 1.5,
            "portfolio_var_95": stake,
            "caps_applied": [],
            "sizing_params": {"kelly_fraction": 0.25, "risk_mode": "normal"},
            "mode": "paper",
        },
        "confirmed_at": None,
        "user_edits": None,
    }


def test_current_balance_defaults_to_zero(tmp_path: Path):
    repo = _repo(tmp_path)
    assert repo.current_balance() == 0.0


def test_current_balance_after_set(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.set_balance(150.0)
    assert repo.current_balance() == 150.0


def test_peak_balance_defaults_to_zero(tmp_path: Path):
    repo = _repo(tmp_path)
    assert repo.peak_balance() == 0.0


def test_peak_balance_after_set(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.set_balance(200.0)
    assert repo.peak_balance() == 200.0


def test_save_and_get_bet_slip(tmp_path: Path):
    repo = _repo(tmp_path)
    slip = _sample_slip("bs1", stake=2.0)
    repo.save_bet_slip(slip)
    got = repo.get_bet_slip("bs1")
    assert got is not None
    assert got["id"] == "bs1"
    assert got["race_id"] == "R1"
    assert got["status"] == "draft"
    assert got["mode"] == "paper"
    assert got["proposed"]["intent"]["market"] == "win"
    assert got["proposed"]["intent"]["selections"] == [3]
    assert got["proposed"]["profit_if_win"] == 3.0
    assert got["stake"] == 2.0


def test_get_bet_slip_missing_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert repo.get_bet_slip("no-such-id") is None


def test_update_bet_slip_status_sets_confirmed_at(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.save_bet_slip(_sample_slip("bs1"))
    repo.update_bet_slip_status("bs1", "confirmed", user_edits={"note": "ok"})
    row = repo.get_bet_slip("bs1")
    assert row["status"] == "confirmed"


def test_update_bet_slip_status_cancelled_stores_user_edits_json(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.save_bet_slip(_sample_slip("bs1"))
    repo.update_bet_slip_status("bs1", "cancelled", user_edits={"kill": True})
    import sqlite3
    conn = sqlite3.connect(repo.db_path)
    row = conn.execute(
        "SELECT status, user_edits FROM stake_bet_slips WHERE id='bs1'"
    ).fetchone()
    assert row[0] == "cancelled"
    assert json.loads(row[1]) == {"kill": True}


def test_save_bet_slip_duplicate_idempotency_key_raises(tmp_path: Path):
    import sqlite3
    repo = _repo(tmp_path)
    slip = _sample_slip("bs1")
    repo.save_bet_slip(slip)
    # Save another slip with same idempotency_key => UNIQUE violation
    slip2 = _sample_slip("bs2")
    slip2["idempotency_key"] = slip["idempotency_key"]
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_bet_slip(slip2)


def test_staked_today_sums_confirmed_slips_only(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.save_bet_slip(_sample_slip("bs1", stake=5.0, status="confirmed"))
    repo.save_bet_slip(_sample_slip("bs2", stake=3.0, status="confirmed"))
    repo.save_bet_slip(_sample_slip("bs3", stake=100.0, status="draft"))
    repo.save_bet_slip(_sample_slip("bs4", stake=10.0, status="cancelled"))
    assert repo.staked_today() == pytest.approx(8.0)


def test_apply_paper_pnl_adjusts_balance(tmp_path: Path):
    repo = _repo(tmp_path)
    repo.set_balance(100.0)
    repo.apply_paper_pnl(race_id="R1", pnl=5.0)
    assert repo.current_balance() == 105.0
    repo.apply_paper_pnl(race_id="R2", pnl=-3.0)
    assert repo.current_balance() == 102.0
