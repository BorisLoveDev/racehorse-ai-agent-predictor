import hashlib
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


Market = Literal[
    "win", "place", "quinella", "exacta",
    "trifecta", "trifecta_box", "first4",
]

RiskMode = Literal["conservative", "normal", "aggressive"]
Mode = Literal["paper", "dry_run", "live"]
SlipStatus = Literal["draft", "confirmed", "cancelled", "expired"]


class BetIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Market
    selections: list[int] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_id: str
    edge_source: str


class SizingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kelly_fraction: float = Field(gt=0.0, le=1.0)
    risk_mode: RiskMode


class ProposedBetSlip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: BetIntent
    stake: float = Field(ge=0.0)
    kelly_fraction_used: float
    expected_return: float
    expected_value: float
    max_loss: float = Field(ge=0.0)
    profit_if_win: float = Field(ge=0.0)
    portfolio_var_95: float = Field(ge=0.0)
    caps_applied: list[str]
    sizing_params: SizingParams
    mode: Mode


class BetSlip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    race_id: str
    user_id: int
    proposed: ProposedBetSlip
    idempotency_key: str
    status: SlipStatus = "draft"
    confirmed_at: Optional[datetime] = None
    user_edits: Optional[dict] = None


def make_idempotency_key(
    user_id: int, race_id: str, market: str, selections: list[int]
) -> str:
    """SHA-256 short-hash over (user_id, race_id, market, sorted_selections).

    Stable under selection reorder (sorted before hashing). Truncated to 32 hex
    chars — ample collision resistance for a single-user paper bot.
    """
    sel = ",".join(str(s) for s in sorted(selections))
    payload = f"{user_id}|{race_id}|{market}|{sel}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
