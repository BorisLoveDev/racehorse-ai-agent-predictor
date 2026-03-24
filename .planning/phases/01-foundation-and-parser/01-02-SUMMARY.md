---
phase: 01-foundation-and-parser
plan: 02
subsystem: database, config
tags: [pydantic-settings, sqlite, bankroll, configuration, python]

# Dependency graph
requires: []
provides:
  - StakeSettings configuration with STAKE_ prefix and nested env var support
  - BankrollRepository with SQLite-backed singleton row for balance and stake_pct
  - stake_bankroll and stake_pipeline_runs table migrations
  - get_stake_settings() singleton factory function
affects:
  - All subsequent stake plans (use BankrollRepository for BANK-02, BET-01, BET-03)
  - Parser plan (uses StakeSettings.parser.model for model selection)
  - Telegram service (uses StakeSettings.telegram_bot_token)
  - Pipeline plan (uses StakeSettings.redis.url for FSM storage)

# Tech tracking
tech-stack:
  added:
    - pydantic-settings (already installed, pattern extended to Stake service)
  patterns:
    - BaseModel for nested config classes (NOT BaseSettings) — required for env_nested_delimiter to work
    - Singleton bankroll row pattern via CHECK (id = 1) + ON CONFLICT DO UPDATE upsert
    - Repository auto-runs migrations on __init__
    - TDD: failing tests committed before implementation

key-files:
  created:
    - services/stake/__init__.py
    - services/stake/settings.py
    - services/stake/bankroll/__init__.py
    - services/stake/bankroll/migrations.py
    - services/stake/bankroll/repository.py
    - tests/stake/__init__.py
    - tests/stake/test_settings.py
    - tests/stake/test_bankroll.py
  modified: []

key-decisions:
  - "Nested Pydantic config classes extend BaseModel not BaseSettings — BaseSettings nested classes each try to load env vars independently, breaking env_nested_delimiter. BaseModel delegates to parent's prefix logic."
  - "BankrollRepository.set_balance uses read-then-write to preserve stake_pct when only updating balance — simpler than ON CONFLICT partial update"
  - "get_stake_settings uses lru_cache singleton — matches existing get_settings() pattern in src/config/settings.py"

patterns-established:
  - "StakeSettings pattern: BaseSettings root with BaseModel nested classes, STAKE_ prefix, __ delimiter"
  - "Repository singleton row: CHECK (id = 1) table constraint + upsert on write"
  - "Auto-migration on init: run_stake_migrations called in BankrollRepository.__init__"

requirements-completed: [PARSE-02, BANK-01, BANK-05, PIPELINE-04]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 01 Plan 02: Config and Bankroll Persistence Summary

**StakeSettings Pydantic config with STAKE_ env prefix + SQLite bankroll repository using singleton row pattern, with 22 passing tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-24T06:02:48Z
- **Completed:** 2026-03-24T06:06:50Z
- **Tasks:** 2 (each with TDD RED/GREEN cycles)
- **Files modified:** 8 (all created)

## Accomplishments
- StakeSettings loads parser model, Redis URL, bankroll defaults, and audit path from STAKE_-prefixed env vars; STAKE_PARSER__MODEL correctly overrides parser.model via nested delimiter
- BankrollRepository persists balance and stake_pct to SQLite singleton row, survives restarts, and auto-runs migrations on init
- 22 tests covering defaults, env overrides, singleton constraint, CRUD operations, cross-instance persistence, and schema correctness

## Task Commits

Each task was committed atomically with TDD pattern (test → feat):

1. **Task 1 RED: StakeSettings tests** - `62057c9` (test)
2. **Task 1 GREEN: StakeSettings implementation** - `8b863f4` (feat)
3. **Task 2 RED: BankrollRepository tests** - `e763c7d` (test)
4. **Task 2 GREEN: BankrollRepository + migrations** - `a8b9d10` (feat)

_TDD tasks have multiple commits per task (test → feat)_

## Files Created/Modified
- `services/stake/__init__.py` - Package init for stake service
- `services/stake/settings.py` - StakeSettings (BaseSettings root) with ParserSettings, RedisSettings, BankrollSettings, AuditSettings (all BaseModel); get_stake_settings() singleton
- `services/stake/bankroll/__init__.py` - Package init
- `services/stake/bankroll/migrations.py` - run_stake_migrations() creates stake_bankroll (singleton row) and stake_pipeline_runs tables
- `services/stake/bankroll/repository.py` - BankrollRepository with get_balance, set_balance, get_stake_pct, set_stake_pct
- `tests/stake/__init__.py` - Test package init
- `tests/stake/test_settings.py` - 9 tests for StakeSettings
- `tests/stake/test_bankroll.py` - 13 tests for BankrollRepository and migrations

## Decisions Made
- Nested Pydantic config classes extend `BaseModel` not `BaseSettings` — if nested classes were `BaseSettings`, each independently loads env vars, breaking the `STAKE_PARSER__MODEL` → `parser.model` mapping. `BaseModel` delegates to parent's prefix/delimiter.
- `BankrollRepository.set_balance` uses read-before-write to preserve `stake_pct` when only the balance changes, rather than a partial `ON CONFLICT` update which SQLite handles less cleanly when the row may not exist.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - pytest was not installed in the venv and was added as a prerequisite (Rule 3 - blocking), which is expected for a fresh environment.

## User Setup Required

None - no external service configuration required. SQLite and pydantic-settings are existing dependencies.

## Next Phase Readiness
- StakeSettings ready for use in parser (PARSE-01/02), Telegram bot, and FSM storage
- BankrollRepository ready for BANK-02 (auto-extraction from dialog), BET-01 (Kelly sizing)
- stake_pipeline_runs table ready for pipeline run logging (PIPELINE-01 through PIPELINE-04)

---
*Phase: 01-foundation-and-parser*
*Completed: 2026-03-24*
