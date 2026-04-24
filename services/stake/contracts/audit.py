from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


REPRODUCIBLE_TEMPERATURE_MAX = 0.1


class AuditStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_name: str
    ts: datetime
    inputs_hash: str
    outputs_hash: str
    model: str
    prompt_hash: str
    cost_usd: float = 0.0
    temperature: float = 0.0
    error: Optional[str] = None


class AuditTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    race_id: str
    thread_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    reproducible: Optional[bool] = None
    steps: list[AuditStep] = Field(default_factory=list)
    total_cost_usd: float = 0.0

    def finish(self, now: Optional[datetime] = None) -> None:
        self.finished_at = now or datetime.now(timezone.utc)
        self.total_cost_usd = sum(s.cost_usd for s in self.steps)
        self.reproducible = all(
            s.temperature <= REPRODUCIBLE_TEMPERATURE_MAX and s.error is None
            for s in self.steps
        )
