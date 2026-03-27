# Phase 2: EV Engine and Analysis - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Given a confirmed parsed race from Phase 1, the bot runs web research on each runner, computes overround/EV/Kelly via deterministic Python functions, produces AI analysis with betting-relevant labels, applies portfolio risk caps and uncertainty discount, and delivers exact USDT bet amounts — or issues a skip signal when the margin makes betting structurally unprofitable. This phase adds research, analysis, and bet sizing nodes to the existing LangGraph pipeline.

</domain>

<decisions>
## Implementation Decisions

### Research Strategy
- **D-01:** Primary search provider is OpenRouter online model (e.g., Perplexity or Gemini with grounding) — has built-in web access, single API call. SearXNG as fallback when online model returns sparse results.
- **D-02:** Research orchestrator pattern — expensive model (`AnalysisSettings.model`, gemini-pro) creates a research plan, then cheap sub-agents (`ResearchSettings.model`, flash-lite) execute it via sub-agent spawning.
- **D-03:** The orchestrator (senior agent) autonomously decides: research each runner individually, batch some together, or skip runners where data is sufficient from the paste. Full autonomy over research strategy.
- **D-04:** The senior agent decides what data to prioritize per runner (form, trainer stats, expert tips, track conditions) — no hardcoded research template. The prompt describes available data categories but lets the agent choose.
- **D-05:** Search provider configurable via env var (`STAKE_RESEARCH__PROVIDER`): `online` (default) or `searxng`.

### Two-Tier Skip Signal
- **D-06:** **Pre-analysis skip (Tier 1):** After parsing (Phase 1 calc_node output), if overround exceeds configurable threshold → automatic skip BEFORE research/analysis. Saves cost by not running expensive LLM calls on squeezed races. Threshold is configurable via env, Claude picks sensible default.
- **D-07:** **Post-analysis skip (Tier 2):** After AI analysis, the senior agent can recommend skip based on qualitative assessment — bad race situation, unreliable data, suspicious patterns. Prompted to say "don't bet if you think the situation is unfavorable."
- **D-08:** AI can override positive EV — if research reveals red flags (e.g., horse withdrawn info not reflected in odds, suspicious pattern, unreliable data), the agent can recommend skip even when math says +EV. Output includes "AI override" flag explaining why.

### EV/Kelly Math Engine
- **D-09:** All numerical calculations in deterministic Python (ARCH-01): no-vig probability, EV, Kelly fraction, USDT amounts. Results passed to senior agent as computed inputs — agent never generates final bet amounts.
- **D-10:** Kelly fraction default, per-bet caps (3%), total race exposure cap (5%), max 2 win bets — all per requirements BET-01 through BET-07. Exact Kelly fraction (quarter-Kelly vs flat 1%) is Claude's discretion during implementation.
- **D-11:** When research data is sparse for a runner, sizing halved and flagged (ANALYSIS-04 uncertainty discount).
- **D-12:** Place bet payout uses correct terms extracted from parse (BET-07) — not assumed as win odds.

### AI Analysis Output
- **D-13:** Structured card per runner in Telegram: name, betting label (`highest_win_probability`, `best_value`, `best_place_candidate`, `no_bet`), EV, Kelly%, USDT amount, and 2-3 sentence reasoning.
- **D-14:** Numbers + brief reasoning — each recommended runner gets an explanation of why. Helps user understand the recommendation.
- **D-15:** Market discrepancy note when research finds significantly different odds (ANALYSIS-05).
- **D-16:** Audit log entry updated with recommendation data for this run (extends Phase 1 audit trail).

### Claude's Discretion
- Exact overround threshold for pre-analysis skip (BET-05 says 15% default)
- Kelly fraction: quarter-Kelly vs flat 1% until calibrated — pick based on research
- Research prompt design and sub-agent spawning strategy
- Telegram message formatting and card layout for recommendations
- How to structure the LangGraph nodes for research → analysis → sizing
- Error handling when research or analysis fails mid-pipeline
- How to handle edge cases: all runners -EV, only 1 runner +EV, etc.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — Full v1 requirements; Phase 2 covers SEARCH-01/02, ANALYSIS-01-05, BET-01-07
- `.planning/REQUIREMENTS.md` §Architectural Rules — ARCH-01: all numerical calculations by deterministic Python, never LLM

