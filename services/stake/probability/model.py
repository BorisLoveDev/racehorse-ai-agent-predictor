"""ProbabilityModel — overround-normalised market probabilities + bounded LLM adjustment.

Phase 1 flow:
  1. Implied probs from win_odds, normalised so they sum to 1.0 (overround removed).
  2. Aggregate LLMAdjustment per horse into signed pp shifts, then clip each
     horse's total shift to +/-MAX_TOTAL_SHIFT_PP (=3.0) to prevent runaway.
  3. Apply shifts, renormalise.
  4. Run the appropriate Calibrator (identity in Phase 1), renormalise.

p_raw and p_calibrated coincide in Phase 1 because IdentityCalibrator is the
only layer registered. Phase 3 will diverge them.
"""
from typing import Optional

from services.stake.contracts.llm import (
    LLMAdjustment, MAGNITUDE_TO_PP, MAX_TOTAL_SHIFT_PP,
)
from services.stake.probability.calibration import CalibratorRegistry
from services.stake.probability.models import RunnerProb


def _signed_pp(adj: LLMAdjustment) -> float:
    magnitude_pp = MAGNITUDE_TO_PP[adj.magnitude]
    if adj.direction == "up":
        return magnitude_pp
    if adj.direction == "down":
        return -magnitude_pp
    return 0.0  # neutral


def _aggregate_adjustments(adjustments: list[LLMAdjustment]) -> dict[int, float]:
    totals: dict[int, float] = {}
    for adj in adjustments:
        totals[adj.target_horse_no] = totals.get(adj.target_horse_no, 0.0) + _signed_pp(adj)
    for horse_no, pp in totals.items():
        if pp > MAX_TOTAL_SHIFT_PP:
            totals[horse_no] = MAX_TOTAL_SHIFT_PP
        elif pp < -MAX_TOTAL_SHIFT_PP:
            totals[horse_no] = -MAX_TOTAL_SHIFT_PP
    return totals


class ProbabilityModel:
    def __init__(self, *, registry: CalibratorRegistry, track: Optional[str], market: str):
        self.registry = registry
        self.track = track
        self.market = market

    def compute(
        self,
        runners: list[dict],
        adjustments: list[LLMAdjustment],
    ) -> list[RunnerProb]:
        implied = []
        for r in runners:
            odds = r.get("win_odds")
            if odds and odds > 1.0:
                implied.append((r["number"], 1.0 / odds))
        total = sum(p for _, p in implied)
        if total <= 0:
            return []

        p_market = {h: p / total for h, p in implied}
        shifts_pp = _aggregate_adjustments(adjustments)

        p_raw_raw = {
            h: max(1e-6, pm + shifts_pp.get(h, 0.0) / 100.0)
            for h, pm in p_market.items()
        }
        s = sum(p_raw_raw.values())
        p_raw = {h: v / s for h, v in p_raw_raw.items()}

        calibrator = self.registry.resolve(market=self.market, track=self.track)
        p_cal_raw = {h: calibrator.transform(v) for h, v in p_raw.items()}
        s2 = sum(p_cal_raw.values())
        p_cal = {h: v / s2 for h, v in p_cal_raw.items()}

        return [
            RunnerProb(
                horse_no=h,
                p_market=p_market[h],
                p_raw=p_raw[h],
                p_calibrated=p_cal[h],
                applied_adjustment_pp=shifts_pp.get(h, 0.0),
            )
            for h in p_market
        ]
