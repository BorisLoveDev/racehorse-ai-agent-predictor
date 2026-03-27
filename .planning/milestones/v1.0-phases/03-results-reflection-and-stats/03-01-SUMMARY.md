---
phase: 03-results-reflection-and-stats
plan: "01"
subsystem: results-foundation
tags: [models, evaluator, migrations, repositories, fsm, callbacks, p-and-l]
dependency_graph:
  requires: []
  provides:
    - services/stake/results/models.py (ParsedResult, BetOutcome, LessonEntry)
    - services/stake/results/evaluator.py (evaluate_bets)
    - services/stake/results/repository.py (BetOutcomesRepository)
    - services/stake/reflection/repository.py (LessonsRepository)
    - services/stake/bankroll/migrations.py (stake_bet_outcomes, stake_lessons tables)
    - services/stake/bankroll/repository.py (peak_balance + drawdown methods)
    - services/stake/settings.py (ReflectionSettings, RiskSettings)
    - services/stake/states.py (Phase 3 FSM states)
    - services/stake/callbacks.py (TrackingCB, ResultCB, DrawdownCB)
    - services/stake/pipeline/nodes.py (decimal_odds/place_odds in final_bets)
  affects:
    - All Phase 3 plans (03-02 through 03-04) depend on these models and tables
tech_stack:
  added: []
  patterns:
    - Pydantic BaseModel for result/outcome/lesson data contracts
    - Pure-Python P&L evaluator (ARCH-01 compliant — no LLM calls)
    - SQLite idempotent migrations with PRAGMA table_info column checks
    - Singleton row pattern extended with peak/drawdown columns
    - aiogram CallbackData with short prefixes for 64-byte Telegram limit
key_files:
  created:
    - services/stake/results/__init__.py
    - services/stake/results/models.py
    - services/stake/results/evaluator.py
    - services/stake/results/repository.py
    - services/stake/reflection/__init__.py
    - services/stake/reflection/repository.py
    - tests/stake/test_results.py
    - tests/stake/test_reflection.py
  modified:
    - services/stake/bankroll/migrations.py
    - services/stake/bankroll/repository.py
    - services/stake/settings.py
    - services/stake/states.py
    - services/stake/callbacks.py
    - services/stake/pipeline/nodes.py
decisions:
  - "evaluate_bets() handles partial results by marking place bets evaluable=False while keeping win bets evaluable — avoids incorrect P&L on incomplete data"
  - "get_recent_failures orders by created_at DESC, id DESC — guards against SQLite CURRENT_TIMESTAMP second-level precision giving same timestamp to same-second inserts"
  - "increment_application_count uses SQL IN (...) which deduplicates ids within a single call — callers must invoke once per application event, not pass duplicate ids in one call"
  - "set_balance auto-calls update_peak_if_higher to ensure peak is always updated without requiring callers to remember to do it"
metrics:
  duration_seconds: 375
  completed_date: "2026-03-27"
  tasks_completed: 3
  files_created: 8
  files_modified: 6
---

# Phase 03 Plan 01: Data Foundation for Results Tracking Summary

**One-liner:** Pure-Python P&L evaluator with Pydantic models, SQLite tables, CRUD repositories, bankroll peak/drawdown tracking, Phase 3 FSM states/callbacks, and odds gap fix in sizing_node.

## What Was Built

Three tasks creating the complete data foundation that all subsequent Phase 3 plans depend on.

**Task 1: Pydantic models, evaluator, and tests (TDD)**
- `ParsedResult` — structured race result (finishing_order, is_partial, confidence)
- `BetOutcome` — per-bet evaluation outcome (won, profit_usdt, evaluable flag)
- `LessonEntry` — extracted lesson from reflection (error_tag, rule_sentence, is_failure_mode)
- `evaluate_bets()` — pure-Python P&L calculator handling win/place/partial result cases per ARCH-01

**Task 2a: Migrations, repositories, settings**
- `stake_bet_outcomes` table for bet outcome persistence
- `stake_lessons` table for reflection-extracted rules
- `peak_balance_usdt` and `drawdown_unlocked` columns on `stake_bankroll` (idempotent ALTER TABLE via PRAGMA)
- `BetOutcomesRepository` with save/aggregate stats methods, placed vs tracked filtering
- `LessonsRepository` with save, top rules, recent failures, and application count tracking
- `BankrollRepository` extended with peak balance tracking and drawdown circuit breaker methods
- `ReflectionSettings` and `RiskSettings` added to `StakeSettings`

**Task 2b: FSM states, callbacks, odds fix**
- 4 new `PipelineStates`: `awaiting_placed_tracked`, `awaiting_result`, `awaiting_result_clarification`, `confirming_result`
- 3 new `CallbackData` classes: `TrackingCB` (st:), `ResultCB` (sr:), `DrawdownCB` (sd:)
- Fixed `sizing_node`: win bets now include `decimal_odds`, place bets include both `decimal_odds` and `place_odds` — required for P&L evaluation in downstream plans

## Test Coverage

- 14 unit tests for evaluator and Pydantic models (test_results.py initial)
- 11 repository and bankroll extension tests added to test_results.py
- 10 LessonsRepository tests in test_reflection.py
- Total: 35 new tests, all passing
- Full non-E2E suite: 197 tests pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite CURRENT_TIMESTAMP same-second precision in test**
- **Found during:** Task 2a test run
- **Issue:** `get_recent_failures` ordered by `created_at DESC` only; rows inserted in the same test second get identical timestamps, making ORDER BY nondeterministic
- **Fix:** Changed ORDER BY to `created_at DESC, id DESC` — id is always unique and monotonically increasing
- **Files modified:** services/stake/reflection/repository.py

**2. [Rule 2 - Missing functionality] `increment_application_count` test used duplicates in single call**
- **Found during:** Task 2a test run
- **Issue:** Test passed `[id2, id2, id2]` expecting count=3, but SQL `IN (...)` deduplicates; this was a test design issue revealing semantics mismatch
- **Fix:** Changed tests to call increment once per event; documented the semantics in decisions
- **Files modified:** tests/stake/test_reflection.py

**3. [Rule 2 - Missing functionality] `datetime.utcnow()` deprecation warning**
- **Found during:** Task 2a test run (DeprecationWarning)
- **Fix:** Replaced with `datetime.now(timezone.utc)` in repository.py
- **Files modified:** services/stake/results/repository.py

### Pre-existing Issue (out of scope)

`tests/stake/test_e2e_pipeline.py::test_full_pipeline_end_to_end` fails with 401 (missing OpenRouter API key in test environment). Confirmed pre-existing before this plan. Not caused by these changes. All 197 non-E2E tests pass.

## Known Stubs

None — all data flows are implemented. No placeholder values or TODO stubs in produced files.

## Self-Check: PASSED

| Check | Status |
|-------|--------|
| services/stake/results/models.py | FOUND |
| services/stake/results/evaluator.py | FOUND |
| services/stake/results/repository.py | FOUND |
| services/stake/reflection/repository.py | FOUND |
| tests/stake/test_results.py | FOUND |
| tests/stake/test_reflection.py | FOUND |
| Commit 9f61abc (Task 1) | FOUND |
| Commit 0230e6b (Task 2a) | FOUND |
| Commit 83a5d7a (Task 2b) | FOUND |
