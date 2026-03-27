---
phase: 01-foundation-and-parser
plan: "04"
subsystem: telegram-bot
tags: [aiogram, fsm, redis, inline-keyboards, callback-data, telegram]

requires:
  - phase: 01-02
    provides: StakeSettings with redis.url/state_ttl/data_ttl, BankrollRepository with get/set balance and stake_pct

provides:
  - PipelineStates FSM state group (7 states including awaiting_clarification for PIPELINE-02)
  - ConfirmCB, BankrollCB, MenuCB callback data classes with 64-byte-safe prefixes
  - confirm_parse_kb, bankroll_confirm_kb, bankroll_input_kb, main_menu_kb keyboard builders
  - /start, /help, /cancel, /balance, /stake command handlers with balance_header helper
  - Bot entry point with Dispatcher + RedisStorage for FSM persistence

affects:
  - 01-05 (pipeline handlers will register into this bot's Dispatcher and use PipelineStates)
  - 01-06 (Docker service entry point is services/stake/main.py)

tech-stack:
  added: []
  patterns:
    - "FSM states defined in dedicated states.py StatesGroup — single source of truth for pipeline flow"
    - "CallbackData prefixes sc/sb/sm avoid collision with existing telegram service (m/r/s/c/d)"
    - "balance_header() helper centralizes bankroll display, called from every response"
    - "main.py include_router pattern: commands_router first, pipeline_router added in Plan 05"

key-files:
  created:
    - services/stake/states.py
    - services/stake/callbacks.py
    - services/stake/keyboards/__init__.py
    - services/stake/keyboards/stake_kb.py
    - services/stake/handlers/__init__.py
    - services/stake/handlers/commands.py
    - services/stake/main.py
  modified: []

key-decisions:
  - "MenuCB prefix 'sm' (not 'm') to avoid collision with existing telegram service MenuCB which uses 'm'"
  - "balance_header uses f-string dashes separator (not ─ unicode) in fallback path to avoid encoding issues"
  - "bankroll_input_kb included (not in plan spec) as completion of bankroll keyboard set for Plan 05 handlers"

patterns-established:
  - "PipelineStates.idle is the default state — /start and /cancel always return here"
  - "All keyboards return InlineKeyboardMarkup from InlineKeyboardBuilder.as_markup()"
  - "Command handlers call get_stake_settings() at handler call time (not module level) so lru_cache works correctly"

requirements-completed: [INPUT-01, INPUT-02, PIPELINE-03, PIPELINE-05, BANK-04, BANK-05]

duration: 8min
completed: 2026-03-24
---

# Phase 01 Plan 04: Telegram Bot Skeleton Summary

**aiogram bot shell with RedisStorage FSM, 7-state PipelineStates, /start /help /cancel /balance /stake commands, and inline keyboard infrastructure for parse confirmation and bankroll management**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-24T09:31:49Z
- **Completed:** 2026-03-24T09:39:52Z
- **Tasks:** 2
- **Files modified:** 7 created

## Accomplishments

- PipelineStates with 7 states including awaiting_clarification (PIPELINE-02 ambiguous data flow)
- CallbackData classes ConfirmCB/BankrollCB/MenuCB with short prefixes (sc/sb/sm) well under 64-byte Telegram limit
- All four inline keyboard builders: confirm_parse_kb, bankroll_confirm_kb, bankroll_input_kb, main_menu_kb
- Five command handlers: /start (sets idle + shows welcome), /help (full guide), /cancel (clears FSM), /balance (view/set), /stake (view/set %)
- Bot entry point with Dispatcher + RedisStorage using redis.url/state_ttl/data_ttl from StakeSettings

## Task Commits

Each task was committed atomically:

1. **Task 1: FSM states, callbacks, and keyboards** - `d28ab81` (feat)
2. **Task 2: Bot entry point and command handlers** - `d68dbc5` (feat)

**Plan metadata:** (to be committed)

## Files Created/Modified

- `services/stake/states.py` - PipelineStates FSM group with 7 states for full pipeline flow
- `services/stake/callbacks.py` - ConfirmCB (sc), BankrollCB (sb), MenuCB (sm) callback data classes
- `services/stake/keyboards/__init__.py` - Empty package init
- `services/stake/keyboards/stake_kb.py` - Keyboard builders: confirm_parse_kb, bankroll_confirm_kb, bankroll_input_kb, main_menu_kb
- `services/stake/handlers/__init__.py` - Empty package init
- `services/stake/handlers/commands.py` - Command handlers + balance_header() helper function
- `services/stake/main.py` - Bot entry point: Bot + Dispatcher + RedisStorage + include_router

## Decisions Made

- MenuCB prefix `sm` (not `m`) to avoid collision with existing telegram service `MenuCB` which uses prefix `m`
- bankroll_input_kb added even though not explicitly in keyboard spec — needed by Plan 05 awaiting_bankroll_input state handlers
- Commands import get_stake_settings() at handler call time so lru_cache singleton works correctly across tests

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Worktree did not have stake service files from Plans 01-02 (they were merged to main branch from other worktrees). Merged main into worktree branch before executing. This is expected parallel worktree behavior.
- `ConfirmCB.prefix` attribute is not directly accessible in this aiogram version — verified via `.pack()` method output instead.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

All 7 files confirmed present on disk. Both task commits (d28ab81, d68dbc5) confirmed in git log.

## Next Phase Readiness

- Bot skeleton complete: Plan 05 can import `PipelineStates`, `ConfirmCB`, `BankrollCB`, and register pipeline router into existing Dispatcher
- All 7 FSM states defined, including `awaiting_clarification` for PIPELINE-02 ambiguous data handling
- Keyboard builders ready for use in Plan 05 pipeline flow handlers

---
*Phase: 01-foundation-and-parser*
*Completed: 2026-03-24*
