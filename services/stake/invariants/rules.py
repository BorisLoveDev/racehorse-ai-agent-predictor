"""Non-negotiable invariants I1..I9. Single source of truth for rule ids/messages."""


class InvariantViolation(RuntimeError):
    def __init__(self, rule_id: str, message: str):
        self.rule_id = rule_id
        super().__init__(f"[{rule_id}] {message}")


INVARIANTS = {
    "I1": "Agent shall never place a live bet without mode=live AND live_unlock=true.",
    "I2": "LLM never outputs probabilities; only bounded LLMAdjustment.",
    "I3": "Parser must-have fields require raw_excerpt.",
    "I4": "Sizer receives only p_calibrated.",
    "I5": "Kelly edge below threshold => paper-only intent.",
    "I6": "Drawdown/daily/per-bet caps enforced before ProposedBetSlip emitted.",
    "I7": "Checkpoint persists before any irreversible user-visible action.",
    "I8": "Live forbidden if audit.reproducible=false in any of last 10 races.",
    "I9": "paper->live requires paper samples + Brier + reproducibility + explicit promote.",
}
