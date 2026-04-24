from pydantic import BaseModel, ConfigDict


class RunnerProb(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horse_no: int
    p_market: float
    p_raw: float
    p_calibrated: float
    applied_adjustment_pp: float = 0.0
