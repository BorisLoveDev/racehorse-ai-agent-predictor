import pytest
from unittest.mock import MagicMock

from services.stake.config.models import PhaseOneSettings
from services.stake.contracts import BetIntent
from services.stake.invariants.checker import InvariantChecker
from services.stake.invariants.rules import InvariantViolation
from services.stake.pipeline.nodes.sizer import (
    compute_proposed_slip, make_sizer_node,
)


def _intent(market="win", horse=3, conf=0.6):
    return BetIntent(market=market, selections=[horse], confidence=conf,
                     rationale_id="r1", edge_source="paper_only")


def _settings(**overrides):
    s = PhaseOneSettings(mode="paper")
    if "kelly_divisor" in overrides:
        s.sizing.default_kelly_divisor = overrides["kelly_divisor"]
    if "max_single_stake_pct" in overrides:
        s.sizing.max_single_stake_pct = overrides["max_single_stake_pct"]
    if "daily_limit_pct" in overrides:
        s.sizing.daily_limit_pct = overrides["daily_limit_pct"]
    if "min_edge_pp" in overrides:
        s.thresholds.min_edge_pp = overrides["min_edge_pp"]
    if "min_kelly_fraction" in overrides:
        s.thresholds.min_kelly_fraction = overrides["min_kelly_fraction"]
    return s


def test_zero_edge_yields_zero_stake_and_edge_tag():
    settings = _settings()
    checker = InvariantChecker(settings)
    # p_cal == p_market => edge=0pp < min_edge_pp=3 => edge_below_threshold cap.
    slip = compute_proposed_slip(
        intent=_intent(),
        p_calibrated=0.40, p_market=0.40, win_odds=2.50,
        bankroll=100.0, total_today=0.0,
        settings=settings, checker=checker,
    )
    assert slip.stake == 0.0
    assert "edge_below_threshold" in slip.caps_applied
    assert slip.mode == "paper"
    assert slip.max_loss == 0.0
    assert slip.profit_if_win == 0.0
    assert slip.portfolio_var_95 == 0.0


def test_positive_edge_risk_triplet_computed():
    settings = _settings()
    checker = InvariantChecker(settings)
    # p_cal=0.50, p_market=0.40, odds=2.50 => edge=10pp, full Kelly=(0.5*1.5-0.5)/1.5=0.1667
    # With kelly_divisor=4, fractional=0.0417, stake=4.17 on 100.
    slip = compute_proposed_slip(
        intent=_intent(),
        p_calibrated=0.50, p_market=0.40, win_odds=2.50,
        bankroll=100.0, total_today=0.0,
        settings=settings, checker=checker,
    )
    assert slip.stake > 0
    assert slip.max_loss == slip.stake
    assert slip.profit_if_win == pytest.approx(slip.stake * (2.50 - 1.0))
    # Phase 1 simple VaR95 == max_loss when P(lose) >= 5%.
    assert slip.portfolio_var_95 == slip.max_loss
    assert slip.sizing_params.kelly_fraction == 0.25  # 1/4


def test_per_bet_cap_trims_stake():
    # Force a large Kelly shoving stake above 2% cap.
    settings = _settings(max_single_stake_pct=0.02)
    checker = InvariantChecker(settings)
    slip = compute_proposed_slip(
        intent=_intent(conf=1.0),
        p_calibrated=0.90, p_market=0.30, win_odds=3.0,
        bankroll=100.0, total_today=0.0,
        settings=settings, checker=checker,
    )
    assert slip.stake == pytest.approx(2.0)
    assert "per_bet_cap" in slip.caps_applied


def test_daily_cap_trims_remaining_allowance():
    settings = _settings(daily_limit_pct=0.05)  # 5% = 5 on bankroll 100
    checker = InvariantChecker(settings)
    slip = compute_proposed_slip(
        intent=_intent(conf=1.0),
        p_calibrated=0.90, p_market=0.30, win_odds=3.0,
        bankroll=100.0, total_today=4.0,
        settings=settings, checker=checker,
    )
    # 5 - 4 = 1 remaining
    assert slip.stake == pytest.approx(1.0)
    assert "daily_limit" in slip.caps_applied


