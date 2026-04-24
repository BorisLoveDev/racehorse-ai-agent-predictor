import pytest
import yaml
from pathlib import Path

from services.stake.config.loader import ConfigLoadError, load_config
from services.stake.invariants.rules import InvariantViolation


def test_paper_mode_loads(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({
        "mode": "paper",
        "live_unlock": False,
        "thresholds": {
            "overround": {
                "win": {"hard_skip": 0.15, "interrupt": 0.12},
                "place": {"hard_skip": 0.18, "interrupt": 0.15},
                "quinella_exacta": {"hard_skip": 0.20, "interrupt": 0.17},
                "trifecta_first4": {"hard_skip": 0.35, "interrupt": 0.30},
            },
            "min_edge_pp": 3.0,
            "min_kelly_fraction": 0.005,
            "drawdown_lock_pct": 0.20,
        },
        "sizing": {"default_kelly_divisor": 4, "max_single_stake_pct": 0.05, "daily_limit_pct": 0.15},
        "calibration": {"layer": "identity", "promotion": {"global_min_samples": 100, "by_market_min": 300, "by_track_min": 500}},
        "reflection": {"top_n_lessons_in_prompt": 10},
    }))
    settings = load_config(cfg)
    assert settings.mode == "paper"
    assert settings.live_unlock is False
    assert settings.thresholds.overround.win.hard_skip == 0.15
    assert settings.thresholds.overround.trifecta_first4.hard_skip == 0.35
    assert settings.calibration.layer == "identity"


def test_live_mode_rejected_in_phase1(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"mode": "live", "live_unlock": True}))
    with pytest.raises(InvariantViolation) as exc:
        load_config(cfg)
    assert "I1" in str(exc.value)


def test_missing_config_falls_back_to_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("STAKE_MODE", "paper")
    settings = load_config(tmp_path / "does-not-exist.yaml")
    assert settings.mode == "paper"


def test_malformed_yaml_raises_config_load_error(tmp_path: Path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("mode: paper\n  bad: : : indent")  # invalid YAML
    with pytest.raises(ConfigLoadError):
        load_config(cfg)


def test_invalid_mode_value_raises_config_load_error(tmp_path: Path):
    cfg = tmp_path / "bad_mode.yaml"
    cfg.write_text("mode: bogus\n")
    with pytest.raises(ConfigLoadError):
        load_config(cfg)


def test_dry_run_mode_is_allowed(tmp_path: Path):
    cfg = tmp_path / "dr.yaml"
    cfg.write_text("mode: dry_run\n")
    settings = load_config(cfg)
    assert settings.mode == "dry_run"


def test_unknown_top_level_key_rejected(tmp_path: Path):
    cfg = tmp_path / "typo.yaml"
    cfg.write_text("mode: paper\nthrsholds: {}\n")  # typo: thrsholds
    with pytest.raises(ConfigLoadError):
        load_config(cfg)
