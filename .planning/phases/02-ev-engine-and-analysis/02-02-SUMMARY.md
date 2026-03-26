---
phase: 02-ev-engine-and-analysis
plan: "02"
subsystem: ev-kelly-math
tags: [math, kelly, ev, sizing, tdd, pure-functions, arch-01]
dependency_graph:
  requires: ["02-01"]
  provides: ["no_vig_probability", "expected_value", "kelly_fraction", "bet_size_usdt", "apply_portfolio_caps", "apply_sparsity_discount", "place_bet_ev", "pre_skip_check_node"]
  affects: ["services/stake/parser/math.py", "services/stake/pipeline/nodes.py"]
tech_stack:
  added: []
  patterns: ["TDD red-green", "pure functions", "quarter-Kelly sizing", "portfolio caps"]
key_files:
  created:
    - tests/stake/test_ev_kelly_math.py
  modified:
    - services/stake/parser/math.py
    - services/stake/pipeline/nodes.py
decisions:
  - "kelly_fraction clamps to 0.0 for breakeven EV (<=0) — no bet at zero edge"
  - "apply_portfolio_caps preserves highest-EV bets when trimming win bet count"
  - "apply_sparsity_discount applies 1.0 USDT minimum check after discounting"
  - "pre_skip_check_node uses strict > comparison (not >=) for threshold — exactly-at-threshold races proceed"
metrics:
  duration: "2 minutes"
  completed_date: "2026-03-26"
  tasks_completed: 1
  files_modified: 3
---

# Phase 02 Plan 02: EV/Kelly Math Engine + Pre-Skip Node Summary

**One-liner:** Pure-Python EV/Kelly math engine (7 functions) with quarter-Kelly sizing, portfolio caps, sparsity discount, and overround-based pre-skip node — fully TDD tested (56 tests).

## What Was Built

### Math Functions — `services/stake/parser/math.py`

All 7 new functions are pure Python with no I/O, no LLM imports (ARCH-01 compliant):

| Function | Purpose |
|---|---|
| `no_vig_probability` | Remove bookmaker margin: `implied_prob / overround` |
| `expected_value` | EV of a bet: `ai_prob * decimal_odds - 1` |
| `kelly_fraction` | Full Kelly fraction, clamped to 0.0 for -EV bets |
| `bet_size_usdt` | Quarter-Kelly sizing with 3% cap and 1 USDT minimum |
| `apply_portfolio_caps` | Enforce max 2 win bets and 5% total exposure limit |
| `apply_sparsity_discount` | Halve bet size when research data is sparse |
| `place_bet_ev` | EV for place market using `place_odds` (not win_odds, per BET-07) |

### Pre-Skip Node — `services/stake/pipeline/nodes.py`

`pre_skip_check_node(state)` reads `overround_active` from pipeline state, computes margin as `(overround - 1) * 100`, and compares against `settings.sizing.skip_overround_threshold` (default 15%).

- **Margin > threshold**: returns `{skip_signal: True, skip_reason: str, skip_tier: 1}`
- **Margin <= threshold**: returns `{skip_signal: False}`
- **No overround data**: returns `{}` (no decision)

### Tests — `tests/stake/test_ev_kelly_math.py`

56 tests across 8 test classes covering:
- Normal cases from plan spec
- Edge cases (zero bankroll, zero probability, zero Kelly)
- Boundary conditions (exactly at threshold, exactly at minimum)
- Type checks and mutation-safety checks

## Verification

```
PYTHONPATH=. pytest tests/stake/test_ev_kelly_math.py -x -v
56 passed in 0.42s

PYTHONPATH=. pytest tests/stake/ -x -q
146 passed in 1.44s
```

## Commits

| Commit | Type | Description |
|---|---|---|
| 740e4f0 | test | Add failing tests (RED phase) — 56 tests |
| 54563b3 | feat | Implement all 7 functions + pre_skip_check_node (GREEN phase) |

## Deviations from Plan

None — plan executed exactly as written.

All must_haves verified:
- `no_vig_probability` divides implied prob by overround — confirmed
- `expected_value` returns positive when `ai_prob * odds > 1` — confirmed
- `kelly_fraction` returns 0.0 for negative EV — confirmed
- `bet_size_usdt` applies quarter-Kelly, 3% cap, 1 USDT min — confirmed
- `apply_portfolio_caps` enforces 5% total and max 2 win bets — confirmed
- `place_bet_ev` uses `place_odds` not win_odds — confirmed
- `pre_skip_check_node` sets `skip_signal=True` when margin > threshold — confirmed

## Known Stubs

None — all functions are fully implemented with real math logic.

## Self-Check: PASSED
