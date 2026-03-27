---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Milestone complete
stopped_at: Completed 03-04-PLAN.md
last_updated: "2026-03-27T16:00:00.000Z"
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 14
  completed_plans: 14
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.
**Current focus:** Phase 03 — results-reflection-and-stats

## Current Position

Phase: 03
Plan: Not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 4 | 1 tasks | 8 files |
| Phase 01 P02 | 4 | 2 tasks | 8 files |
| Phase 01 P04 | 8 | 2 tasks | 7 files |
| Phase 01 P03 | 12 | 2 tasks | 5 files |
| Phase 01 P05 | 5 | 3 tasks | 11 files |
| Phase 01 P06 | 5 | 1 tasks | 3 files |
| Phase 02 P01 | 123 | 2 tasks | 5 files |
| Phase 02 P02 | 2 | 1 tasks | 3 files |
| Phase 02 P03 | 3 | 2 tasks | 6 files |
| Phase 02-ev-engine-and-analysis P04 | 15 | 3 tasks | 6 files |
| Phase 03 P01 | 375 | 3 tasks | 14 files |
| Phase 03 P03 | 2 | 2 tasks | 3 files |
| Phase 03 P02 | 308 | 2 tasks | 8 files |
| Phase 03 P04 | 20 | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: LangGraph chosen as framework — already installed, zero migration cost, supports dual pipeline/agent mode. PydanticAI rejected (splits codebase, no user-visible gain).
- [Init]: Pipeline-first, agent-mode v2 — hybrid code harder to debug than either pure form. AGENT-01 deferred.
- [Init]: SearXNG as default search — already running on Meridian, free, no API key needed.
- [Init]: PARSE-01 is highest-risk step — Stake.com paste format unknown until real data. Plan one iteration cycle with real paste before treating as done.
- [Phase 01]: to_decimal uses (fmt, odds_value) signature — format first for readability
- [Phase 01]: recalculate_without_scratches raises ValueError for no active runners — fail-fast over silent empty
- [Phase 01]: odds_drift_pct returns None (not 0.0) when inputs are None — unknown-vs-zero semantics
- [Phase 01]: Nested Pydantic config classes extend BaseModel not BaseSettings — BaseSettings nested classes each try to load env vars independently, breaking env_nested_delimiter. BaseModel delegates to parent's prefix logic.
- [Phase 01]: BankrollRepository.set_balance uses read-then-write to preserve stake_pct when only updating balance, avoiding partial ON CONFLICT complexity.
- [Phase 01]: MenuCB prefix 'sm' (not 'm') to avoid collision with existing telegram service MenuCB which uses 'm'
- [Phase 01]: bankroll_input_kb added beyond plan spec for Plan 05 awaiting_bankroll_input state handlers
- [Phase 01]: PARSE_SYSTEM_PROMPT includes explicit odds conversion — LLM converts fractional/american to decimal, records original format in win_odds_format field
- [Phase 01]: ChatOpenAI.with_structured_output chain built once in __init__ — not rebuilt per parse call to avoid overhead
- [Phase 01]: Pipeline node returns partial update dict — LangGraph merges, preserving prior fields
- [Phase 01]: ambiguous_fields uses string codes not human text — handlers map to user-facing questions dynamically
- [Phase 02]: TypedDict uses dict fields (not Pydantic models) for research_results, analysis_result, final_bets — Redis FSM requires JSON-serialisable types; model_dump() at write, model_validate() at read
- [Phase 02]: SizingSettings extends BaseModel (not BaseSettings) — consistent with Phase 1 pattern to avoid env loading issues with nested BaseSettings
- [Phase 02]: ResearchSettings.provider defaults to 'online' (OpenRouter) not 'searxng' — simpler dependency, no local server needed for development
- [Phase 02]: kelly_fraction clamps to 0.0 for breakeven EV (<=0) — no bet at zero edge
- [Phase 02]: pre_skip_check_node uses strict > comparison for threshold — exactly-at-threshold races proceed
- [Phase 02]: ResearchPlan/SearchQuery as internal Pydantic models for Phase 1 structured output — orchestrator plans into typed model before sub-agents execute
- [Phase 02]: Three-phase research_node: plan (ResearchPlan) -> execute (sub-agents) -> synthesize (ResearchOutput) — two separate orchestrator LLM calls for clean typed outputs
- [Phase 02-ev-engine-and-analysis]: ARCH-01 split: analysis_node calls LLM with pre-computed no-vig probabilities; sizing_node is pure Python — LLM never generates bet amounts
- [Phase 02-ev-engine-and-analysis]: build_analysis_graph() is a separate compiled graph from build_pipeline_graph() — parse and analysis pipelines are independent, chained via FSM state
- [Phase 03]: evaluate_bets marks place bets evaluable=False on partial results while keeping win bets evaluable
- [Phase 03]: set_balance auto-calls update_peak_if_higher to ensure peak tracking without extra caller burden
- [Phase 03]: LessonExtractor uses temperature=0.3 (lower than ReflectionWriter 0.7) for more consistent structured extraction
- [Phase 03]: mindset_path parent directory created at ReflectionWriter init (not at write time) — consistent with AuditLogger pattern
- [Phase 03]: drawdown_check_node fires as the first node in build_analysis_graph, before pre_skip_check — ensures no API credits are spent when circuit breaker is active
- [Phase 03]: awaiting_placed_tracked state only set when final_bets is non-empty and skip_signal is False — no tracking keyboard shown on skip/empty recommendation
- [Phase 03]: Reflection pipeline is non-blocking: try/except wraps writer+extractor, state transitions to idle BEFORE reflection to avoid blocking user if LLM is slow
- [Phase 03]: Lesson injection prepends lessons_block to analysis prompt so LLM reads learned context before race data
- [Phase 03]: /stats P&L display HTML-escapes ampersand as &amp; to avoid Telegram parse_mode=HTML silent failures

### Pending Todos

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260327-vxe | Fix drawdown_unlock_kb not attached to skip message | 2026-03-27 | 3eeab51 | [260327-vxe](./quick/260327-vxe-fix-drawdown-unlock-kb-not-attached-to-s/) |

### Blockers/Concerns

- [Phase 1]: Stake.com paste format is unknown — LLM extraction prompt may need tuning based on real data. Treat PARSE-01 as experimental; plan iteration cycle.
- [Phase 2]: Place bet terms on Stake.com not confirmed — parser must extract explicit place terms from paste; if absent, prompt user.
- [Phase 2]: Kelly sizing should not activate until 50+ resolved bets. Use flat 1% initially. Transition trigger needs specification during Phase 2 planning.

## Session Continuity

Last session: 2026-03-27T12:00:16.095Z
Stopped at: Completed 03-04-PLAN.md
Resume file: None
