import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from services.stake.contracts.bet import (
    BetIntent, ProposedBetSlip, BetSlip, SizingParams, make_idempotency_key,
)
from services.stake.contracts.llm import LLMAdjustment, MAGNITUDE_TO_PP, MAX_TOTAL_SHIFT_PP
from services.stake.contracts.audit import AuditTrace, AuditStep
from services.stake.contracts.lesson import Lesson, PnLTrack


def test_idempotency_key_stable_under_selection_reorder():
    k1 = make_idempotency_key(user_id=42, race_id="R1", market="win", selections=[3, 1])
    k2 = make_idempotency_key(user_id=42, race_id="R1", market="win", selections=[1, 3])
    assert k1 == k2


def test_idempotency_key_differs_on_market():
    k1 = make_idempotency_key(user_id=42, race_id="R1", market="win", selections=[3])
    k2 = make_idempotency_key(user_id=42, race_id="R1", market="place", selections=[3])
    assert k1 != k2


def test_bet_intent_rejects_unknown_market():
    with pytest.raises(ValidationError):
        BetIntent(market="bogus", selections=[1], confidence=0.5,
                  rationale_id="r1", edge_source="p_model")


def test_bet_intent_rejects_empty_selections():
    with pytest.raises(ValidationError):
        BetIntent(market="win", selections=[], confidence=0.5,
                  rationale_id="r1", edge_source="p_model")


def test_bet_intent_confidence_in_zero_to_one():
    with pytest.raises(ValidationError):
        BetIntent(market="win", selections=[1], confidence=1.5,
                  rationale_id="r1", edge_source="p_model")


def test_llm_adjustment_direction_magnitude():
    adj = LLMAdjustment(target_horse_no=3, direction="up", magnitude="small",
                        rationale="form trend")
    assert adj.direction == "up"


def test_llm_adjustment_rejects_probability_field():
    # Invariant I2: LLM cannot emit a probability.
    with pytest.raises(ValidationError):
        LLMAdjustment(target_horse_no=3, direction="up", magnitude="small",
                      rationale="x", probability=0.42)


def test_llm_adjustment_magnitude_pp_mapping():
    assert MAGNITUDE_TO_PP["none"] == 0.0
    assert MAGNITUDE_TO_PP["small"] == 1.0
    assert MAGNITUDE_TO_PP["medium"] == 2.0
    assert MAGNITUDE_TO_PP["large"] == 3.0
    assert MAX_TOTAL_SHIFT_PP == 3.0


def test_proposed_bet_slip_has_risk_triplet():
    intent = BetIntent(market="win", selections=[3], confidence=0.6,
                       rationale_id="r1", edge_source="p_model")
    sp = SizingParams(kelly_fraction=0.25, risk_mode="normal")
    slip = ProposedBetSlip(
        intent=intent, stake=5.0, kelly_fraction_used=0.25,
        expected_return=6.0, expected_value=0.3,
        max_loss=5.0, profit_if_win=10.0, portfolio_var_95=5.0,
        caps_applied=[], sizing_params=sp, mode="paper",
    )
    assert slip.max_loss == 5.0
    assert slip.profit_if_win == 10.0
    assert slip.portfolio_var_95 == 5.0


def test_proposed_bet_slip_rejects_negative_risk():
    intent = BetIntent(market="win", selections=[3], confidence=0.6,
                       rationale_id="r", edge_source="p_model")
    sp = SizingParams(kelly_fraction=0.25, risk_mode="normal")
    with pytest.raises(ValidationError):
        ProposedBetSlip(
            intent=intent, stake=5.0, kelly_fraction_used=0.25,
            expected_return=6.0, expected_value=0.3,
            max_loss=-1.0, profit_if_win=10.0, portfolio_var_95=5.0,
            caps_applied=[], sizing_params=sp, mode="paper",
        )


