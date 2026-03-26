---
phase: 2
slug: ev-engine-and-analysis
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 02-01-01 | 01 | 1 | SEARCH-01 | unit | `pytest tests/stake/test_research.py -k searxng` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | SEARCH-02 | unit | `pytest tests/stake/test_research.py -k online_model` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | ANALYSIS-01 | unit | `pytest tests/stake/test_ev_engine.py -k overround` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | ANALYSIS-02 | unit | `pytest tests/stake/test_ev_engine.py -k ev_kelly` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | ANALYSIS-03 | unit | `pytest tests/stake/test_ev_engine.py -k deterministic` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 1 | ANALYSIS-04 | unit | `pytest tests/stake/test_ev_engine.py -k margin_skip` | ❌ W0 | ⬜ pending |
| 02-02-05 | 02 | 1 | ANALYSIS-05 | unit | `pytest tests/stake/test_ev_engine.py -k discrepancy` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | BET-01 | unit | `pytest tests/stake/test_sizing.py -k quarter_kelly` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | BET-02 | unit | `pytest tests/stake/test_sizing.py -k per_bet_cap` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | BET-03 | unit | `pytest tests/stake/test_sizing.py -k race_exposure` | ❌ W0 | ⬜ pending |
| 02-03-04 | 03 | 2 | BET-04 | unit | `pytest tests/stake/test_sizing.py -k max_win_bets` | ❌ W0 | ⬜ pending |
| 02-03-05 | 03 | 2 | BET-05 | unit | `pytest tests/stake/test_sizing.py -k sparse_data` | ❌ W0 | ⬜ pending |
| 02-03-06 | 03 | 2 | BET-06 | unit | `pytest tests/stake/test_sizing.py -k min_bet` | ❌ W0 | ⬜ pending |
| 02-03-07 | 03 | 2 | BET-07 | unit | `pytest tests/stake/test_audit.py -k recommendation` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/stake/test_research.py` — stubs for SEARCH-01, SEARCH-02
- [ ] `tests/stake/test_ev_engine.py` — stubs for ANALYSIS-01 through ANALYSIS-05
- [ ] `tests/stake/test_sizing.py` — stubs for BET-01 through BET-06
- [ ] `tests/stake/test_audit.py` — stubs for BET-07

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SearXNG returns racing data | SEARCH-01 | Requires live SearXNG instance | Send test query to `http://46.30.43.46:8888/search?q=horse+form&format=json`, verify results |
| AI labels runners correctly | ANALYSIS-02 | LLM output varies | Parse race, check each runner has one of: highest_win_probability, best_value, best_place_candidate, no_bet |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
