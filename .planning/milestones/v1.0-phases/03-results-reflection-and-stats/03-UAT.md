---
status: partial
phase: 03-results-reflection-and-stats
source: [03-VERIFICATION.md]
started: 2026-03-27
updated: 2026-03-27
---

## Current Test

[paused — deploy needed]

## Tests

### 1. Tracking Keyboard Display
expected: After recommendation message, two inline keyboard buttons appear — "Placed (I bet this)" and "Tracked (not bet)"
result: blocked — prod not deployed with Phase 3 code

### 2. Drawdown Skip Message UX
expected: After 25%+ drawdown from peak, paste triggers skip message with "DRAWDOWN PROTECTION", drawdown %, current vs peak balance, and "Unlock Protection" inline button
result: blocked — prod not deployed with Phase 3 code

### 3. Reflection Quality (REFLECT-02)
expected: After submitting a winning result, lesson error_tag and rule_sentence are specific and calibration-focused, not generic
result: blocked — prod not deployed with Phase 3 code

### 4. mindset.md Creation
expected: After result submission, `data/mindset.md` on server contains timestamped reflection entries in `## Reflection — YYYY-MM-DD HH:MM UTC` format
result: blocked — prod not deployed with Phase 3 code

## Summary

total: 4
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 4

## Gaps
