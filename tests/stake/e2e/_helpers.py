"""Helpers shared by the e2e scenarios.

Kept in a plain module (not conftest) so it can be imported under
`tests.stake.e2e._helpers` without pytest plugin gymnastics.
"""


class StubShiftCalibrator:
    """Power-transform calibrator: p -> p**power (non-linear, sharpens the
    distribution when power > 1).

    Renormalisation inside ProbabilityModel keeps the result on the simplex,
    but because the transform is non-linear it produces a distribution that
    differs from p_market. That gives the sizer a non-zero edge on the
    favourite so the happy-path e2e test can exercise the full approval -
    settlement flow.

    A uniform additive shift + renormalise collapses back toward p_market
    (fails to produce usable edge); a power transform sharpens the leader
    which is exactly the pattern we need for a realistic positive-edge bet.
    """

    def __init__(self, power: float = 2.0, shift_pp: float | None = None):
        # shift_pp preserved for call-site readability; we treat any positive
        # value as a request for the default sharpening power.
        if shift_pp is not None:
            # Larger shift_pp = sharper transform. 10pp -> power 1.5, 20pp -> 2.
            self.power = max(1.0, 1.0 + shift_pp / 20.0)
        else:
            self.power = power

    def transform(self, p: float) -> float:
        return max(1e-9, p ** self.power)
