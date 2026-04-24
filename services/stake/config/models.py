from typing import Literal
from pydantic import BaseModel, Field


class OverroundThreshold(BaseModel):
    hard_skip: float
    interrupt: float


class OverroundByMarket(BaseModel):
    win: OverroundThreshold = OverroundThreshold(hard_skip=0.15, interrupt=0.12)
    place: OverroundThreshold = OverroundThreshold(hard_skip=0.18, interrupt=0.15)
    quinella_exacta: OverroundThreshold = OverroundThreshold(hard_skip=0.20, interrupt=0.17)
    trifecta_first4: OverroundThreshold = OverroundThreshold(hard_skip=0.35, interrupt=0.30)


class ThresholdSettings(BaseModel):
    overround: OverroundByMarket = Field(default_factory=OverroundByMarket)
    min_edge_pp: float = 3.0
    min_kelly_fraction: float = 0.005
    drawdown_lock_pct: float = 0.20


class SizingBlockSettings(BaseModel):
    default_kelly_divisor: int = 4
    default_risk_mode: Literal["conservative", "normal", "aggressive"] = "normal"
    max_single_stake_pct: float = 0.05
    daily_limit_pct: float = 0.15


class CalibrationPromotion(BaseModel):
    global_min_samples: int = 100
    by_market_min: int = 300
    by_track_min: int = 500
    brier_alert_increase: float = 0.01


class CalibrationBlockSettings(BaseModel):
    layer: Literal["identity", "platt", "isotonic"] = "identity"
    retrain_interval_days: int = 7
    lookback_days: int = 90
    promotion: CalibrationPromotion = Field(default_factory=CalibrationPromotion)


class ReflectionBlockSettings(BaseModel):
    top_n_lessons_in_prompt: int = 10
    auto_archive_applied: int = 20
    auto_archive_roi: float = -0.05
    promote_applied: int = 30
    promote_roi: float = 0.10


class PhaseOneSettings(BaseModel):
    mode: Literal["paper", "dry_run", "live"] = "paper"
    live_unlock: bool = False
    thresholds: ThresholdSettings = Field(default_factory=ThresholdSettings)
    sizing: SizingBlockSettings = Field(default_factory=SizingBlockSettings)
    calibration: CalibrationBlockSettings = Field(default_factory=CalibrationBlockSettings)
    reflection: ReflectionBlockSettings = Field(default_factory=ReflectionBlockSettings)
    checkpointer_path: str = "data/checkpoints.db"