def test_daily_cap_fully_consumed_zero_stake():
    settings = _settings(daily_limit_pct=0.05)
    checker = InvariantChecker(settings)
    slip = compute_proposed_slip(
        intent=_intent(conf=1.0),
        p_calibrated=0.90, p_market=0.30, win_odds=3.0,
        bankroll=100.0, total_today=5.0,  # exactly at limit
        settings=settings, checker=checker,
    )
    assert slip.stake == 0.0
    assert "daily_limit" in slip.caps_applied


def test_min_kelly_fraction_zeroes_tiny_stake():
    # Edge big enough to pass min_edge_pp but Kelly too small.
    settings = _settings(min_edge_pp=0.1, min_kelly_fraction=0.5)
    checker = InvariantChecker(settings)
    slip = compute_proposed_slip(
        intent=_intent(),
        p_calibrated=0.41, p_market=0.40, win_odds=2.5,
        bankroll=100.0, total_today=0.0,
        settings=settings, checker=checker,
    )
    # Full Kelly here is tiny; fractional well below 0.5.
    assert slip.stake == 0.0
    assert "below_min_kelly_fraction" in slip.caps_applied


def test_live_mode_rejected_in_phase1():
    settings = _settings()
    checker = InvariantChecker(settings)
    with pytest.raises(InvariantViolation):
        compute_proposed_slip(
            intent=_intent(),
            p_calibrated=0.50, p_market=0.40, win_odds=2.50,
            bankroll=100.0, total_today=0.0,
            settings=settings, checker=checker, requested_mode="live",
        )


def test_multi_leg_markets_placeholder_in_phase1():
    settings = _settings()
    checker = InvariantChecker(settings)
    intent = BetIntent(
        market="trifecta_box", selections=[1, 2, 3],
        confidence=0.5, rationale_id="r", edge_source="paper_only",
    )
    # Sizer is win-single in Phase 1; other markets become zero-stake placeholders
    # with the 'phase1_market_unsupported' cap. This is handled by make_sizer_node
    # (node wrapper), not compute_proposed_slip — so this test exercises the node.
    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 100.0
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0
    node = make_sizer_node(settings=settings, checker=checker, bankroll_repo=bankroll_repo)
    import asyncio
    out = asyncio.get_event_loop().run_until_complete(node({
        "bet_intents": [intent.model_dump(mode="json")],
        "probabilities": [],
        "enriched_runners": [],
    }))
    assert len(out["proposed_bet_slips"]) == 1
    slip = out["proposed_bet_slips"][0]
    assert slip["stake"] == 0.0
    assert "phase1_market_unsupported" in slip["caps_applied"]


@pytest.mark.asyncio
async def test_sizer_node_integration_happy_path():
    settings = _settings()
    checker = InvariantChecker(settings)
    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 100.0
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0

    intent = BetIntent(market="win", selections=[3], confidence=0.6,
                       rationale_id="r", edge_source="paper_only")
    state = {
        "bet_intents": [intent.model_dump(mode="json")],
        "probabilities": [
            {"horse_no": 3, "p_market": 0.40, "p_raw": 0.50,
             "p_calibrated": 0.50, "applied_adjustment_pp": 0.0},
        ],
        "enriched_runners": [{"number": 3, "win_odds": 2.50}],
    }
    node = make_sizer_node(settings=settings, checker=checker, bankroll_repo=bankroll_repo)
    out = await node(state)
    slips = out["proposed_bet_slips"]
    assert len(slips) == 1
    assert slips[0]["mode"] == "paper"
    assert slips[0]["stake"] > 0
    assert slips[0]["max_loss"] == slips[0]["stake"]


@pytest.mark.asyncio
async def test_sizer_node_drawdown_blocks_when_triggered():
    # Simulate bankroll below peak by more than threshold.
    settings = _settings()
    settings.thresholds.drawdown_lock_pct = 0.20
    checker = InvariantChecker(settings)
    bankroll_repo = MagicMock()
    bankroll_repo.current_balance.return_value = 70.0   # 30% drawdown
    bankroll_repo.peak_balance.return_value = 100.0
    bankroll_repo.staked_today.return_value = 0.0
    node = make_sizer_node(settings=settings, checker=checker, bankroll_repo=bankroll_repo)
    with pytest.raises(InvariantViolation):
        await node({
            "bet_intents": [_intent().model_dump(mode="json")],
            "probabilities": [{"horse_no": 3, "p_market": 0.4, "p_raw": 0.5,
                               "p_calibrated": 0.5, "applied_adjustment_pp": 0.0}],
            "enriched_runners": [{"number": 3, "win_odds": 2.5}],
        })
