---
phase: 3
slug: results-reflection-and-stats
status: draft
nyquist_compliant: false
wave_0_complete: false
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | RESULT-01 | unit | `pytest tests/stake/test_result_parser.py -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | RESULT-02 | unit | `pytest tests/stake/test_bet_evaluation.py -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | RESULT-03 | unit | `pytest tests/stake/test_bet_outcomes.py -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | TRACK-01 | unit | `pytest tests/stake/test_placed_tracked.py -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | REFLECT-01 | unit | `pytest tests/stake/test_reflection.py -x` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03 | 2 | REFLECT-02, REFLECT-03 | unit | `pytest tests/stake/test_lessons.py -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 2 | STATS-01 | unit | `pytest tests/stake/test_stats.py -x` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 1 | RISK-01 | unit | `pytest tests/stake/test_drawdown.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/stake/test_result_parser.py` — stubs for RESULT-01 (flexible text parsing, ambiguity detection)
- [ ] `tests/stake/test_bet_evaluation.py` — stubs for RESULT-02 (bet evaluation against results)
- [ ] `tests/stake/test_bet_outcomes.py` — stubs for RESULT-03 (P&L breakdown display)
- [ ] `tests/stake/test_placed_tracked.py` — stubs for TRACK-01 (placed/tracked distinction)
- [ ] `tests/stake/test_reflection.py` — stubs for REFLECT-01 (mindset.md reflection writing)
- [ ] `tests/stake/test_lessons.py` — stubs for REFLECT-02, REFLECT-03 (lesson extraction, injection)
- [ ] `tests/stake/test_stats.py` — stubs for STATS-01 (P&L stats command)
- [ ] `tests/stake/test_drawdown.py` — stubs for RISK-01 (drawdown circuit breaker)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram inline keyboard for placed/tracked | TRACK-01 | Requires real Telegram interaction | Send recommendation, verify "Placed"/"Tracked" buttons appear, tap each |
| Ambiguity clarification flow | RESULT-01 | Requires multi-turn FSM interaction | Submit ambiguous result text, verify bot asks for clarification |
| SKIP (drawdown protection) message display | RISK-01 | Visual verification of message format | Trigger drawdown, submit new race, verify SKIP message shown |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
