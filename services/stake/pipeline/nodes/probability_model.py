"""probability_model node (spec shaft 5).

Computes RunnerProb for each runner using the ProbabilityModel + Calibrator
registry. Writes one row per runner into stake_calibration_samples (outcome
NULL until settlement updates it). Reads LLMAdjustment[] from state (usually
empty in Phase 1 since Analyst runs AFTER this node — Phase 2+ may re-run).
"""
from datetime import datetime, timezone

from services.stake.calibration.samples import CalibrationSamplesRepository
from services.stake.contracts.llm import LLMAdjustment
from services.stake.pipeline.state import PipelineState
from services.stake.probability.calibration import CalibratorRegistry
from services.stake.probability.model import ProbabilityModel


def make_probability_model_node(
    *,
    registry: CalibratorRegistry,
    samples_repo: CalibrationSamplesRepository,
):
    async def probability_model_node(state: PipelineState) -> dict:
        parsed = state.get("parsed_race") or {}
        track = parsed.get("track") if isinstance(parsed, dict) else None
        jurisdiction = parsed.get("country") if isinstance(parsed, dict) else None
        runners = state.get("enriched_runners") or []
        adjustments_raw = state.get("llm_adjustments") or []
        # Strict validation — if the LLM ever injected a forbidden field,
        # LLMAdjustment.model_validate raises (invariant I2).
        adjustments = [LLMAdjustment.model_validate(a) for a in adjustments_raw]

        model = ProbabilityModel(registry=registry, track=track, market="win")
        probs = model.compute(runners=runners, adjustments=adjustments)

        now = datetime.now(timezone.utc)
        race_id = state.get("race_id") or "unknown"
        for rp in probs:
            samples_repo.insert(
                race_id=race_id,
                horse_no=rp.horse_no,
                market="win",
                track=track,
                jurisdiction=jurisdiction,
                p_model_raw=rp.p_raw,
                p_model_calibrated=rp.p_calibrated,
                p_market=rp.p_market,
                placed_bet=False,
                ts=now,
            )

        return {"probabilities": [p.model_dump(mode="json") for p in probs]}
    return probability_model_node
