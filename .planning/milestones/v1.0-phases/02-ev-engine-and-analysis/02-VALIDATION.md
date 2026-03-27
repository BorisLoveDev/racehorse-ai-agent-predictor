---
phase: 2
slug: ev-engine-and-analysis
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/stake/` (existing test directory) |
| **Quick run command** | `PYTHONPATH=. pytest tests/stake/ -x -q --timeout=10` |
| **Full suite command** | `PYTHONPATH=. pytest tests/stake/ -v --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=. pytest tests/stake/ -x -q --timeout=10`
- **After every plan wave:** Run `PYTHONPATH=. pytest tests/stake/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SEARCH-01 | unit | `pytest tests/stake/test_research_tools.py -k searxng` | TDD in 02-03 | pending |
| 02-01-02 | 01 | 1 | SEARCH-02 | unit | `pytest tests/stake/test_research_tools.py -k online_model` | TDD in 02-03 | pending |
| 02-02-01 | 02 | 2 | ANALYSIS-01 | unit | `pytest tests/stake/test_ev_kelly_math.py -k overround` | TDD in 02-02 | pending |
| 02-02-02 | 02 | 2 | ANALYSIS-02 | unit | `pytest tests/stake/test_ev_kelly_math.py -k ev_kelly` | TDD in 02-02 | pending |
| 02-02-03 | 02 | 2 | ANALYSIS-03 | unit | `pytest tests/stake/test_ev_kelly_math.py -k deterministic` | TDD in 02-02 | pending |
| 02-02-04 | 02 | 2 | ANALYSIS-04 | unit | `pytest tests/stake/test_ev_kelly_math.py -k margin_skip` | TDD in 02-02 | pending |
| 02-02-05 | 02 | 2 | ANALYSIS-05 | unit | `pytest tests/stake/test_ev_kelly_math.py -k discrepancy` | TDD in 02-02 | pending |
| 02-03-01 | 04 | 3 | BET-01 | unit | `pytest tests/stake/test_sizing_node.py -k quarter_kelly` | TDD in 02-04 | pending |
| 02-03-02 | 04 | 3 | BET-02 | unit | `pytest tests/stake/test_sizing_node.py -k per_bet_cap` | TDD in 02-04 | pending |
| 02-03-03 | 04 | 3 | BET-03 | unit | `pytest tests/stake/test_sizing_node.py -k race_exposure` | TDD in 02-04 | pending |
| 02-03-04 | 04 | 3 | BET-04 | unit | `pytest tests/stake/test_sizing_node.py -k max_win_bets` | TDD in 02-04 | pending |
| 02-03-05 | 04 | 3 | BET-05 | unit | `pytest tests/stake/test_sizing_node.py -k sparse_data` | TDD in 02-04 | pending |
| 02-03-06 | 04 | 3 | BET-06 | unit | `pytest tests/stake/test_sizing_node.py -k min_bet` | TDD in 02-04 | pending |
| 02-03-07 | 04 | 3 | BET-07 | unit | `pytest tests/stake/test_sizing_node.py -k recommendation` | TDD in 02-04 | pending |

*Status: pending | green | red | flaky*

---

## Wave 0 Strategy

Wave 0 test stubs are NOT needed as separate files. Each plan creates its own tests inline:

- **Plan 02-02** (type: tdd): Creates `tests/stake/test_ev_kelly_math.py` via RED-GREEN-REFACTOR cycle. Tests written BEFORE implementation.
- **Plan 02-03** (type: execute): Task 1 creates `tests/stake/test_research_tools.py` with mocked httpx/ChatOpenAI tests.
- **Plan 02-04** (type: execute): Task 1 creates `tests/stake/test_sizing_node.py` with sizing/portfolio cap tests.

All test files are created by TDD tasks or inline test tasks within their respective plans. No separate Wave 0 plan needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SearXNG returns racing data | SEARCH-01 | Requires live SearXNG instance | Send test query to `http://46.30.43.46:8888/search?q=horse+form&format=json`, verify results |
| AI labels runners correctly | ANALYSIS-02 | LLM output varies | Parse race, check each runner has one of: highest_win_probability, best_value, best_place_candidate, no_bet |
| End-to-end Telegram flow | BET-06 | Requires live bot + Telegram | Plan 02-04 Task 3 (checkpoint:human-verify) covers this |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or TDD-created test files
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered by TDD and inline test tasks (no separate stubs needed)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
