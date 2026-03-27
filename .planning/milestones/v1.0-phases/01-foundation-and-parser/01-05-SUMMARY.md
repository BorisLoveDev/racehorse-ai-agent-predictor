---
phase: 01-foundation-and-parser
plan: 05
subsystem: pipeline
tags: [langgraph, aiogram, fsm, telegram, audit-logging, odds-math]

# Dependency graph
requires:
  - phase: 01-foundation-and-parser plan 01
    provides: ParsedRace model, RunnerInfo, odds math functions
  - phase: 01-foundation-and-parser plan 02
    provides: BankrollRepository, StakeSettings with audit.log_path
  - phase: 01-foundation-and-parser plan 03
    provides: StakeParser.parse() LLM extraction
  - phase: 01-foundation-and-parser plan 04
    provides: PipelineStates FSM, ConfirmCB/BankrollCB callbacks, keyboard builders, main.py entry point

provides:
  - LangGraph StateGraph pipeline (parse -> calc nodes) with ambiguity detection
  - PipelineState TypedDict shared state object
  - format_race_summary() HTML formatter with overround + runner table + ambiguous warnings
  - AuditLogger append-only JSONL audit trail per D-27/D-28
  - pipeline.py: INPUT-01 text paste, INPUT-02 .txt doc, PIPELINE-02 clarification handlers
  - callbacks.py: ConfirmCB and BankrollCB handlers with stake % guidance (D-16)
  - main.py: all routers registered (commands -> callbacks -> pipeline)
  - 9 unit tests covering all FSM state transitions

affects: [02-research-and-analysis, future phases using pipeline state]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LangGraph StateGraph with TypedDict state, conditional edge error routing"
    - "Partial update dicts from each node — LangGraph merges into running state"
    - "Ambiguity detection in parse_node: runner count mismatch, missing odds threshold, unknown track"
    - "Audit log as append-only JSONL: one event per line, default=str for non-JSON types"
    - "Catch-all F.text handler registered LAST in router order"

key-files:
  created:
    - services/stake/pipeline/__init__.py
    - services/stake/pipeline/state.py
    - services/stake/pipeline/nodes.py
    - services/stake/pipeline/graph.py
    - services/stake/pipeline/formatter.py
    - services/stake/audit/__init__.py
    - services/stake/audit/logger.py
    - services/stake/handlers/pipeline.py
    - services/stake/handlers/callbacks.py
    - tests/stake/test_pipeline_handlers.py
  modified:
    - services/stake/main.py

key-decisions:
  - "Pipeline node returns partial update dict — LangGraph merges, preserving prior fields. No full state copy needed."
  - "ambiguous_fields uses string codes (runner_count_mismatch, missing_odds, track) not human text — handlers map to user-facing questions"
  - "Tests import from pipeline.py/callbacks.py directly — required Task 3 to be done before Task 2 tests ran, so all three tasks' files created before final test run"
  - "handle_paste_no_state catches F.text globally (no state filter) and defers to active-state handlers for clarification/bankroll_input states to avoid intercepting them"

patterns-established:
  - "Pipeline pattern: LangGraph StateGraph for parse/calc, FSM for Telegram flow — cleanly separated"
  - "Audit pattern: AuditLogger().log_entry(event, data) called at every decision point"
  - "Router order: commands -> callbacks -> pipeline (catch-all last)"

requirements-completed: [PARSE-04, BANK-02, BANK-03, BANK-04, PIPELINE-01, PIPELINE-02, PIPELINE-05, AUDIT-01]

# Metrics
duration: 5min
completed: 2026-03-24
---

# Phase 01 Plan 05: Pipeline Handlers and Audit Logging Summary

**LangGraph parse pipeline wired to Telegram FSM: text/doc input → LLM parse → ambiguity check → race summary confirm → bankroll detect/set → JSONL audit trail**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-24T06:19:23Z
- **Completed:** 2026-03-24T06:24:15Z
- **Tasks:** 3
- **Files modified:** 11 (10 created, 1 modified)

