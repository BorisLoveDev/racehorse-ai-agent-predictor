---
quick_id: 260327-vxe
description: Fix drawdown_unlock_kb not attached to skip message in pipeline handler
date: 2026-03-27
status: complete
one_liner: "Wire drawdown_unlock_kb() as reply_markup on drawdown skip messages so user sees an Unlock button instead of needing /unlock_drawdown"
---

# Quick Task 260327-vxe: Fix drawdown_unlock_kb

## What Changed

`services/stake/handlers/pipeline.py`:
1. Added `drawdown_unlock_kb` to import from `stake_kb`
2. When `skip_signal=True` and `skip_tier==0` (drawdown), attach `drawdown_unlock_kb()` as `reply_markup` to the recommendation message

## Files Modified
- `services/stake/handlers/pipeline.py` — 2 changes (import + reply_markup)

## Tests
210 tests pass (no regressions)
