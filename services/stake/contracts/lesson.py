from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


LessonStatus = Literal["active", "archived", "promoted_to_rule"]


class PnLTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applied_count: int = 0
    realized_pnl: float = 0.0
    roi: float = 0.0
    last_applied_at: Optional[datetime] = None


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime
    tag: str
    condition: str
    action: str
    evidence_bet_ids: list[str] = Field(default_factory=list)
    pnl_track: PnLTrack = Field(default_factory=PnLTrack)
    status: LessonStatus = "active"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
