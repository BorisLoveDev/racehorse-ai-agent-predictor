# Phase 3: Results, Reflection and Stats - Context

**Gathered:** 2026-03-27 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

User can submit a race result back to the bot; the system evaluates every recommended bet (distinguishing placed from tracked), updates P&L, writes a memory-distilled AI reflection, makes statistics visible on demand, and activates a drawdown circuit breaker if the bank drops 20% from peak.

</domain>

<decisions>
## Implementation Decisions

### Result Input and Parsing
- **D-01:** LLM-based result parsing — reuse the same `StakeParser` pattern for flexible text input ("3,5,11,12" or "horse name won"), with ambiguity detection and clarification flow via FSM `awaiting_clarification` state.
- **D-02:** Results linked to recommendations via `run_id` from `stake_pipeline_runs` — reference stored in FSM state after recommendation display, matched on result submission.

### Placed vs Tracked & P&L Storage
- **D-03:** Placed/tracked distinction presented as inline keyboard on the recommendation message itself — user taps "Placed" or "Tracked" before submitting results. New `st:` callback prefix, follows existing callback pattern.
- **D-04:** P&L stored in new SQLite table (`stake_bet_outcomes`) alongside existing tables, following the migration and repository patterns. Each row links to a pipeline run and records per-bet outcome (win/loss, amount won/lost).
- **D-05:** `stake_bankroll` table gets a `peak_balance_usdt` column for drawdown tracking (RISK-01).

### AI Reflection and Lesson Extraction
- **D-06:** Use configurable model for reflections — new `ReflectionSettings` nested BaseModel in `StakeSettings`, defaulting to the analysis model but independently configurable.
- **D-07:** Dual storage: `mindset.md` server-side markdown file for human-readable reflection log + SQLite `stake_lessons` table for queryable structured lessons.
- **D-08:** Lessons injected into analysis prompt: top-5 extracted rules + last-3 failure modes queried from `stake_lessons` and appended to `_build_analysis_prompt()`.

### Drawdown Circuit Breaker
- **D-09:** Early pipeline check before analysis — read peak balance from bankroll table, compare with current balance. If ≥20% drawdown, short-circuit to skip message without running expensive LLM steps. Follows existing `pre_skip_check_node` pattern.
- **D-10:** 20% threshold configurable via env var. Deterministic math only (ARCH-01).

### Claude's Discretion
- Exact SQLite schema for `stake_bet_outcomes` and `stake_lessons` tables
- Result parsing prompt design
- `mindset.md` format and reflection prose style
- Telegram message formatting for result confirmation and stats display
- How to handle partial results (e.g., user only knows winner, not full finishing order)
- Stats display layout and which metrics to show for STATS-01
- FSM state names and transitions for the result submission flow

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — Phase 3 covers RESULT-01, RESULT-02, RESULT-03, TRACK-01, REFLECT-01, REFLECT-02, REFLECT-03, STATS-01, RISK-01
- `.planning/REQUIREMENTS.md` §Architectural Rules — ARCH-01: all numerical calculations by deterministic Python, never LLM

### Phase 1 & 2 context
- `.planning/phases/01-foundation-and-parser/01-CONTEXT.md` — Service architecture, parse model, pipeline, bankroll, Telegram UX
- `.planning/phases/02-ev-engine-and-analysis/02-CONTEXT.md` — Research/analysis nodes, EV/Kelly math, two-tier skip, portfolio sizing

### Existing code (Phase 1 & 2 output)
- `services/stake/pipeline/nodes.py` — Existing pipeline nodes (`parse_node`, `calc_node`, `pre_skip_check_node`, `research_node`, `analysis_node`, `sizing_node`) — pattern for new result/reflection nodes
- `services/stake/pipeline/state.py` — `PipelineState` TypedDict — extend for result/reflection fields
- `services/stake/pipeline/graph.py` — LangGraph StateGraph — add result processing subgraph
- `services/stake/pipeline/formatter.py` — HTML formatter — extend for result confirmation and stats display
- `services/stake/bankroll/repository.py` — Bankroll singleton repository — extend for peak balance and P&L queries
- `services/stake/bankroll/migrations.py` — Migration pattern — add new tables and columns
- `services/stake/callbacks.py` — CallbackData classes (`sc:`, `sb:`, `ss:`) — add `st:` for tracking
- `services/stake/keyboards/stake_kb.py` — Inline keyboard builders — add placed/tracked and stats keyboards
- `services/stake/audit/logger.py` — JSONL audit logger — extend entries with result data
- `services/stake/settings.py` — `StakeSettings` with nested settings — add `ReflectionSettings`
- `services/stake/states.py` — FSM states — add result submission states
- `services/stake/handlers/pipeline.py` — Pipeline handlers — add result submission handler

### Project context
- `.planning/PROJECT.md` — Vision, constraints, framework decision (LangGraph)
- `.planning/ROADMAP.md` — Phase 3 goal and success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`StakeParser`** (`parser/llm_parser.py`): LLM parsing with structured output — reuse for result text parsing
- **`pipeline/nodes.py`**: Node pattern (async fn → partial state update dict) — apply to result evaluation, reflection, lesson extraction nodes
- **`pre_skip_check_node`**: Early exit pattern — reuse for drawdown circuit breaker
- **`bankroll/repository.py`**: Singleton table pattern — extend with peak balance column and P&L query methods
- **`bankroll/migrations.py`**: `CREATE TABLE IF NOT EXISTS` pattern — add `stake_bet_outcomes`, `stake_lessons` tables
- **`callbacks.py`**: Short-prefix CallbackData classes — add `st:` for placed/tracked
- **`audit/logger.py`**: JSONL append pattern — extend for result and reflection entries
- **`_build_analysis_prompt()`** (`nodes.py`): Analysis prompt construction — add lesson injection point

### Established Patterns
- **LangGraph nodes**: Async functions taking `PipelineState`, returning partial update dicts
- **Pydantic structured output**: `ChatOpenAI().with_structured_output(Model)` for LLM calls
- **ARCH-01**: All numerical calculations (P&L, drawdown %) in deterministic Python
- **BaseModel for nested config**: `ReflectionSettings` follows `ParserSettings`/`ResearchSettings` pattern
- **64-byte callback limit**: Short prefixes (`st:`) with minimal payload
- **TypedDict with dict fields**: For Redis FSM compatibility (no Pydantic objects in state)

### Integration Points
- **Pipeline graph**: Result processing as separate subgraph or handler flow (not inline with analysis pipeline)
- **FSM state machine**: New states for `awaiting_placed_tracked`, `awaiting_result`, `confirming_result`
- **Bankroll**: Update balance after result evaluation, track peak balance
- **Analysis prompt**: Inject lessons from `stake_lessons` table into next race's analysis
- **Telegram output**: Result confirmation cards, stats display, drawdown warning messages

</code_context>

<specifics>
## Specific Ideas

- Result parsing should be as flexible as race text parsing — user might type "3 won" or "3,5,11" or "Thunder won, Lightning 2nd"
- Placed/tracked choice happens immediately after recommendation, not at result time — prevents forgetting
- Lessons feed back into the analysis loop — the system should get smarter over time
- Drawdown breaker is a safety net — fires before expensive LLM calls to save money AND protect bankroll

</specifics>

<deferred>
## Deferred Ideas

None — analysis stayed within phase scope

</deferred>

---

*Phase: 03-results-reflection-and-stats*
*Context gathered: 2026-03-27*
