from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


Direction = Literal["up", "down", "neutral"]
Magnitude = Literal["none", "small", "medium", "large"]


class LLMAdjustment(BaseModel):
    """Qualitative probability adjustment from the Analyst LLM.

    Invariant I2: the LLM must NEVER emit a probability. `extra="forbid"` makes
    any stray field (including 'probability', 'p_raw', etc.) raise ValidationError.
    Python translates {direction, magnitude} into a bounded pp shift inside
    ProbabilityModel; the total per-horse shift is capped at ±MAX_TOTAL_SHIFT_PP.
    """
    model_config = ConfigDict(extra="forbid")

    target_horse_no: int
    direction: Direction
    magnitude: Magnitude
    rationale: str = Field(max_length=500)


MAGNITUDE_TO_PP = {
    "none": 0.0,
    "small": 1.0,
    "medium": 2.0,
    "large": 3.0,
}
MAX_TOTAL_SHIFT_PP = 3.0