## Accomplishments

- LangGraph StateGraph pipeline with parse_node (LLM + ambiguity detection) and calc_node (odds math), error routing via conditional edge
- Full Telegram pipeline flow: paste/doc input → progress message → parse → clarification if ambiguous (PIPELINE-02) → race summary confirm → bankroll detect/set with stake % (D-16)
- Append-only JSONL audit logger logging every pipeline event (pipeline_start, parse_complete, user_confirmed, clarification_asked, bankroll_set, etc.)
- 9 unit tests covering all 9 FSM state transition paths, all passing

## Task Commits

1. **Task 1: Create LangGraph pipeline core** - `a84e570` (feat)
2. **Task 2: Create formatter, audit logger, and tests** - `4600528` (feat)
3. **Task 3: Create pipeline/callback handlers and wire into main.py** - `e55090f` (feat)

## Files Created/Modified

- `services/stake/pipeline/state.py` — PipelineState TypedDict with ambiguous_fields
- `services/stake/pipeline/nodes.py` — parse_node (LLM + ambiguity detection) and calc_node (odds math)
- `services/stake/pipeline/graph.py` — build_pipeline_graph() StateGraph
- `services/stake/pipeline/formatter.py` — format_race_summary() HTML with overround + runner table
- `services/stake/audit/logger.py` — AuditLogger append-only JSONL
- `services/stake/handlers/pipeline.py` — handle_paste, handle_document, handle_clarification, handle_bankroll_input
- `services/stake/handlers/callbacks.py` — handle_parse_confirm (ConfirmCB), handle_bankroll_action (BankrollCB)
- `services/stake/main.py` — added callbacks_router and pipeline_router registrations
- `tests/stake/test_pipeline_handlers.py` — 9 FSM state transition tests

## Decisions Made

- Pipeline node returns partial update dict — LangGraph merges, preserving prior fields. No full state copy needed.
- `ambiguous_fields` uses string codes (`runner_count_mismatch`, `missing_odds`, `track`) not human text — handlers map to user-facing questions dynamically.
- Tests require Task 3 files (pipeline.py, callbacks.py) before running — all three tasks' files were created before final test run to avoid false failures.
- `handle_paste_no_state` (global F.text handler) defers to active-state handlers for `awaiting_clarification` and `awaiting_bankroll_input` states to avoid intercepting them mid-flow.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None. The pipeline is fully wired for Phase 1 scope. The completion message after parse confirm says "Analysis pipeline will be available in Phase 2" — this is intentional, not a stub, as Phase 2 plans cover the analysis step.

## Next Phase Readiness

- Full paste-to-confirmation pipeline operational
- All foundation pieces connected: LLM parse → odds math → bankroll → audit trail → Telegram FSM
- Phase 2 (analysis) can build on `pipeline_result` in FSM state data, which already contains parsed race, enriched runners, and overround
- Blockers from STATE.md still apply: Stake.com paste format unknown until real data tested

---
*Phase: 01-foundation-and-parser*
*Completed: 2026-03-24*

## Self-Check: PASSED

Files verified:
- FOUND: services/stake/pipeline/__init__.py
- FOUND: services/stake/pipeline/state.py
- FOUND: services/stake/pipeline/nodes.py
- FOUND: services/stake/pipeline/graph.py
- FOUND: services/stake/pipeline/formatter.py
- FOUND: services/stake/audit/__init__.py
- FOUND: services/stake/audit/logger.py
- FOUND: services/stake/handlers/pipeline.py
- FOUND: services/stake/handlers/callbacks.py
- FOUND: tests/stake/test_pipeline_handlers.py
- FOUND: services/stake/main.py

Commits verified:
- FOUND: a84e570 (Task 1 — pipeline core)
- FOUND: 4600528 (Task 2 — formatter, audit, tests)
- FOUND: e55090f (Task 3 — handlers, main.py)