### Phase 1 context
- `.planning/phases/01-foundation-and-parser/01-CONTEXT.md` — Phase 1 decisions (service architecture, parse model, pipeline, bankroll)

### Existing code (Phase 1 output)
- `services/stake/settings.py` — `StakeSettings` with `ParserSettings`, `ResearchSettings`, `AnalysisSettings` already defined
- `services/stake/parser/models.py` — `ParsedRace`, `RunnerInfo` Pydantic models (data contracts)
- `services/stake/parser/math.py` — Deterministic odds math: `to_decimal`, `implied_probability`, `overround`, `recalculate_without_scratches`, `odds_drift_pct`
- `services/stake/pipeline/state.py` — `PipelineState` TypedDict (extend for research/analysis/sizing fields)
- `services/stake/pipeline/graph.py` — LangGraph StateGraph with `parse → calc` nodes (extend with research → analysis → sizing nodes)
- `services/stake/pipeline/nodes.py` — `parse_node`, `calc_node` implementations (pattern for new nodes)
- `services/stake/pipeline/formatter.py` — `format_race_summary` HTML formatter (extend for recommendation cards)

### Project context
- `.planning/PROJECT.md` — Vision, constraints, framework decision (LangGraph)
- `.planning/ROADMAP.md` — Phase 2 goal and success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`parser/math.py`**: Already has `implied_probability`, `overround`, `recalculate_without_scratches` — extend with `no_vig_probability`, `expected_value`, `kelly_fraction`, `bet_size_usdt` functions
- **`pipeline/state.py`**: `PipelineState` TypedDict — add fields for research results, analysis output, bet recommendations
- **`pipeline/graph.py`**: LangGraph `StateGraph` with conditional edges — add research/analysis/sizing nodes with error routing
- **`pipeline/formatter.py`**: HTML formatter for Telegram — extend with recommendation card formatting
- **`settings.py`**: `ResearchSettings` and `AnalysisSettings` already configured with model, temperature, max_tokens
- **`bankroll/`**: Bankroll repository already provides current balance for sizing calculations

### Established Patterns
- **LangGraph nodes**: Each node is an async function taking `PipelineState`, returning partial update dict. New nodes follow same pattern.
- **Pydantic models for data contracts**: `ParsedRace`, `RunnerInfo` — extend with analysis/recommendation models
- **ARCH-01 enforcement**: Math functions are pure Python, no LLM. New EV/Kelly functions follow same pattern.
- **Error routing**: `error_router` conditional edge after parse — same pattern for research/analysis error handling
- **Settings via `BaseModel` nested in `BaseSettings`**: New config (e.g., skip threshold, Kelly fraction) follows same pattern

### Integration Points
- **Pipeline graph**: New nodes chain after existing `calc` node: `calc → pre_skip_check → research → analysis → sizing → format_recommendation`
- **FSM state**: Pipeline handlers in `handlers/pipeline.py` trigger the extended graph
- **Bankroll**: `bankroll/repository.py` provides balance for sizing calculations
- **Audit trail**: `audit/` module logs recommendation data alongside parse data
- **Telegram output**: Extended formatter produces recommendation cards sent via existing message handlers

</code_context>

<specifics>
## Specific Ideas

- User emphasized: "senior agent decides everything important" — give the analysis agent maximum autonomy over qualitative decisions
- Two-tier skip is cost-saving: pre-analysis skip avoids wasting LLM calls on squeezed races
- Research orchestrator creates a plan, cheap sub-agents execute — this is a LangGraph sub-graph or tool-calling pattern
- AI override flag when agent recommends skip despite +EV — transparency for user
- All math in Python, all judgment calls to the senior agent — clean separation

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-ev-engine-and-analysis*
*Context gathered: 2026-03-25*
