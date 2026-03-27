---
phase: 03-results-reflection-and-stats
plan: "02"
subsystem: result-submission-flow
tags: [handlers, fsm, result-parser, drawdown, keyboards, p-and-l, pipeline]
dependency_graph:
  requires:
    - 03-01 (ParsedResult, BetOutcome, BetOutcomesRepository, evaluator, bankroll peak/drawdown, TrackingCB/ResultCB/DrawdownCB, FSM states)
  provides:
    - services/stake/results/parser.py (ResultParser, RESULT_PARSE_SYSTEM_PROMPT)
    - services/stake/handlers/results.py (full result submission flow router)
    - services/stake/keyboards/stake_kb.py (tracking_kb, result_confirm_kb, drawdown_unlock_kb)
    - services/stake/pipeline/nodes.py (drawdown_check_node)
    - services/stake/pipeline/graph.py (drawdown_check as first node in analysis graph)
    - services/stake/handlers/commands.py (/unlock_drawdown command)
    - services/stake/main.py (results_router registered before pipeline_router)
  affects:
    - 03-03 (stats plan reads from stake_bet_outcomes table, populated here)
    - 03-04 (reflection plan reads FSM data: last_evaluated_outcomes, last_parsed_result)
tech_stack:
  added: []
  patterns:
    - ResultParser mirrors StakeParser pattern — ChatOpenAI.with_structured_output(ParsedResult)
    - drawdown_check_node as first graph node saves API cost on blocked sessions
    - FSM model_dump() pattern for Pydantic -> Redis serialization (CLAUDE.md)
    - html.escape() on all LLM-generated strings in Telegram HTML replies (CLAUDE.md)
    - Router registration order: results before pipeline (state-specific handlers take priority over catch-all)
key_files:
  created:
    - services/stake/results/parser.py
    - services/stake/handlers/results.py
  modified:
    - services/stake/pipeline/nodes.py
    - services/stake/pipeline/graph.py
    - services/stake/keyboards/stake_kb.py
    - services/stake/handlers/pipeline.py
    - services/stake/handlers/commands.py
    - services/stake/main.py
decisions:
  - "drawdown_check_node fires as the first node in build_analysis_graph, before pre_skip_check — ensures no API credits are spent when circuit breaker is active"
  - "ResultParser chain built once in __init__ (not per parse call) — consistent with StakeParser pattern"
  - "awaiting_placed_tracked state only set when final_bets is non-empty and skip_signal is False — no keyboard shown on skip/empty recommendation"
  - "run_id stored in FSM via sqlite3 INSERT after analysis completes — required for BetOutcomesRepository.save_outcomes foreign key"
metrics:
  duration_seconds: 308
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_created: 2
  files_modified: 6
---

# Phase 03 Plan 02: Result Submission Flow Summary

**One-liner:** LLM result parser, drawdown circuit breaker node, placed/tracked keyboard, full result submission FSM flow (TrackingCB -> awaiting_result -> parse -> confirm -> P&L evaluate -> bankroll update).

## What Was Built

Two tasks wiring the complete result submission flow on top of the data foundation from Plan 01.

**Task 1: Result parser, drawdown node, keyboards, pipeline modification**
- `ResultParser` in `services/stake/results/parser.py` — mirrors StakeParser pattern, uses cheap parser model, `.with_structured_output(ParsedResult)` for structured result extraction
- `drawdown_check_node` added to `services/stake/pipeline/nodes.py` — reads peak/current balance from BankrollRepository, fires `skip_signal=True` with `skip_tier=0` when drawdown >= threshold (configurable via `settings.risk.drawdown_threshold_pct`)
- `build_analysis_graph()` updated to use `drawdown_check_node` as the first node before `pre_skip_check_node` — drawdown check fires before any expensive LLM calls
- Three new keyboards in `stake_kb.py`: `tracking_kb()`, `result_confirm_kb()`, `drawdown_unlock_kb()`
- `_run_analysis_inline()` in `pipeline.py` modified to:
  - Insert a `stake_pipeline_runs` record and store `run_id` in FSM
  - Store `final_bets` in FSM data
  - Set `awaiting_placed_tracked` state and show `tracking_kb()` when bets are non-empty and no skip signal
  - Fall back to idle when bets are empty or skip was triggered

**Task 2: Result handlers, /unlock_drawdown command, router registration**
- `services/stake/handlers/results.py` — new router with 5 handlers:
  1. `TrackingCB` handler — stores `is_placed` choice, transitions to `awaiting_result`
  2. `awaiting_result` message handler — parses result text via `ResultParser`, routes to clarification (low confidence) or confirmation (high confidence)
  3. `awaiting_result_clarification` message handler — re-routes to awaiting_result for retry
  4. `ResultCB` handler — on confirm: evaluates bets via `evaluate_bets()`, saves outcomes, updates bankroll (if placed), calls `check_and_auto_reset_drawdown`, displays P&L summary
  5. `DrawdownCB` handler — sets `drawdown_unlocked=True` in SQLite
- `/unlock_drawdown` command added to `commands.py` — same effect as DrawdownCB handler
- `results_router` registered in `main.py` before `pipeline_router`

## Test Coverage

207 tests pass (all non-E2E). No new tests added for this plan (handler tests require mocking aiogram; the data layer tests from Plan 01 cover evaluator and repositories). E2E test remains pre-existing failure (requires OpenRouter API key).

## Deviations from Plan

None — plan executed exactly as written.

The plan specified a bare `sql INSERT` pattern in `_run_analysis_inline` for the run_id, which was implemented exactly as specified. The only minor difference is that `BankrollRepository` is imported as `_BR` alias to avoid name collision in the local scope.

## Known Stubs

None — all data flows are fully implemented. The result flow is wired end-to-end:
- `tracking_kb()` appears after real recommendations
- `ResultParser.parse()` calls the actual LLM
- `evaluate_bets()` is pure Python with real calculation
- `BetOutcomesRepository.save_outcomes()` writes to SQLite
- Bankroll is updated from real P&L figures

## Self-Check: PASSED

| Check | Status |
|-------|--------|
| services/stake/results/parser.py | FOUND |
| services/stake/handlers/results.py | FOUND |
| Commit 202f68a (Task 1) | FOUND |
| Commit 82b2944 (Task 2) | FOUND |
