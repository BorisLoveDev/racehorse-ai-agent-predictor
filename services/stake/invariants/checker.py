"""Runtime enforcement of non-negotiable invariants I1..I9.

Phase 1 implements I1 (startup + per-slip), I6 (caps + drawdown), I7 (caller
responsibility — see interrupt_approval node), and I8 (reproducibility check,
no-op until live mode is ever permitted).

I2..I5 and I9 are enforced contextually inside individual nodes (analyst
validator, sizer edge check, promote-live command handler) — see their tasks.
"""
from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.rules import InvariantViolation


class InvariantChecker:
    def __init__(self, settings: PhaseOneSettings):
        self.settings = settings

    def run_startup(self) -> None:
        if self.settings.mode == "live" and not self.settings.live_unlock:
            raise InvariantViolation("I1", "mode=live but live_unlock=False")
        if self.settings.mode == "live":
            # Phase 1 never promotes; I8/I9 always block live here.
            raise InvariantViolation("I1", "live mode disallowed in Phase 1")

    def check_bet_slip_can_be_live(self, *, requested_mode: str) -> None:
        if requested_mode == "live" and self.settings.mode != "live":
            raise InvariantViolation(
                "I1", f"requested live bet while agent mode={self.settings.mode}"
            )
        if requested_mode == "live" and not self.settings.live_unlock:
            raise InvariantViolation("I1", "requested live bet but live_unlock=False")

    def check_sizing_caps(
        self, *, stake: float, bankroll: float, total_today: float
    ) -> None:
        if bankroll <= 0:
            raise InvariantViolation("I6", "non-positive bankroll")
        if stake / bankroll > self.settings.sizing.max_single_stake_pct + 1e-9:
            raise InvariantViolation(
                "I6",
                f"stake {stake:.4f} exceeds max_single_stake_pct="
                f"{self.settings.sizing.max_single_stake_pct} of bankroll {bankroll:.4f}",
            )
        if (total_today + stake) / bankroll > self.settings.sizing.daily_limit_pct + 1e-9:
            raise InvariantViolation(
                "I6",
                f"daily total {total_today + stake:.4f} exceeds "
                f"daily_limit_pct={self.settings.sizing.daily_limit_pct}",
            )

    def check_drawdown(self, *, current: float, peak: float) -> None:
        if peak <= 0:
            return
        drawdown = (peak - current) / peak
        if drawdown >= self.settings.thresholds.drawdown_lock_pct:
            raise InvariantViolation(
                "I6",
                f"drawdown {drawdown:.2%} >= threshold "
                f"{self.settings.thresholds.drawdown_lock_pct:.2%}",
            )

    def check_reproducibility_for_live(self, *, last_10_reproducible: list[bool]) -> None:
        if self.settings.mode != "live":
            return
        if not all(last_10_reproducible):
            raise InvariantViolation(
                "I8", "at least one of last 10 races is non-reproducible"
            )
