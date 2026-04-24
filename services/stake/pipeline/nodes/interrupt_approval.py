"""interrupt_approval (spec shaft 8).

For each positive-stake proposed slip, persist a draft BetSlip row
(status='draft') and emit an InterruptApprovalPayload via langgraph.interrupt().
The graph pauses; when the Telegram bridge sends Command(resume={decision,
details}) the status transitions:
  - accept / edit -> 'confirmed' (edit stores details in user_edits)
  - reject        -> 'cancelled'
  - kill          -> 'cancelled' + halt remaining slips (kill_requested=True)

Invariant I7: checkpointer persists graph state BEFORE interrupt() pauses,
so a crash mid-race leaves the slip in 'draft' and the approval can be
re-tried by resuming the thread_id.

Re-execution note: LangGraph re-runs the whole node body on resume, so
save_bet_slip is called a second time with the same idempotency_key. The
UNIQUE constraint fires IntegrityError, which we swallow — the prior draft
row is still there and the idempotency_key guarantees we do not double-book.
"""
import sqlite3
from typing import Optional

from langgraph.types import interrupt

from services.stake.contracts import (
    BetSlip, ProposedBetSlip, make_idempotency_key, Mode,
)
from services.stake.pipeline.interrupts import (
    InterruptApprovalPayload, InterruptResume,
)
from services.stake.pipeline.state import PipelineState


def build_approval_payload(
    *,
    race_id: str,
    slip: dict,
    rationale: str,
    mode: Mode,
    reflection_id: Optional[str],
) -> InterruptApprovalPayload:
    return InterruptApprovalPayload(
        race_id=race_id, bet_slip=slip, rationale=rationale,
        reflection_id=reflection_id, mode=mode,
        options=["accept", "edit", "reject", "kill"],
    )


def make_interrupt_approval_node(*, bankroll_repo, mode: Mode):
    async def interrupt_approval_node(state: PipelineState) -> dict:
        race_id = state.get("race_id") or "unknown"
        user_id = int(state.get("user_id") or 0)
        slips = state.get("final_proposed_slips") or []
        if not slips:
            return {}

        bet_slip_ids: list[str] = []
        decisions: list[str] = []

        for slip_dict in slips:
            proposed = ProposedBetSlip.model_validate(slip_dict)
            idem = make_idempotency_key(
                user_id, race_id, proposed.intent.market, proposed.intent.selections,
            )
            bet = BetSlip(
                race_id=race_id, user_id=user_id, proposed=proposed,
                idempotency_key=idem, status="draft",
            )
            try:
                bankroll_repo.save_bet_slip(bet.model_dump(mode="json"))
            except sqlite3.IntegrityError:
                # LangGraph re-runs the whole node on resume; fetch the
                # previously persisted slip so downstream status updates
                # hit the existing row, not a newly minted uuid.
                lookup = getattr(bankroll_repo, "get_bet_slip_id_by_idempotency_key", None)
                if lookup is not None:
                    prior = lookup(idem)
                    if prior:
                        bet = bet.model_copy(update={"id": prior})
            bet_slip_ids.append(bet.id)

            payload = build_approval_payload(
                race_id=race_id, slip=slip_dict,
                rationale=state.get("decision_rationale") or "",
                mode=mode, reflection_id=None,
            )
            response = interrupt(payload.model_dump(mode="json"))
            resume = InterruptResume.model_validate(response)
            decisions.append(resume.decision)

            if resume.decision == "accept":
                bankroll_repo.update_bet_slip_status(
                    bet.id, "confirmed", user_edits=resume.details,
                )
            elif resume.decision == "edit":
                bankroll_repo.update_bet_slip_status(
                    bet.id, "confirmed", user_edits=resume.details,
                )
            elif resume.decision == "kill":
                bankroll_repo.update_bet_slip_status(
                    bet.id, "cancelled", user_edits={"kill": True},
                )
                return {
                    "bet_slip_ids": bet_slip_ids,
                    "approval_decisions": decisions,
                    "kill_requested": True,
                }
            else:  # reject
                bankroll_repo.update_bet_slip_status(
                    bet.id, "cancelled", user_edits=resume.details,
                )

        return {
            "bet_slip_ids": bet_slip_ids,
            "approval_decisions": decisions,
        }
    return interrupt_approval_node
