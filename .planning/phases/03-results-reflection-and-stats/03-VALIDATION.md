---
phase: 3
slug: results-reflection-and-stats
status: draft
nyquist_compliant: true
wave_0_complete: true
wave_0_justification: "Test files (test_results.py, test_reflection.py) are created inline by implementation tasks using TDD pattern. Plan 03-01 Task 1 creates test_results.py with TDD (tests written before implementation). Plan 03-01 Task 2a creates test_reflection.py. No separate Wave 0 plan needed."
created: 2026-03-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/stake/` directory |
| **Quick run command** | `PYTHONPATH=. pytest tests/stake/ -x -q --tb=short` |
| **Full suite command** | `PYTHONPATH=. pytest tests/stake/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=. pytest tests/stake/ -x -q --tb=short`
- **After every plan wave:** Run `PYTHONPATH=. pytest tests/stake/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Test File | Status |
|---------|------|------|-------------|-----------|-------------------|-----------|--------|
| 03-01-01 | 01 | 1 | RESULT-02 | unit (TDD) | `pytest tests/stake/test_results.py -x` | test_results.py | pending |
| 03-01-02a | 01 | 1 | RESULT-03, TRACK-01 | unit | `pytest tests/stake/test_results.py tests/stake/test_reflection.py -x` | test_results.py, test_reflection.py | pending |
| 03-01-02b | 01 | 1 | TRACK-01 | import | `python -c "from services.stake.callbacks import TrackingCB"` | N/A | pending |
| 03-02-01 | 02 | 2 | RESULT-01, RISK-01 | import+suite | `pytest tests/stake/ -x -q` | N/A | pending |
| 03-02-02 | 02 | 2 | RESULT-01, RESULT-02 | import+suite | `pytest tests/stake/ -x -q` | N/A | pending |
| 03-03-01 | 03 | 2 | REFLECT-01, REFLECT-02 | unit | `pytest tests/stake/test_reflection.py -x` | test_reflection.py | pending |
| 03-03-02 | 03 | 2 | REFLECT-03 | unit | `pytest tests/stake/test_reflection.py -x` | test_reflection.py | pending |
| 03-04-01 | 04 | 3 | REFLECT-03 | import+suite | `pytest tests/stake/ -x -q` | N/A | pending |
| 03-04-02 | 04 | 3 | STATS-01 | unit | `pytest tests/stake/test_results.py tests/stake/test_reflection.py -x` | test_results.py, test_reflection.py | pending |

*Status: pending / green / red / flaky*

---

## Test File Mapping

| Test File | Created By | Covers |
|-----------|------------|--------|
| `tests/stake/test_results.py` | 03-01 Task 1 (TDD), extended by 03-01 Task 2a, 03-04 Task 2 | Evaluator, BetOutcomesRepository, BankrollRepository peak/drawdown, stats |
| `tests/stake/test_reflection.py` | 03-01 Task 2a, extended by 03-03 Tasks 1-2, 03-04 Task 2 | LessonsRepository, ReflectionWriter, LessonExtractor, _build_lessons_block |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram inline keyboard for placed/tracked | TRACK-01 | Requires real Telegram interaction | Send recommendation, verify "Placed"/"Tracked" buttons appear, tap each |
| Ambiguity clarification flow | RESULT-01 | Requires multi-turn FSM interaction | Submit ambiguous result text, verify bot asks for clarification |
| SKIP (drawdown protection) message display | RISK-01 | Visual verification of message format | Trigger drawdown, submit new race, verify SKIP message shown |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered: test files created inline by TDD tasks (no separate Wave 0 needed)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
