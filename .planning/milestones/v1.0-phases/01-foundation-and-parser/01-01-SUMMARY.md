---
phase: 01-foundation-and-parser
plan: 01
subsystem: testing
tags: [pydantic, pytest, odds-math, models, tdd]

# Dependency graph
requires: []
provides:
  - services/stake/parser/models.py — ParsedRace, RunnerInfo, MarketContext Pydantic models
  - services/stake/parser/math.py — to_decimal, implied_probability, overround, recalculate_without_scratches, odds_drift_pct
  - tests/stake/ — pytest infrastructure with 37 unit tests
affects:
  - 01-02 (stake parser — uses ParsedRace/RunnerInfo models and math functions)
  - all downstream stake-advisor plans (depend on these contracts)

# Tech tracking
tech-stack:
  added: [pytest>=7.0.0]
  patterns: [TDD red-green, Pydantic BaseModel with Literal type validation, pure-function math layer]

key-files:
  created:
    - services/stake/parser/models.py
    - services/stake/parser/math.py
    - services/stake/parser/__init__.py
    - services/stake/__init__.py
    - tests/stake/test_odds.py
    - tests/stake/conftest.py
    - tests/stake/__init__.py
  modified:
    - requirements.txt

key-decisions:
  - "to_decimal signature uses (fmt, odds_value) order — format first for readability in call sites"
  - "recalculate_without_scratches raises ValueError for no active runners — fail-fast, no silent empty results"
  - "odds_drift_pct returns None when either input is None — not 0.0, to preserve unknown-vs-zero semantics"

patterns-established:
  - "Pure math functions: no I/O, no side effects — all odds functions are stateless and testable in isolation"
  - "Pydantic Optional-first: all fields optional except identity fields (number, name on RunnerInfo) to handle partial Stake.com paste data"
  - "pytest.approx with abs tolerance for rounded floats — functions round to known decimal places, tests match that rounding"

requirements-completed: [PARSE-05, PARSE-06]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 01 Plan 01: Foundation and Parser Summary

**Pydantic data contracts (ParsedRace, RunnerInfo, MarketContext) and pure Python odds math (to_decimal, overround, Kelly-ready functions) with 37 passing pytest tests establishing the deterministic math layer.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-24T06:01:45Z
- **Completed:** 2026-03-24T06:05:52Z
- **Tasks:** 1
- **Files modified:** 8

## Accomplishments
- ParsedRace, RunnerInfo, MarketContext Pydantic models with full field definitions per D-07/D-08
- Deterministic odds math layer: to_decimal (decimal/fractional/American), implied_probability, overround, recalculate_without_scratches, odds_drift_pct
- pytest infrastructure with conftest.py fixtures and 37 unit tests covering all behaviors
- Scratched runner exclusion tested and verified
- All acceptance criteria met: 10/10 checks pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Pydantic models and deterministic odds math with tests** - `ce14fe7` (feat)

_Note: TDD tasks — tests written first (RED), then implementation (GREEN), single commit capturing all deliverables._

## Files Created/Modified
- `services/stake/parser/models.py` — ParsedRace, RunnerInfo, MarketContext Pydantic models
- `services/stake/parser/math.py` — to_decimal, implied_probability, overround, recalculate_without_scratches, odds_drift_pct
- `services/stake/parser/__init__.py` — package init (empty)
- `services/stake/__init__.py` — package init (empty)
- `tests/stake/test_odds.py` — 37 unit tests covering all math functions and model validation
- `tests/stake/conftest.py` — sample_runners and sample_parsed_race fixtures
- `tests/stake/__init__.py` — package init (empty)
- `requirements.txt` — added pytest>=7.0.0

## Decisions Made
- `to_decimal` signature is `(fmt, odds_value)` — format first makes call sites read naturally (`to_decimal("fractional", "5/2")`)
- `recalculate_without_scratches` raises `ValueError` for all-scratched case — fail-fast is correct; a race with no active runners is a data error upstream
- `odds_drift_pct` returns `None` not `0.0` when inputs are None — preserves distinction between "no drift" and "drift unknown"

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion tolerance mismatch for rounded float**
- **Found during:** Task 1 (GREEN phase — running tests)
- **Issue:** `test_odds_drift_pct_negative_drift` used `rel=1e-4` tolerance but `odds_drift_pct` rounds to 2 decimal places (`-16.67`), causing `pytest.approx` mismatch
- **Fix:** Changed assertion to `pytest.approx(-16.67, abs=1e-4)` to match the function's explicit rounding contract
- **Files modified:** tests/stake/test_odds.py
- **Verification:** 37/37 tests pass
- **Committed in:** ce14fe7 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test assertion precision)
**Impact on plan:** Single test assertion correction; no behavior change, no scope creep.

## Issues Encountered
- pytest not installed in venv — installed via `pip install pytest` as part of plan execution (this was expected per the task's action block)
- Worktree has no local venv — used main repo's `venv/` which has all required packages (pydantic already installed)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All data contracts established: ParsedRace, RunnerInfo, MarketContext ready for parser plan (01-02)
- Math layer fully tested: ready for integration into Kelly sizing and overround calculations
- pytest infrastructure in place for all subsequent TDD plans in this phase

---
*Phase: 01-foundation-and-parser*
*Completed: 2026-03-24*
