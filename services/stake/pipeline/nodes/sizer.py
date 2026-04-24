"""Sizer node (spec shaft 7) — Kelly + caps -> ProposedBetSlip[].

Enforces invariants:
  I4: sizer reads only p_calibrated (never p_raw).
  I5: edge = p_calibrated - p_market; below thresholds.min_edge_pp => stake 0
      and caps_applied includes 'edge_below_threshold' (paper-only intent).
  I6: drawdown, per-bet cap, daily cap enforced BEFORE slip is emitted. The
      drawdown gate runs once at the top of the node; per-bet + daily caps
      run per-intent and trim the stake (or zero it).
  I1 (defensive): compute_proposed_slip re-asks the checker whether the
     requested mode can be live, so even a bug in upstream can't route a
     live slip through Phase 1.

Phase 1 sizer supports win-single only. Multi-leg markets (trifecta_box etc.)
are emitted as zero-stake placeholders tagged 'phase1_market_unsupported' so
the audit trail shows the intent without producing a stake.
"""
from typing import Optional

from services.stake.config.models import PhaseOneSettings
from services.stake.contracts import (
    BetIntent, ProposedBetSlip, SizingParams, Mode,
)
from services.stake.invariants.checker import InvariantChecker
from services.stake.pipeline.state import PipelineState


def _full_kelly(p: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f = (p * b - q) / b
    return max(0.0, f)


def compute_proposed_slip(
    *,
    intent: BetIntent,
    p_calibrated: float,
    p_market: float,
    win_odds: float,
    bankroll: float,
    total_today: float,
    settings: PhaseOneSettings,
    checker: InvariantChecker,
    requested_mode: Optional[Mode] = None,
) -> ProposedBetSlip:
    mode: Mode = requested_mode or settings.mode
    checker.check_bet_slip_can_be_live(requested_mode=mode)

    caps: list[str] = []
    kelly_divisor = settings.sizing.default_kelly_divisor
    kelly_fraction_param = 1.0 / kelly_divisor
    sizing_params = SizingParams(
        kelly_fraction=kelly_fraction_param,
        risk_mode=settings.sizing.default_risk_mode,
    )

    edge_pp = (p_calibrated - p_market) * 100.0
    if edge_pp < settings.thresholds.min_edge_pp:
        caps.append("edge_below_threshold")
        return ProposedBetSlip(
            intent=intent, stake=0.0, kelly_fraction_used=kelly_fraction_param,
            expected_return=0.0, expected_value=0.0,
            max_loss=0.0, profit_if_win=0.0, portfolio_var_95=0.0,
            caps_applied=caps, sizing_params=sizing_params, mode=mode,
        )

    full_kelly = _full_kelly(p_calibrated, win_odds)
    fractional = full_kelly * kelly_fraction_param
    if fractional < settings.thresholds.min_kelly_fraction:
        caps.append("below_min_kelly_fraction")
        stake = 0.0
    else:
        stake = fractional * bankroll

    per_bet_cap = bankroll * settings.sizing.max_single_stake_pct
    if stake > per_bet_cap:
        stake = per_bet_cap
        caps.append("per_bet_cap")

    daily_cap_remaining = bankroll * settings.sizing.daily_limit_pct - total_today
    if stake > daily_cap_remaining:
        stake = max(0.0, daily_cap_remaining)
        caps.append("daily_limit")

    stake = round(stake, 2)
    if stake > 0:
        checker.check_sizing_caps(stake=stake, bankroll=bankroll, total_today=total_today)

    profit_if_win = stake * (win_odds - 1.0)
    max_loss = stake
    expected_return = stake * win_odds * p_calibrated
    expected_value = expected_return - stake
    # Phase 1: VaR95 == max_loss whenever P(lose) >= 5%. Phase 3 replaces with MC.
    portfolio_var_95 = max_loss if (1.0 - p_calibrated) >= 0.05 else 0.0

    return ProposedBetSlip(
        intent=intent, stake=stake, kelly_fraction_used=kelly_fraction_param,
        expected_return=expected_return, expected_value=expected_value,
        max_loss=max_loss, profit_if_win=profit_if_win, portfolio_var_95=portfolio_var_95,
        caps_applied=caps, sizing_params=sizing_params, mode=mode,
    )


def make_sizer_node(
    *, settings: PhaseOneSettings, checker: InvariantChecker, bankroll_repo,
):
    async def sizer_node(state: PipelineState) -> dict:
        intents_raw = state.get("bet_intents") or []
        probs_raw = state.get("probabilities") or []
        runners = state.get("enriched_runners") or []
        p_by_horse = {p["horse_no"]: p for p in probs_raw}
        odds_by_horse = {r["number"]: r.get("win_odds") for r in runners}

        bankroll = float(bankroll_repo.current_balance())
        peak = float(bankroll_repo.peak_balance())
        checker.check_drawdown(current=bankroll, peak=peak)  # raises if tripped
        total_today = float(bankroll_repo.staked_today())

        slips: list[dict] = []
        for raw in intents_raw:
            intent = BetIntent.model_validate(raw)

            # Phase 1: only win-single gets a real stake calc.
            if intent.market != "win" or len(intent.selections) != 1:
                placeholder = ProposedBetSlip(
                    intent=intent, stake=0.0, kelly_fraction_used=0.0,
                    expected_return=0.0, expected_value=0.0,
                    max_loss=0.0, profit_if_win=0.0, portfolio_var_95=0.0,
                    caps_applied=["phase1_market_unsupported"],
                    sizing_params=SizingParams(
                        kelly_fraction=1.0 / settings.sizing.default_kelly_divisor,
                        risk_mode=settings.sizing.default_risk_mode,
                    ),
                    mode=settings.mode,
                )
                slips.append(placeholder.model_dump(mode="json"))
                continue

            horse = intent.selections[0]
            p = p_by_horse.get(horse)
            odds = odds_by_horse.get(horse)
            if not p or not odds:
                # Missing probability or odds — skip silently. No slip emitted.
                continue

            slip = compute_proposed_slip(
                intent=intent,
                p_calibrated=float(p["p_calibrated"]),
                p_market=float(p["p_market"]),
                win_odds=float(odds),
                bankroll=bankroll,
                total_today=total_today,
                settings=settings, checker=checker,
            )
            total_today += slip.stake
            slips.append(slip.model_dump(mode="json"))

        return {"proposed_bet_slips": slips}
    return sizer_node
