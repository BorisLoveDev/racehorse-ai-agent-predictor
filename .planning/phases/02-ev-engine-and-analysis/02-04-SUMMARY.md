---
phase: 02-ev-engine-and-analysis
plan: 04
subsystem: pipeline
tags: [analysis, sizing, formatter, graph, handler, audit, langgraph, kelly, ev, telegram]
dependency_graph:
  requires: ["02-02", "02-03"]
  provides: ["analysis_node", "sizing_node", "format_recommendation_node", "build_analysis_graph", "recommendation_handler"]
  affects: ["handlers/callbacks.py", "pipeline/graph.py"]
tech_stack:
  added: []
  patterns:
    - "html.escape() on all variable strings before Telegram HTML output"
    - "analysis graph uses conditional edges for skip bypass and error routing"
    - "sizing_node is pure Python (no LLM) per ARCH-01"
    - "_run_analysis_pipeline helper in callbacks.py wires FSM state to LangGraph ainvoke"
key_files:
  created:
    - tests/stake/test_sizing_node.py
  modified:
    - services/stake/pipeline/nodes.py
    - services/stake/pipeline/formatter.py
    - services/stake/pipeline/graph.py
    - services/stake/handlers/callbacks.py
    - services/stake/audit/logger.py
decisions:
  - "format_recommendation extracted to formatter.py (reusable) — format_recommendation_node delegates to it"
  - "analysis_node skips when skip_signal=True or research_error present — fail-fast, no wasted LLM calls"
  - "sizing_node checks analysis_result.overall_skip / ai_override → returns Tier 2 skip with skip_tier=2"
  - "_run_analysis_pipeline sends progressive Telegram messages before graph invocation"
  - "BankrollRepository instantiated in sizing_node (not from state) to get live balance"
  - "apply_portfolio_caps uses 'type' key — raw bets carry both 'type' and 'bet_type' for compatibility"
  - "Place bets without explicit place_odds in parsed_race are skipped (no guessing)"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-26T13:02:00Z"
  tasks_completed: 2
  files_changed: 5
---

# Phase 2 Plan 4: Pipeline Integration Summary

Phase 2 integration plan connecting math engine (Plan 02) + research layer (Plan 03) into
a complete end-to-end recommendation pipeline: LLM qualitative analysis with pre-computed EV,
deterministic Kelly sizing with portfolio caps, and Telegram HTML recommendation cards.

## Tasks Completed

### Task 1: analysis_node, sizing_node, format_recommendation_node with tests

**analysis_node** (`services/stake/pipeline/nodes.py`):
- Receives pre-computed no-vig probabilities as mathematical baseline (ARCH-01)
- Builds detailed prompt with race context, per-runner no-vig probs, and research summaries
- Calls ChatOpenAI with AnalysisResult structured output (expensive analysis model)
- Returns `{"analysis_result": result.model_dump()}`
- Skips immediately if `skip_signal=True` or `research_error` present

**sizing_node** (`services/stake/pipeline/nodes.py`):
- Pure Python deterministic sizing — no LLM (ARCH-01)
- Checks `analysis_result.overall_skip` and `ai_override` → Tier 2 skip with `skip_tier=2`
- For each +EV runner: computes Kelly fraction, applies quarter-Kelly multiplier, 3% per-bet cap
- Applies sparsity discount for runners with `data_quality in ("sparse", "none")`
- Calls `apply_portfolio_caps()` to enforce 2 win bet max and 5% total exposure
- Place bets require explicit `place_odds` from parsed race (not estimated)

**format_recommendation_node** (`services/stake/pipeline/nodes.py`):
- Delegates to `format_recommendation()` in formatter.py
- Returns `{"recommendation_text": str}`

**format_recommendation** (`services/stake/pipeline/formatter.py`):
- Skip message: `<b>SKIP</b> — {escaped reason}` with tier
- No bets: describes all runners are negative EV
- Runner cards: name, label, bet type, USDT, EV, Kelly%, reasoning (all escaped)
- Market discrepancy notes (D-15) appended with `html.escape()`
- Total exposure summary with % of bankroll at bottom
- ALL variable strings escaped with `html.escape()` per CLAUDE.md

