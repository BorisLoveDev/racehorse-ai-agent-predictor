---
phase: 03-results-reflection-and-stats
plan: 04
subsystem: pipeline
tags: [reflection, lessons, stats, aiogram, langchain, sqlite]

requires:
  - phase: 03-01
    provides: LessonsRepository, BetOutcomesRepository with get_total_stats/get_period_stats
  - phase: 03-02
    provides: handle_result_confirm handler, BetOutcomesRepository, DrawdownCB
  - phase: 03-03
    provides: ReflectionWriter, LessonExtractor with write_reflection/extract_and_save

provides:
  - Reflection + lesson extraction wired into handle_result_confirm (non-blocking)
  - _build_lessons_block() injects top-5 rules and last-3 failures into analysis prompts
  - /stats command showing all-time, 30-day, 7-day P&L for placed bets
  - Audit log events reflection_complete and reflection_error with full metadata

affects: [future analysis runs benefit from lesson injection, deployment, REFLECT-03, STATS-01]

tech-stack:
  added: []
  patterns:
    - Non-blocking async try/except for LLM operations in result handlers
    - Lesson injection via prompt prepend (lessons_block + existing_prompt)
    - application_count increment on each lesson injection for frequency tracking

key-files:
  created: []
  modified:
    - services/stake/handlers/results.py
    - services/stake/pipeline/nodes.py
    - services/stake/handlers/commands.py
    - tests/stake/test_reflection.py
    - tests/stake/test_results.py

key-decisions:
  - "Reflection pipeline is non-blocking: try/except wraps writer+extractor, flow continues to idle even on LLM failure"
  - "State transition (set_state idle) happens BEFORE reflection to avoid blocking user if LLM is slow"
  - "Lesson injection prepends lessons_block to prompt so LLM reads context before race data"
  - "P&L display in /stats uses HTML-escaped &amp; for ampersand to avoid Telegram parse_mode=HTML failures"

patterns-established:
  - "Non-blocking LLM side-effects: wrap in try/except, log errors, never block primary flow"
  - "_build_lessons_block() is synchronous (DB reads only), called inside async analysis_node"

requirements-completed: [REFLECT-03, STATS-01, RESULT-03]

duration: 20min
completed: 2026-03-27
---

# Phase 03 Plan 04: Integration — Reflection Pipeline, Lesson Injection, /stats Summary

**Closed the feedback loop: reflection + lesson extraction run automatically after each result, lessons inject into the next race's analysis prompt, /stats shows all-time/30-day/7-day P&L for placed bets**

## Performance

- **Duration:** 20 min
- **Started:** 2026-03-27T12:00:00Z
- **Completed:** 2026-03-27T12:20:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Reflection pipeline integrated into handle_result_confirm: ReflectionWriter + LessonExtractor called automatically after every result evaluation, non-blocking
- Lesson injection wired into analysis_node via _build_lessons_block() querying top-5 rules and last-3 failure modes from SQLite, incrementing application_count on each injection
- /stats command added to commands.py (STATS-01): all-time, 30-day, and 7-day P&L views for placed bets with win rate and ROI
- Audit log extended with reflection_complete/reflection_error events including parsed_result data
- 3 new tests added: test_build_lessons_block_with_rules, test_build_lessons_block_empty_db, test_stats_placed_only

## Task Commits

1. **Task 1: Wire reflection pipeline into result handler and add lesson injection to analysis** - `012ee7b` (feat)
2. **Task 2: /stats command and lessons injection test** - `3be053f` (feat)

**Plan metadata:** (this summary commit)

## Files Created/Modified

- `services/stake/handlers/results.py` - Extended handle_result_confirm with reflection pipeline, audit events, lesson notification to user
- `services/stake/pipeline/nodes.py` - Added _build_lessons_block() and lesson injection in analysis_node
- `services/stake/handlers/commands.py` - Added cmd_stats /stats command handler
- `tests/stake/test_reflection.py` - Added test_build_lessons_block_with_rules, test_build_lessons_block_empty_db
- `tests/stake/test_results.py` - Added test_stats_placed_only

## Decisions Made

- Reflection pipeline is non-blocking: try/except wraps writer+extractor, flow continues to idle even on LLM failure. State transition to idle happens BEFORE reflection to avoid blocking the user if the LLM is slow or unavailable.
- Lesson injection prepends lessons_block to the prompt string so the LLM reads learned context before race data.
- P&L stats in /stats use HTML-escaped `&amp;` for ampersand to avoid Telegram parse_mode=HTML failures (per CLAUDE.md: unescaped `<>` or `&` in bot replies will silently fail).

## Deviations from Plan

None - plan executed exactly as written. The one minor adjustment: `state.set_state(PipelineStates.idle)` was placed before the reflection try/except block (rather than after as the plan pseudocode suggested) so the user isn't blocked waiting for LLM if reflection is slow.

## Issues Encountered

- The existing e2e test (test_e2e_pipeline.py::test_full_pipeline_end_to_end) fails with a 401 auth error because no real OpenRouter API key is present in the test environment. This is pre-existing behavior unrelated to this plan's changes. All 210 other tests pass.

## Next Phase Readiness

- Phase 3 is complete. All four plans executed.
- Full feedback loop operational: result -> reflection -> lesson saved -> injected into next race analysis
- /stats command live for user P&L visibility
- 210 tests passing

---
*Phase: 03-results-reflection-and-stats*
*Completed: 2026-03-27*
