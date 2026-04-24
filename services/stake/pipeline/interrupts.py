"""LangGraph interrupt payloads + resume schema.

Two interrupts in the Phase 1 super-graph:
  - InterruptGatePayload (Tier-1 pre-analysis gate) — options include
    'continue', 'skip', 'ask'. The TelegramGraphRunner (Task 20) renders a
    card; the user's button press maps to Command(resume={"decision": ...}).
  - InterruptApprovalPayload (per-slip approval) — options 'accept', 'edit',
    'reject', 'kill'. mode field is informational ('[PAPER]' label); the
    invariant check on live mode is enforced upstream (Task 13/15).

InterruptResume is the single schema that the Telegram bridge passes back.
Decision values come from the union of all gate/approval decisions.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


GateDecision = Literal["continue", "skip", "ask"]
ApprovalDecision = Literal["accept", "edit", "reject", "kill"]
ResumeDecision = Literal[
    "continue", "skip", "ask",
    "accept", "edit", "reject", "kill",
]


class InterruptGatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["gate"] = "gate"
    race_id: str
    reason: str
    overround: float
    missing_fields: list[str] = Field(default_factory=list)
    options: list[GateDecision]


class InterruptApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["approval"] = "approval"
    race_id: str
    bet_slip: dict                      # ProposedBetSlip.model_dump()
    rationale: str
    reflection_id: Optional[str] = None
    options: list[ApprovalDecision]
    mode: Literal["paper", "dry_run", "live"] = "paper"


class InterruptResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: ResumeDecision
    details: Optional[dict] = None
