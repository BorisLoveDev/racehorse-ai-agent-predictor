import pytest
from unittest.mock import MagicMock

from services.stake.pipeline.nodes.settlement import make_settlement_node


def _samples_and_bankroll_fakes():
    samples_repo = MagicMock()
    bankroll_repo = MagicMock()
    return samples_repo, bankroll_repo


def _probabilities(horse_nos):
    return [
        {"horse_no": h, "p_market": 0.33, "p_raw": 0.33,
         "p_calibrated": 0.33, "applied_adjustment_pp": 0.0}
        for h in horse_nos
    ]


@pytest.mark.asyncio
async def test_marks_winner_outcome_one_and_losers_zero():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = None  # no confirmed slips in this test
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    state = {
        "race_id": "R1",
        "bet_slip_ids": [],
        "result_outcome": {3: 1, 1: 2, 2: 3},
        "probabilities": _probabilities([1, 2, 3]),
    }
    await node(state)
    calls = {c.kwargs["horse_no"]: c.kwargs["outcome"]
             for c in samples_repo.set_outcome.call_args_list}
    assert calls == {1: 0, 2: 0, 3: 1}
    # All used race_id=R1 and market=win
    for c in samples_repo.set_outcome.call_args_list:
        assert c.kwargs["race_id"] == "R1"
        assert c.kwargs["market"] == "win"


@pytest.mark.asyncio
async def test_skips_horses_not_in_outcome():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = None
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    await node({
        "race_id": "R1",
        "bet_slip_ids": [],
        "result_outcome": {3: 1},  # only horse 3 reported
        "probabilities": _probabilities([1, 2, 3]),
    })
    calls = samples_repo.set_outcome.call_args_list
    assert len(calls) == 1  # only horse 3 updated
    assert calls[0].kwargs["horse_no"] == 3


@pytest.mark.asyncio
async def test_paper_pnl_win_adds_profit():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = {
        "id": "b1", "race_id": "R1", "status": "confirmed",
        "market": "win", "selections": [3], "stake": 5.0, "mode": "paper",
        "proposed": {"intent": {"market": "win", "selections": [3]},
                     "profit_if_win": 10.0},
    }
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    out = await node({
        "race_id": "R1",
        "bet_slip_ids": ["b1"],
        "result_outcome": {3: 1},
        "probabilities": _probabilities([3]),
    })
    bankroll_repo.apply_paper_pnl.assert_called_once_with(race_id="R1", pnl=10.0)
    assert out["settlement_pnl"] == 10.0


@pytest.mark.asyncio
async def test_paper_pnl_loss_subtracts_stake():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = {
        "id": "b1", "race_id": "R1", "status": "confirmed",
        "market": "win", "selections": [3], "stake": 5.0, "mode": "paper",
        "proposed": {"intent": {"market": "win", "selections": [3]},
                     "profit_if_win": 10.0},
    }
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    out = await node({
        "race_id": "R1",
        "bet_slip_ids": ["b1"],
        "result_outcome": {3: 2},  # horse 3 finished 2nd => loss
        "probabilities": _probabilities([3]),
    })
    bankroll_repo.apply_paper_pnl.assert_called_once_with(race_id="R1", pnl=-5.0)
    assert out["settlement_pnl"] == -5.0


@pytest.mark.asyncio
async def test_skips_cancelled_slips():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = {
        "id": "b1", "race_id": "R1", "status": "cancelled",
        "market": "win", "selections": [3], "stake": 5.0, "mode": "paper",
        "proposed": {"intent": {"market": "win", "selections": [3]},
                     "profit_if_win": 10.0},
    }
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    out = await node({
        "race_id": "R1",
        "bet_slip_ids": ["b1"],
        "result_outcome": {3: 1},
        "probabilities": _probabilities([3]),
    })
    bankroll_repo.apply_paper_pnl.assert_not_called()
    assert out["settlement_pnl"] == 0.0


@pytest.mark.asyncio
async def test_skips_missing_slips():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = None  # slip disappeared
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=True)
    out = await node({
        "race_id": "R1",
        "bet_slip_ids": ["b1"],
        "result_outcome": {3: 1},
        "probabilities": _probabilities([3]),
    })
    bankroll_repo.apply_paper_pnl.assert_not_called()
    assert out["settlement_pnl"] == 0.0


@pytest.mark.asyncio
async def test_non_paper_mode_does_not_apply_pnl():
    samples_repo, bankroll_repo = _samples_and_bankroll_fakes()
    bankroll_repo.get_bet_slip.return_value = {
        "id": "b1", "race_id": "R1", "status": "confirmed",
        "market": "win", "selections": [3], "stake": 5.0, "mode": "dry_run",
        "proposed": {"intent": {"market": "win", "selections": [3]},
                     "profit_if_win": 10.0},
    }
    node = make_settlement_node(samples_repo=samples_repo,
                                bankroll_repo=bankroll_repo, paper_mode=False)
    await node({
        "race_id": "R1",
        "bet_slip_ids": ["b1"],
        "result_outcome": {3: 1},
        "probabilities": _probabilities([3]),
    })
    bankroll_repo.apply_paper_pnl.assert_not_called()
