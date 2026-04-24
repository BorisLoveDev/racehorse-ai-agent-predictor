"""settlement (spec shaft 10).

1. For each horse in the race (from probabilities), mark outcome in
   stake_calibration_samples: 1 if finished 1st, 0 otherwise, for market='win'.
2. For each confirmed bet slip, compute PnL (+profit_if_win on win, -stake on
   loss) and apply to paper bankroll (paper_mode only). Cancelled/draft/missing
   slips are skipped.
3. Emit settlement_pnl for downstream reflection.
"""
from services.stake.pipeline.state import PipelineState


def make_settlement_node(*, samples_repo, bankroll_repo, paper_mode: bool):
    async def settlement_node(state: PipelineState) -> dict:
        race_id = state.get("race_id")
        outcome = state.get("result_outcome") or {}
        probs = state.get("probabilities") or []

        # 1. Mark outcomes per horse (market='win').
        for p in probs:
            horse_no = p["horse_no"]
            pos = outcome.get(horse_no)
            if pos is None:
                continue
            samples_repo.set_outcome(
                race_id=race_id, horse_no=horse_no, market="win",
                outcome=1 if pos == 1 else 0,
            )

        # 2. PnL for confirmed slips.
        total_pnl = 0.0
        for slip_id in state.get("bet_slip_ids") or []:
            slip = bankroll_repo.get_bet_slip(slip_id)
            if not slip or slip.get("status") != "confirmed":
                continue
            selections = slip.get("proposed", {}).get("intent", {}).get("selections") or []
            if not selections:
                continue
            horse = selections[0]
            won = outcome.get(horse) == 1
            stake = float(slip.get("stake", 0.0))
            profit = float(slip.get("proposed", {}).get("profit_if_win", 0.0))
            pnl = profit if won else -stake
            total_pnl += pnl

        if paper_mode and total_pnl != 0.0:
            bankroll_repo.apply_paper_pnl(race_id=race_id, pnl=total_pnl)

        return {"settlement_pnl": total_pnl}
    return settlement_node
