from datetime import datetime, timezone

from services.stake.audit.trace import AuditTraceRecorder


def test_accumulates_steps():
    rec = AuditTraceRecorder(race_id="R1", thread_id="race:R1:1",
                             started_at=datetime.now(timezone.utc))
    rec.step(step_name="parse", model="m1", prompt_hash="p1",
             inputs_hash="i1", outputs_hash="o1", cost_usd=0.001, temperature=0.0)
    rec.step(step_name="analyst", model="m2", prompt_hash="p2",
             inputs_hash="i2", outputs_hash="o2", cost_usd=0.02, temperature=0.3)
    trace = rec.finalise()
    assert len(trace.steps) == 2
    assert trace.reproducible is False
    assert trace.finished_at is not None
    assert abs(trace.total_cost_usd - 0.021) < 1e-9


def test_reproducible_when_all_low_temp():
    rec = AuditTraceRecorder(race_id="R2", thread_id="race:R2:1",
                             started_at=datetime.now(timezone.utc))
    rec.step(step_name="parse", model="m", prompt_hash="p",
             inputs_hash="i", outputs_hash="o", cost_usd=0.0, temperature=0.0)
    rec.step(step_name="sizer", model="m", prompt_hash="p",
             inputs_hash="i", outputs_hash="o", cost_usd=0.0, temperature=0.1)
    trace = rec.finalise()
    assert trace.reproducible is True


def test_error_flag_makes_non_reproducible():
    rec = AuditTraceRecorder(race_id="R3", thread_id="race:R3:1",
                             started_at=datetime.now(timezone.utc))
    rec.step(step_name="parse", model="m", prompt_hash="p",
             inputs_hash="i", outputs_hash="o",
             cost_usd=0.0, temperature=0.0, error="rate_limit")
    trace = rec.finalise()
    assert trace.reproducible is False


def test_empty_recorder_finalises():
    rec = AuditTraceRecorder(race_id="R4", thread_id="race:R4:1",
                             started_at=datetime.now(timezone.utc))
    trace = rec.finalise()
    assert trace.steps == []
    # Empty step list is vacuously reproducible (all([]) is True).
    assert trace.reproducible is True
    assert trace.total_cost_usd == 0.0


def test_step_ts_is_auto_populated():
    rec = AuditTraceRecorder(race_id="R5", thread_id="race:R5:1",
                             started_at=datetime.now(timezone.utc))
    rec.step(step_name="parse", model="m", prompt_hash="p",
             inputs_hash="i", outputs_hash="o", cost_usd=0.0, temperature=0.0)
    trace = rec.finalise()
    assert trace.steps[0].ts is not None


def test_finalise_uses_override_clock():
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rec = AuditTraceRecorder(race_id="R6", thread_id="race:R6:1",
                             started_at=datetime.now(timezone.utc))
    trace = rec.finalise(now=fixed)
    assert trace.finished_at == fixed
