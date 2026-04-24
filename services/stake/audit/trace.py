"""In-memory audit trace recorder.

Lifecycle:
  - TelegramGraphRunner (Task 20/22) creates one AuditTraceRecorder per race
    when `start_race(...)` is called.
  - Each LLM-invoking node (parse, analyst, reflection) calls
    `recorder.step(step_name=..., model=..., temperature=..., cost_usd=..., ...)`
    once per LLM call.
  - The reflection_update node calls `recorder.finalise()` and passes the
    resulting AuditTrace to AuditTracesRepository.save(trace).

Reproducibility:
  Trace.reproducible is True iff every step has temperature <= 0.1 AND no error.
  An empty step list is vacuously reproducible. The live-mode invariant I8 uses
  the last-10 reproducibility window to decide whether to allow mode transitions.
"""
from datetime import datetime, timezone
from typing import Optional

from services.stake.contracts.audit import AuditTrace, AuditStep


class AuditTraceRecorder:
    def __init__(self, *, race_id: str, thread_id: str, started_at: datetime):
        self.trace = AuditTrace(
            race_id=race_id, thread_id=thread_id, started_at=started_at,
        )

    def step(
        self,
        *,
        step_name: str,
        model: str,
        prompt_hash: str,
        inputs_hash: str,
        outputs_hash: str,
        cost_usd: float,
        temperature: float,
        error: Optional[str] = None,
    ) -> None:
        self.trace.steps.append(AuditStep(
            step_name=step_name,
            ts=datetime.now(timezone.utc),
            inputs_hash=inputs_hash,
            outputs_hash=outputs_hash,
            model=model,
            prompt_hash=prompt_hash,
            cost_usd=cost_usd,
            temperature=temperature,
            error=error,
        ))

    def finalise(self, now: Optional[datetime] = None) -> AuditTrace:
        self.trace.finish(now=now)
        return self.trace
