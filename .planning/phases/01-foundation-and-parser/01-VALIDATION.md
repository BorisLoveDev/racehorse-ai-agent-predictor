---
phase: 1
slug: foundation-and-parser
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/stake/ -x -q` |
| **Full suite command** | `pytest tests/stake/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/stake/ -x -q`
- **After every plan wave:** Run `pytest tests/stake/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/stake/test_odds.py` — unit tests for odds normalization (PARSE-05)
- [ ] `tests/stake/conftest.py` — shared fixtures (sample paste data, mock Redis)
- [ ] `pip install pytest` — add pytest to requirements.txt

*Planner will populate full task map after plans are created.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram paste ingestion UX | INPUT-01 | Requires live Telegram bot interaction | Paste real Stake.com text into bot, verify summary response |
| Inline keyboard confirmation flow | PARSE-04 | UI interaction requires Telegram client | Confirm/reject parsed summary via inline buttons |
| Balance display in response header | BANK-04 | Visual Telegram formatting check | Verify USDT balance appears in every bot response |
| Progressive pipeline updates | PIPELINE-01 | Requires observing message sequence in Telegram | Watch step-by-step messages appear during pipeline run |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
