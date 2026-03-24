---
phase: 01-foundation-and-parser
plan: 03
subsystem: parsing
tags: [langchain, openrouter, pydantic, llm, structured-output, pytest-asyncio]

requires:
  - phase: 01-foundation-and-parser
    plan: 01
    provides: "ParsedRace, RunnerInfo, MarketContext Pydantic models"
  - phase: 01-foundation-and-parser
    plan: 02
    provides: "StakeSettings with parser.model, temperature, max_tokens config"
provides:
  - "PARSE_SYSTEM_PROMPT covering all D-07 fields, D-08 null handling, D-10 scratches, PARSE-03 bankroll"
  - "StakeParser class using ChatOpenAI.with_structured_output(ParsedRace)"
  - "parse_race_text() convenience function"
  - "16 mocked unit tests covering init, parse, bankroll, scratched runners, market context"
affects:
  - 01-04
  - pipeline integration
  - web research step

tech-stack:
  added:
    - pytest-asyncio>=0.21.0 (async test support)
    - pytest.ini with asyncio_mode=auto
  patterns:
    - ChatOpenAI.with_structured_output(ParsedRace) — typed LLM extraction returning Pydantic model directly
    - SystemMessage + HumanMessage pattern for structured extraction prompts
    - Mocked async chain tests using AsyncMock + patch("module.ChatOpenAI")

key-files:
  created:
    - services/stake/parser/prompt.py
    - services/stake/parser/llm_parser.py
    - tests/stake/test_parser.py
    - pytest.ini
  modified:
    - requirements.txt (added pytest-asyncio)

key-decisions:
  - "PARSE_SYSTEM_PROMPT includes explicit odds conversion instructions — LLM converts fractional/american to decimal before storing, records original format in win_odds_format"
  - "Chain built once in __init__ via with_structured_output — not rebuilt per call, avoids repeated overhead"
  - "parse_race_text() creates a fresh StakeParser per call — avoids settings singleton issues in tests"

patterns-established:
  - "LLM extraction via with_structured_output returns typed Pydantic model — no JSON parsing needed"
  - "Mock pattern: patch ChatOpenAI at import path, set mock_instance.with_structured_output.return_value = AsyncMock"

requirements-completed: [PARSE-01, PARSE-03, PARSE-04]

duration: 12min
completed: 2026-03-24
---

# Phase 01 Plan 03: LLM Parser Summary

**ChatOpenAI.with_structured_output(ParsedRace) parser using OpenRouter, with comprehensive D-07 extraction prompt and 16 mocked tests covering bankroll detection and scratched runners**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-24T06:11:13Z
- **Completed:** 2026-03-24T06:23:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created `PARSE_SYSTEM_PROMPT` covering all D-07 race-level and per-runner fields, D-08 null handling, D-10 scratched detection, PARSE-03 bankroll extraction, and odds format detection
- Built `StakeParser` class wiring `ChatOpenAI.with_structured_output(ParsedRace)` against OpenRouter via configurable model from `StakeSettings.parser.model`
- Created 16 mocked tests — zero real API calls, all passing — covering init, parse, bankroll, scratched runners, market context, and convenience function

## Task Commits

1. **Task 1: Create LLM parser system prompt** - `9c84e06` (feat)
2. **Task 2: StakeParser class with structured output and mocked tests** - `f467cfb` (feat)

## Files Created/Modified

- `services/stake/parser/prompt.py` - PARSE_SYSTEM_PROMPT (6150 chars, all D-07 fields + bankroll/scratch/format rules)
- `services/stake/parser/llm_parser.py` - StakeParser class and parse_race_text() convenience function
- `tests/stake/test_parser.py` - 16 mocked unit tests (TestStakeParserInit, TestStakeParserParse, TestParseRaceTextFunction, TestMarketContextExtraction)
- `requirements.txt` - Added pytest-asyncio>=0.21.0
- `pytest.ini` - Added asyncio_mode=auto for pytest-asyncio

## Decisions Made

- `PARSE_SYSTEM_PROMPT` includes explicit in-prompt odds conversion — LLM converts fractional/american to decimal, records original format in `win_odds_format`. This keeps the parser self-contained without downstream format-switching logic.
- `chain` built once in `__init__` — avoids rebuilding structured output wrapper per parse call.
- `parse_race_text()` creates a fresh `StakeParser` instance per call — avoids test isolation issues with cached singletons.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing pytest-asyncio and configured asyncio_mode**
- **Found during:** Task 2 (running parser tests)
- **Issue:** Async tests using `@pytest.mark.asyncio` failed with "async def functions are not natively supported" — pytest-asyncio not installed
- **Fix:** Installed pytest-asyncio 1.3.0, added `pytest.ini` with `asyncio_mode = auto`, added `pytest-asyncio>=0.21.0` to requirements.txt
- **Files modified:** requirements.txt, pytest.ini (new)
- **Verification:** All 75 stake tests pass including 16 new async tests
- **Committed in:** f467cfb (Task 2 commit)

**2. [Rule 3 - Blocking] Merged main branch to get stake service files from plans 01 and 02**
- **Found during:** Plan start (loading context)
- **Issue:** Worktree was based on old main (pre plans 01/02 merge) — services/stake/ did not exist
- **Fix:** `git merge main` to fast-forward worktree branch to include committed work from parallel agents
- **Files modified:** All files from plans 01 and 02 (fast-forward, no conflicts)
- **Verification:** services/stake/parser/models.py and services/stake/settings.py present after merge

---

**Total deviations:** 2 auto-fixed (both blocking)
**Impact on plan:** Both essential to execute the plan. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Known Stubs

None — parser is wired to real ChatOpenAI.with_structured_output(ParsedRace) using configurable model. No hardcoded empty values or placeholder returns.

## Next Phase Readiness

- StakeParser ready for integration into the pipeline (Plan 04 onwards)
- `parse_race_text(raw_text)` is the public API — accepts raw string, returns `ParsedRace`
- Model configurable via `STAKE_PARSER__MODEL` env var
- Tests require `pytest-asyncio` (now in requirements.txt and pytest.ini)

## Self-Check: PASSED

- FOUND: services/stake/parser/prompt.py
- FOUND: services/stake/parser/llm_parser.py
- FOUND: tests/stake/test_parser.py
- FOUND: 01-03-SUMMARY.md
- FOUND: commit 9c84e06
- FOUND: commit f467cfb

---
*Phase: 01-foundation-and-parser*
*Completed: 2026-03-24*
