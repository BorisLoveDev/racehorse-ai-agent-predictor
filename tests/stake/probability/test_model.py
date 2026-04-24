import pytest

from services.stake.contracts.llm import LLMAdjustment
from services.stake.probability.calibration import (
    IdentityCalibrator, CalibratorRegistry,
)
from services.stake.probability.model import ProbabilityModel


def test_implied_normalized_subtracts_overround():
    runners = [
        {"number": 1, "win_odds": 2.0},
        {"number": 2, "win_odds": 4.0},
        {"number": 3, "win_odds": 5.0},
    ]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track="Sandown", market="win")
    probs = pm.compute(runners, adjustments=[])
    s = sum(p.p_market for p in probs)
    assert abs(s - 1.0) < 1e-9
    for p in probs:
        assert p.p_raw == p.p_market
        assert p.p_calibrated == p.p_raw
        assert p.applied_adjustment_pp == 0.0


def test_adjustment_shifts_probability_bounded():
    runners = [{"number": 1, "win_odds": 2.0}, {"number": 2, "win_odds": 2.0}]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track="T", market="win")
    adj = [LLMAdjustment(target_horse_no=1, direction="up", magnitude="medium",
                         rationale="x")]
    probs = pm.compute(runners, adjustments=adj)
    p1 = next(p for p in probs if p.horse_no == 1)
    p2 = next(p for p in probs if p.horse_no == 2)
    assert p1.applied_adjustment_pp == 2.0
    assert p1.p_calibrated > p1.p_market
    assert abs((p1.p_calibrated + p2.p_calibrated) - 1.0) < 1e-9


def test_adjustment_total_shift_capped():
    runners = [{"number": 1, "win_odds": 2.0}, {"number": 2, "win_odds": 2.0}]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track="T", market="win")
    # Two "large" adjustments would be +6pp; MAX_TOTAL_SHIFT_PP=3.0 caps it
    adj = [
        LLMAdjustment(target_horse_no=1, direction="up", magnitude="large", rationale=""),
        LLMAdjustment(target_horse_no=1, direction="up", magnitude="large", rationale=""),
    ]
    probs = pm.compute(runners, adjustments=adj)
    p1 = next(p for p in probs if p.horse_no == 1)
    assert p1.applied_adjustment_pp == 3.0


def test_adjustment_down_direction_negative_shift():
    runners = [{"number": 1, "win_odds": 2.0}, {"number": 2, "win_odds": 2.0}]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track="T", market="win")
    adj = [LLMAdjustment(target_horse_no=1, direction="down", magnitude="small", rationale="")]
    probs = pm.compute(runners, adjustments=adj)
    p1 = next(p for p in probs if p.horse_no == 1)
    assert p1.applied_adjustment_pp == -1.0
    assert p1.p_calibrated < p1.p_market


def test_adjustment_neutral_no_shift():
    runners = [{"number": 1, "win_odds": 2.0}, {"number": 2, "win_odds": 2.0}]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track="T", market="win")
    adj = [LLMAdjustment(target_horse_no=1, direction="neutral", magnitude="large", rationale="")]
    probs = pm.compute(runners, adjustments=adj)
    p1 = next(p for p in probs if p.horse_no == 1)
    assert p1.applied_adjustment_pp == 0.0


def test_runners_without_win_odds_excluded():
    runners = [
        {"number": 1, "win_odds": 2.0},
        {"number": 2, "win_odds": None},
        {"number": 3},
        {"number": 4, "win_odds": 4.0},
    ]
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track=None, market="win")
    probs = pm.compute(runners, adjustments=[])
    horse_nos = {p.horse_no for p in probs}
    assert horse_nos == {1, 4}


def test_empty_runners_returns_empty():
    registry = CalibratorRegistry(default=IdentityCalibrator())
    pm = ProbabilityModel(registry=registry, track=None, market="win")
    assert pm.compute([], adjustments=[]) == []


def test_registry_precedence_track_over_market_over_global():
    class Tag:
        def __init__(self, name): self.name = name
        def transform(self, p): return p
    reg = CalibratorRegistry(default=Tag("global"))
    reg.set_for_market("win", Tag("market_win"))
    reg.set_for_track("Sandown", Tag("track_sandown"))
    assert reg.resolve(market="win", track="Sandown").name == "track_sandown"
    assert reg.resolve(market="win", track="Other").name == "market_win"
    assert reg.resolve(market="place", track="Other").name == "global"
    assert reg.resolve(market="win", track=None).name == "market_win"


def test_identity_calibrator_noop():
    cal = IdentityCalibrator()
    for p in (0.0, 0.5, 1.0, 0.123456):
        assert cal.transform(p) == p