**tests/stake/test_sizing_node.py** (17 tests, all passing):
- Portfolio cap enforcement (max win bets, total exposure)
- Sparsity discount application and data_sparse flag
- overall_skip and ai_override passthrough → Tier 2 skip
- skip_signal passthrough (returns {})
- Empty bets for all-negative-EV runners
- HTML escaping for runner_name, reasoning, skip_reason, market notes
- format_recommendation_node delegation test

### Task 2: Extended pipeline graph, handler, and audit

**build_analysis_graph()** (`services/stake/pipeline/graph.py`):
```
pre_skip_check -> [skip_router] -> format_recommendation -> END  (Tier 1 skip)
                                -> research -> [research_error_router] -> END
                                                                       -> analysis -> [analysis_error_router] -> END
                                                                                   -> sizing -> format_recommendation -> END
```
- 5 nodes: pre_skip_check, research, analysis, sizing, format_recommendation
- 3 router functions: skip_router, research_error_router, analysis_error_router
- Tier 1 skip bypasses all LLM nodes (saves API cost)
- Errors route to END (non-recoverable at analysis/research layer)

**handlers/callbacks.py** updates:
- `_run_analysis_pipeline()` helper: builds LangGraph initial state from FSM pipeline_result
- Sends progressive messages ("Race confirmed. Running analysis...", "Checking margins...")
- `await analysis_graph.ainvoke(initial_state)` invokes full Phase 2 graph
- Sends `recommendation_text` to user with `parse_mode="HTML"`
- Both bankroll confirmation paths (detected + existing) now trigger analysis pipeline
- Exception handling routes to idle state with error message

**audit/logger.py** updates:
- Added `recommendation` event type documentation (D-16)
- Captures: final_bets, skip_signal, skip_reason, skip_tier, analysis_summary, overround_active
- Added `analysis_error` event type

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Functionality] Place bets without explicit place_odds skipped**
- **Found during:** Task 1 implementation
- **Issue:** Plan specified looking up `place_odds` from parsed_race runners; if absent, not clear whether to estimate or skip.
- **Fix:** Skip place bets when `place_odds` is None in parsed race — no guessing, prevents false sizing.
- **Files modified:** services/stake/pipeline/nodes.py

**2. [Rule 2 - Missing Functionality] apply_portfolio_caps "type" key compatibility**
- **Found during:** Task 1 sizing_node implementation
- **Issue:** `apply_portfolio_caps()` uses `b["type"]` key but plan used `bet_type` in bet dicts.
- **Fix:** Raw bets carry both `"type"` and `"bet_type"` keys for compatibility with math.py function signature.
- **Files modified:** services/stake/pipeline/nodes.py

**3. [Rule 2 - Missing Functionality] Progressive analysis messages via callbacks**
- **Found during:** Task 2 handler update
- **Issue:** Plan mentioned progressive updates ("Checking margins...", "Researching runners...", etc.) but the analysis graph is a single ainvoke call. Sending a status message before the call provides user feedback.
- **Fix:** Send two status messages ("Running analysis...", "Checking margins...") before invoking the graph. Full streaming/step-by-step would require graph streaming which is a more complex architectural change (Rule 4 boundary — kept simple).
- **Files modified:** services/stake/handlers/callbacks.py

## Known Stubs

None — all data flows are wired. The recommendation pipeline reads live bankroll from SQLite and invokes real LLM calls. Telegram sends are real aiogram calls.

## Self-Check: PASSED

Files created/modified:
- /Users/borislovemac/projects/racehorse-agent/services/stake/pipeline/nodes.py — FOUND
- /Users/borislovemac/projects/racehorse-agent/services/stake/pipeline/formatter.py — FOUND
- /Users/borislovemac/projects/racehorse-agent/services/stake/pipeline/graph.py — FOUND
- /Users/borislovemac/projects/racehorse-agent/services/stake/handlers/callbacks.py — FOUND
- /Users/borislovemac/projects/racehorse-agent/services/stake/audit/logger.py — FOUND
- /Users/borislovemac/projects/racehorse-agent/tests/stake/test_sizing_node.py — FOUND

Commits:
- 46141b8: feat(02-04): implement analysis_node, sizing_node, format_recommendation_node with tests — FOUND
- ea55031: feat(02-04): extend pipeline graph, confirmation handler, and audit for Phase 2 — FOUND

Test results: 163 passed, 0 failed
