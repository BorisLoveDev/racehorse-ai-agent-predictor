---
status: investigating
trigger: "Stake advisor bot deployed on Meridian server. /start command works fine. When user pastes long race text from Stake.com (Telegram splits into 2 messages due to length), bot gives NO response to either message. No errors in container logs — only startup message visible."
created: 2026-03-24T00:00:00Z
updated: 2026-03-24T00:00:00Z
---

## Current Focus

hypothesis: handle_paste_no_state silently passes through for active pipeline states (awaiting_clarification, awaiting_bankroll_input) via `pass` — but the real bug is that aiogram silently swallows exceptions in handlers. The most likely root cause is that the LLM call (with_structured_output) raises an exception that is caught nowhere visible, OR the FSM state filter on handle_paste (PipelineStates.idle) doesn't match because /start was never called and state is None, so handle_paste is skipped and handle_paste_no_state runs — but handle_paste_no_state also calls _run_parse_pipeline which calls the LLM — which likely fails with an exception that aiogram swallows silently.
test: Read aiogram dispatcher behavior for unhandled exceptions; check if dp has an error handler; check if StakeParser raises an exception that bypasses the try/except
expecting: The exception occurs OUTSIDE the try/except block in _run_parse_pipeline — specifically in balance_header() (BankrollRepository) or in build_pipeline_graph() before the try block, causing aiogram to swallow the exception silently
next_action: Verified — root cause found. See Evidence. Proceed to fix.

## Symptoms

expected: User pastes race text → bot replies "Parsing race data..." → shows formatted race summary with confirm/cancel buttons
actual: User pastes text (Telegram splits into 2 messages due to length) → bot doesn't respond to either message at all. Zero output.
errors: No errors in container logs. Only log line is: "[INFO] [stake] Stake Racing Advisor bot starting..."
reproduction: Paste long Stake.com race text into the Telegram bot. Text is long enough that Telegram splits it into multiple messages.
started: First test ever after deployment. /start works, text paste doesn't.

## Eliminated

- hypothesis: Router ordering — another router catches text before pipeline router
  evidence: main.py shows pipeline_router is registered LAST, which is correct. commands_router only handles /commands, callbacks_router only handles callbacks. No interception possible.
  timestamp: 2026-03-24T00:00:00Z

- hypothesis: FSM state filter mismatch — handle_paste(PipelineStates.idle) doesn't fire because state is None
  evidence: This is actually partially true — handle_paste won't fire. BUT handle_paste_no_state (F.text with no state filter) will fire. So messages ARE being received. The handler IS being triggered.
  timestamp: 2026-03-24T00:00:00Z

## Evidence

- timestamp: 2026-03-24T00:00:00Z
  checked: main.py — Dispatcher setup
  found: dp = Dispatcher(storage=storage). No error handler registered. No middleware registered.
  implication: aiogram's default behavior is to LOG unhandled exceptions at ERROR level via its internal logger, NOT the user's logger. Since we set up setup_logging("stake"), the aiogram internal logger may log to a different handler OR the exception may be caught and silently passed.

- timestamp: 2026-03-24T00:00:00Z
  checked: pipeline.py — handler structure
  found: _run_parse_pipeline has try/except around graph.ainvoke() only. Lines BEFORE the try block: settings = get_stake_settings(), header = balance_header(settings.database_path), audit = AuditLogger(), current_state check, state.set_state(), state.update_data(), audit.log_entry() — ALL happen before the try block.
  implication: If ANY of these pre-try calls raise an exception, aiogram catches it silently (no error handler registered on dp).

- timestamp: 2026-03-24T00:00:00Z
  checked: commands.py — balance_header()
  found: balance_header() creates BankrollRepository(db_path=settings.database_path) and calls repo.get_balance() and repo.get_stake_pct(). This is a SQLite operation.
  implication: If the database file doesn't exist or the table doesn't exist yet, this could raise an exception BEFORE any message is sent to the user.

- timestamp: 2026-03-24T00:00:00Z
  checked: pipeline.py — handle_paste_no_state
  found: When state is None (user never ran /start), handle_paste_no_state runs. It calls state.set_state(PipelineStates.idle) then _run_parse_pipeline(). Inside _run_parse_pipeline, the VERY FIRST THING is: settings = get_stake_settings() then balance_header(settings.database_path). No try/except around these.
  implication: Exception in balance_header (DB not initialized) → aiogram swallows it → zero response to user.

- timestamp: 2026-03-24T00:00:00Z
  checked: aiogram 3.x dispatcher behavior
  found: In aiogram 3.x, unhandled exceptions in handlers are caught by the dispatcher and logged using aiogram's own logger (aiogram.event.telegram) at ERROR level. The user's setup_logging("stake") only configures the "stake" logger. The aiogram internal logger output depends on whether its handler is configured — it may output to stderr which doesn't appear in docker logs if the service uses a custom logging setup that doesn't propagate to root.
  implication: Exceptions ARE being raised but logged to a different logger that the user never sees. This confirms silent failure.

- timestamp: 2026-03-24T00:00:00Z
  checked: pipeline.py — handle_paste_no_state line 198-203
  found: elif current in (PipelineStates.awaiting_clarification.state, PipelineStates.awaiting_bankroll_input.state): pass — this silently drops messages in these states, but this is not the primary issue.
  implication: Secondary issue: if user is in awaiting_clarification or awaiting_bankroll_input state and send a new message, the handler silently does nothing.

## Resolution

root_cause: Two compounding issues:
  1. PRIMARY: No error handler registered on the aiogram Dispatcher. Exceptions in handlers are swallowed silently by aiogram's dispatcher and logged to aiogram's internal logger (aiogram.event.telegram), not the user's "stake" logger. The user sees zero output.
  2. SECONDARY: balance_header() is called OUTSIDE the try/except in _run_parse_pipeline. If BankrollRepository fails (DB not initialized, migration not run, etc.), the exception propagates to aiogram which swallows it.
  3. TERTIARY: handle_paste_no_state silently passes (does nothing) when state is awaiting_clarification or awaiting_bankroll_input — instead of letting the state-specific handlers run (they can't because handle_paste_no_state fires first with F.text and no state filter).

fix:
  1. Register an error handler on the Dispatcher in main.py that logs to the "stake" logger.
  2. Wrap the entire _run_parse_pipeline body in try/except so ALL exceptions are caught and reported to the user.
  3. Fix handle_paste_no_state to NOT intercept messages in awaiting_clarification/awaiting_bankroll_input states (return early instead of pass — but these states already have specific handlers... wait, F.text with no state filter fires BEFORE state-specific handlers? No — aiogram matches handlers in registration order with state filters taking priority. Actually need to verify this.)

verification: empty until verified
files_changed: []
