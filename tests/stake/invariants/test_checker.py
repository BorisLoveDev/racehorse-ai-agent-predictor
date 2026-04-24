import pytest
from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.checker import InvariantChecker
from services.stake.invariants.rules import InvariantViolation


def test_startup_passes_in_paper():
    settings = PhaseOneSettings(mode="paper", live_unlock=False)
    checker = InvariantChecker(settings)
    checker.run_startup()  # no exception


def test_startup_blocks_live_without_unlock():
    # Bypass loader validation via model_construct so we can reach the
    # InvariantChecker's own startup check (defense in depth — if a caller
    # somehow instantiates PhaseOneSettings with mode='live' without going
    # through load_config, run_startup() must still catch it).
    settings = PhaseOneSettings.model_construct(mode="live", live_unlock=False)
    checker = InvariantChecker(settings)
    with pytest.raises(InvariantViolation) as exc:
        checker.run_startup()
    assert exc.value.rule_id == "I1"


def test_check_mode_blocks_live_stake_in_phase1():
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    with pytest.raises(InvariantViolation) as exc:
        checker.check_bet_slip_can_be_live(requested_mode="live")
    assert exc.value.rule_id == "I1"


def test_check_caps_i6():
    settings = PhaseOneSettings(mode="paper")
    settings.sizing.max_single_stake_pct = 0.05
    settings.sizing.daily_limit_pct = 0.15
    checker = InvariantChecker(settings)
    # stake 10 on bankroll 100 = 10% > 5% cap => violation
    with pytest.raises(InvariantViolation) as exc:
        checker.check_sizing_caps(stake=10.0, bankroll=100.0, total_today=0.0)
    assert exc.value.rule_id == "I6"


def test_check_caps_within_limits_passes():
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    checker.check_sizing_caps(stake=2.0, bankroll=100.0, total_today=5.0)  # no raise


def test_check_caps_daily_limit_violation():
    settings = PhaseOneSettings(mode="paper")
    settings.sizing.max_single_stake_pct = 0.05
    settings.sizing.daily_limit_pct = 0.10
    checker = InvariantChecker(settings)
    # Stake alone OK (4% < 5%); total today (9%) + new (4%) = 13% > 10%
    with pytest.raises(InvariantViolation) as exc:
        checker.check_sizing_caps(stake=4.0, bankroll=100.0, total_today=9.0)
    assert exc.value.rule_id == "I6"


def test_check_caps_non_positive_bankroll():
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    with pytest.raises(InvariantViolation) as exc:
        checker.check_sizing_caps(stake=1.0, bankroll=0.0, total_today=0.0)
    assert exc.value.rule_id == "I6"


def test_check_drawdown_trips_at_threshold():
    settings = PhaseOneSettings(mode="paper")
    settings.thresholds.drawdown_lock_pct = 0.20
    checker = InvariantChecker(settings)
    # 20% drawdown => trip
    with pytest.raises(InvariantViolation) as exc:
        checker.check_drawdown(current=80.0, peak=100.0)
    assert exc.value.rule_id == "I6"


def test_check_drawdown_below_threshold_passes():
    settings = PhaseOneSettings(mode="paper")
    settings.thresholds.drawdown_lock_pct = 0.20
    checker = InvariantChecker(settings)
    checker.check_drawdown(current=85.0, peak=100.0)  # 15% — OK


def test_check_drawdown_no_peak_no_op():
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    # peak==0 means no history yet — should not raise
    checker.check_drawdown(current=50.0, peak=0.0)


def test_reproducibility_noop_in_paper():
    settings = PhaseOneSettings(mode="paper")
    checker = InvariantChecker(settings)
    # Non-live mode => reproducibility is not enforced
    checker.check_reproducibility_for_live(last_10_reproducible=[False, True])
