---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
stopped_at: "Completed 01-06-PLAN.md Task 1, awaiting checkpoint:human-verify Task 2"
last_updated: "2026-03-24T06:29:16.552Z"
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.
**Current focus:** Phase 01 — foundation-and-parser

## Current Position

Phase: 01 (foundation-and-parser) — EXECUTING
Plan: 6 of 6

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Stake.com paste format is unknown — LLM extraction prompt may need tuning based on real data. Treat PARSE-01 as experimental; plan iteration cycle.
- [Phase 2]: Place bet terms on Stake.com not confirmed — parser must extract explicit place terms from paste; if absent, prompt user.
- [Phase 2]: Kelly sizing should not activate until 50+ resolved bets. Use flat 1% initially. Transition trigger needs specification during Phase 2 planning.

## Session Continuity

Last session: 2026-03-24T06:29:13.082Z
Stopped at: Completed 01-06-PLAN.md Task 1, awaiting checkpoint:human-verify Task 2
Resume file: None
