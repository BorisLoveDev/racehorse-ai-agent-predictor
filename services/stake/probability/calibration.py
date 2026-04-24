"""Calibrator interface + registry (Phase 1: identity only).

Registry precedence for `resolve(market, track)`: track -> market -> default.
Phase 3 will register Platt/isotonic calibrators at each level once sample
thresholds are reached (100 global / 300 market / 500 track).
"""
from typing import Optional, Protocol


class Calibrator(Protocol):
    def transform(self, p: float) -> float: ...


class IdentityCalibrator:
    """Phase 1 default — returns input unchanged."""
    def transform(self, p: float) -> float:
        return p


class CalibratorRegistry:
    def __init__(self, default: Calibrator):
        self._default = default
        self._by_market: dict[str, Calibrator] = {}
        self._by_track: dict[str, Calibrator] = {}

    def set_for_market(self, market: str, cal: Calibrator) -> None:
        self._by_market[market] = cal

    def set_for_track(self, track: str, cal: Calibrator) -> None:
        self._by_track[track] = cal

    def resolve(self, *, market: str, track: Optional[str]) -> Calibrator:
        if track and track in self._by_track:
            return self._by_track[track]
        if market in self._by_market:
            return self._by_market[market]
        return self._default