def test_bet_slip_lifecycle():
    intent = BetIntent(market="win", selections=[1], confidence=0.4,
                       rationale_id="r2", edge_source="p_model")
    sp = SizingParams(kelly_fraction=0.25, risk_mode="normal")
    proposed = ProposedBetSlip(
        intent=intent, stake=2.0, kelly_fraction_used=0.25,
        expected_return=3.0, expected_value=0.1,
        max_loss=2.0, profit_if_win=4.0, portfolio_var_95=2.0,
        caps_applied=[], sizing_params=sp, mode="paper",
    )
    slip = BetSlip(
        race_id="R1", user_id=1, proposed=proposed,
        idempotency_key=make_idempotency_key(1, "R1", "win", [1]),
        status="draft",
    )
    assert slip.status == "draft"
    assert slip.id  # auto-generated UUID
    slip.status = "confirmed"
    slip.confirmed_at = datetime.now(timezone.utc)
    assert slip.confirmed_at is not None


def test_bet_slip_rejects_unknown_status():
    intent = BetIntent(market="win", selections=[1], confidence=0.4,
                       rationale_id="r", edge_source="p_model")
    sp = SizingParams(kelly_fraction=0.25, risk_mode="normal")
    proposed = ProposedBetSlip(
        intent=intent, stake=1.0, kelly_fraction_used=0.25,
        expected_return=2.0, expected_value=0.1,
        max_loss=1.0, profit_if_win=1.0, portfolio_var_95=1.0,
        caps_applied=[], sizing_params=sp, mode="paper",
    )
    with pytest.raises(ValidationError):
        BetSlip(race_id="R1", user_id=1, proposed=proposed,
                idempotency_key="k", status="bogus")


def test_audit_trace_not_reproducible_with_high_temp_step():
    trace = AuditTrace(race_id="R1", thread_id="race:R1:1",
                       started_at=datetime.now(timezone.utc))
    trace.steps.append(AuditStep(
        step_name="parse", ts=datetime.now(timezone.utc),
        inputs_hash="h1", outputs_hash="h2",
        model="m1", prompt_hash="p1", cost_usd=0.001, temperature=0.0,
    ))
    trace.steps.append(AuditStep(
        step_name="analyst", ts=datetime.now(timezone.utc),
        inputs_hash="h3", outputs_hash="h4",
        model="m2", prompt_hash="p2", cost_usd=0.02, temperature=0.3,
    ))
    trace.finish()
    assert trace.reproducible is False
    assert trace.finished_at is not None
    assert abs(trace.total_cost_usd - 0.021) < 1e-9


def test_audit_trace_reproducible_when_all_low_temp():
    trace = AuditTrace(race_id="R2", thread_id="race:R2:1",
                       started_at=datetime.now(timezone.utc))
    trace.steps.append(AuditStep(
        step_name="parse", ts=datetime.now(timezone.utc),
        inputs_hash="h", outputs_hash="h", model="m",
        prompt_hash="p", cost_usd=0.0, temperature=0.0,
    ))
    trace.steps.append(AuditStep(
        step_name="sizer", ts=datetime.now(timezone.utc),
        inputs_hash="h", outputs_hash="h", model="m",
        prompt_hash="p", cost_usd=0.0, temperature=0.1,
    ))
    trace.finish()
    assert trace.reproducible is True


def test_audit_trace_reproducible_false_when_any_step_errored():
    trace = AuditTrace(race_id="R3", thread_id="race:R3:1",
                       started_at=datetime.now(timezone.utc))
    trace.steps.append(AuditStep(
        step_name="parse", ts=datetime.now(timezone.utc),
        inputs_hash="h", outputs_hash="h", model="m",
        prompt_hash="p", cost_usd=0.0, temperature=0.0,
        error="rate_limit",
    ))
    trace.finish()
    assert trace.reproducible is False


def test_lesson_defaults_pnl_track_and_status():
    lesson = Lesson(
        created_at=datetime.now(timezone.utc),
        tag="sandown_good_favourite",
        condition="at Sandown with going=Good",
        action="favs <2.5 underpriced ~6%",
    )
    assert lesson.status == "active"
    assert lesson.pnl_track.applied_count == 0
    assert lesson.confidence == 0.5
    assert lesson.evidence_bet_ids == []


def test_lesson_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        Lesson(created_at=datetime.now(timezone.utc),
               tag="t", condition="c", action="a", confidence=1.5)
