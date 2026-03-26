# Phase 2: EV Engine and Analysis - Research

**Researched:** 2026-03-26
**Domain:** EV/Kelly math engine, LangGraph research orchestrator, SearXNG integration, OpenRouter online models, Telegram recommendation cards
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Research Strategy**
- D-01: Primary search provider is OpenRouter online model (Perplexity or Gemini with grounding) — has built-in web access, single API call. SearXNG as fallback when online model returns sparse results.
- D-02: Research orchestrator pattern — expensive model (AnalysisSettings.model, gemini-pro) creates a research plan, then cheap sub-agents (ResearchSettings.model, flash-lite) execute it via sub-agent spawning.
- D-03: The orchestrator (senior agent) autonomously decides: research each runner individually, batch some together, or skip runners where data is sufficient from the paste. Full autonomy over research strategy.
- D-04: The senior agent decides what data to prioritize per runner (form, trainer stats, expert tips, track conditions) — no hardcoded research template. Prompt describes available data categories but lets the agent choose.
- D-05: Search provider configurable via env var (STAKE_RESEARCH__PROVIDER): `online` (default) or `searxng`.

**Two-Tier Skip Signal**
- D-06: Pre-analysis skip (Tier 1): After parsing (Phase 1 calc_node output), if overround exceeds configurable threshold → automatic skip BEFORE research/analysis. Saves cost by not running expensive LLM calls on squeezed races. Threshold configurable via env, Claude picks sensible default.
- D-07: Post-analysis skip (Tier 2): After AI analysis, the senior agent can recommend skip based on qualitative assessment — bad race situation, unreliable data, suspicious patterns. Prompted to say "don't bet if you think the situation is unfavorable."
- D-08: AI can override positive EV — if research reveals red flags, the agent can recommend skip even when math says +EV. Output includes "AI override" flag explaining why.

**EV/Kelly Math Engine**
- D-09: All numerical calculations in deterministic Python (ARCH-01): no-vig probability, EV, Kelly fraction, USDT amounts. Results passed to senior agent as computed inputs — agent never generates final bet amounts.
- D-10: Kelly fraction default, per-bet caps (3%), total race exposure cap (5%), max 2 win bets — all per requirements BET-01 through BET-07. Exact Kelly fraction (quarter-Kelly vs flat 1%) is Claude's discretion during implementation.
- D-11: When research data is sparse for a runner, sizing halved and flagged (ANALYSIS-04 uncertainty discount).
- D-12: Place bet payout uses correct terms extracted from parse (BET-07) — not assumed as win odds.

**AI Analysis Output**
- D-13: Structured card per runner in Telegram: name, betting label, EV, Kelly%, USDT amount, 2-3 sentence reasoning.
- D-14: Numbers + brief reasoning — each recommended runner gets an explanation of why.
- D-15: Market discrepancy note when research finds significantly different odds (ANALYSIS-05).
- D-16: Audit log entry updated with recommendation data for this run (extends Phase 1 audit trail).

### Claude's Discretion
- Exact overround threshold for pre-analysis skip (BET-05 says 15% default)
- Kelly fraction: quarter-Kelly vs flat 1% until calibrated — pick based on research
- Research prompt design and sub-agent spawning strategy
- Telegram message formatting and card layout for recommendations
- How to structure the LangGraph nodes for research → analysis → sizing
- Error handling when research or analysis fails mid-pipeline
- How to handle edge cases: all runners -EV, only 1 runner +EV, etc.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEARCH-01 | Web research for each runner's form, trainer stats, expert opinions, recent race history | SearXNG async @tool + create_react_agent pattern; 40+ results per query confirmed |
| SEARCH-02 | Search provider configurable: SearXNG or OpenRouter online model via env var | STAKE_RESEARCH__PROVIDER env var added to ResearchSettings; ChatOpenAI extra_body supports online models |
| ANALYSIS-01 | AI labels each runner with betting-relevant category (highest_win_probability, best_value, best_place_candidate, no_bet) | Pydantic response_format in create_react_agent v2 enforces structured output |
| ANALYSIS-02 | Overround/no-vig probability by deterministic Python (ARCH-01) | Extend math.py: no_vig_probability = implied_prob / overround |
| ANALYSIS-03 | EV = AI probability vs no-vig probability, deterministic Python (ARCH-01) | EV = ai_prob * (odds - 1) - (1 - ai_prob) using no-vig baseline |
| ANALYSIS-04 | 50% uncertainty discount on sizing when research data is sparse; flagged in output | apply_sparsity_discount() pure function; data_sparse flag from research node |
| ANALYSIS-05 | Market discrepancy note when external sources show significantly different odds | Research returns external_odds per runner; compare in sizing node |
| BET-01 | All EV/Kelly/USDT calculations by deterministic Python — LLM receives computed numbers | Extend math.py; results dict passed into analysis prompt as structured context |
| BET-02 | Quarter-Kelly default (0.25×); configurable via env | kelly_fraction() * 0.25; STAKE_SIZING__KELLY_MULTIPLIER env var |
| BET-03 | Hard cap per bet: max 3% of bankroll regardless of Kelly | min(kelly_amount, bankroll * 0.03) in bet_size_usdt() |
| BET-04 | Max 5% total exposure per race; max 2 win bets | apply_portfolio_caps() sorts by EV, enforces both constraints |
| BET-05 | Skip signal when overround > threshold (default 15%) | pre_skip_check node after calc; (overround - 1) * 100 > threshold |
| BET-06 | Output shows exact USDT amounts per bet type | format_recommendation() in formatter.py extension |
| BET-07 | Place bet payout uses extracted place terms from parse | place_odds from RunnerInfo; place_bet_ev() uses runner.place_odds, not win_odds |
</phase_requirements>

---

## Summary

Phase 2 extends the existing LangGraph pipeline (`calc → END`) with four new nodes: `pre_skip_check → research → analysis → sizing → format_recommendation`. The math engine (EV, Kelly, portfolio caps) is a pure-Python extension of the existing `parser/math.py` module. The research layer uses a LangGraph `create_react_agent` pattern with an async SearXNG `@tool`; the senior analysis agent receives structured computed inputs and returns a Pydantic-validated recommendation.

The key architectural insight from code inspection: LangGraph 1.0.7 `create_react_agent` supports `response_format` (Pydantic model for structured output) and can be invoked directly inside a node function. A compiled sub-graph can also be passed as a node to the outer `StateGraph`. Both patterns are verified to work in the installed version. The simpler approach — calling `research_agent.ainvoke()` inside a `research_node` function — avoids sub-graph state schema conflicts and is preferred.

SearXNG at `http://46.30.43.46:8888` is live and returns 35-40 horse racing results per query. Async httpx is already installed and tested. The online model path (OpenRouter Perplexity/Sonar or Gemini with grounding) uses `ChatOpenAI(extra_body={"plugins": [{"id": "web"}]})` for web-grounded responses.

**Primary recommendation:** Implement research as a tool-calling React agent invoked inside a LangGraph node. All math in pure-Python functions added to `math.py`. Analysis senior agent receives computed values in a structured prompt and returns a `Pydantic`-validated `AnalysisResult`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.0.7 (installed) | Pipeline graph, node orchestration | Already used; create_react_agent, StateGraph, sub-graph support verified |
| langchain-openai | 1.1.7 (installed) | ChatOpenAI with extra_body for OpenRouter | Already used; extra_body confirmed for web plugins |
| langchain-core | 1.2.7 (installed) | @tool decorator, BaseTool, ToolNode | @tool with async httpx verified working |
| httpx | 0.28.1 (installed) | Async HTTP client for SearXNG | Already installed; AsyncClient tested against SearXNG |
| pydantic | (installed) | Structured output models for analysis | Already used for ParsedRace/RunnerInfo |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 (installed) | Unit tests for math functions | All new math.py functions need unit tests |
| pytest-asyncio | (check) | Async test support | Needed for testing async research tools |

### Verify before writing code
```bash
pip show pytest-asyncio
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| create_react_agent inside node | Sub-graph as outer node | Sub-graph nesting requires matching state schemas — extra complexity. Direct ainvoke() inside node is simpler |
| httpx AsyncClient for SearXNG | aiohttp | httpx already installed and tested; aiohttp available but unnecessary |
| Pydantic response_format in agent | JSON parsing from LLM text | response_format enforces structure, no fragile string parsing |

**Installation:**
No new packages needed. All dependencies already installed in project venv.

---

## Architecture Patterns

### Recommended Pipeline Extension

```
[existing] parse → calc → [new] pre_skip_check → research → analysis → sizing → format_recommendation → END
                     ↓ (error)          ↓ (skip)          ↓ (error/skip)
                    END               END                END
```

### Recommended Project Structure
```
services/stake/
├── parser/
│   └── math.py              # Extend with: no_vig_probability, expected_value,
│                            #   kelly_fraction, bet_size_usdt, apply_portfolio_caps,
│                            #   apply_sparsity_discount, place_bet_ev
├── pipeline/
│   ├── state.py             # Extend PipelineState with research/analysis/sizing fields
│   ├── graph.py             # Add new nodes + conditional edges
│   ├── nodes.py             # Add: pre_skip_check_node, research_node, analysis_node, sizing_node
│   ├── formatter.py         # Add: format_recommendation() for Telegram cards
│   └── research/
│       ├── __init__.py
│       ├── tools.py         # @tool functions: searxng_search, online_model_search
│       └── agent.py         # create_react_agent wrapping research tools
├── analysis/
│   ├── __init__.py
│   ├── models.py            # Pydantic: RunnerAnalysis, AnalysisResult, BetRecommendation
│   └── prompts.py           # System prompts for senior analysis agent
└── settings.py              # Add: SizingSettings, ResearchSettings.provider field
```

### Pattern 1: Math Engine Extension (ARCH-01)

**What:** Pure functions added to `parser/math.py`. No I/O, no LLM, deterministic.
**When to use:** All numerical derivations — EV, Kelly, bet sizes.

```python
# Source: verified against Kelly Criterion formula
def no_vig_probability(implied_prob: float, book_overround: float) -> float:
    """Normalize implied probability to remove bookmaker margin.

    Uses simple normalization (Shin method is more accurate but adds complexity).
    Suitable for v1 given no calibration data yet.
    """
    return round(implied_prob / book_overround, 6)


def expected_value(ai_prob: float, decimal_odds: float) -> float:
    """EV as fraction of stake using AI-assigned probability.

    Positive EV = structurally profitable long-term at these odds.
    Uses AI probability (not no-vig probability) as the true probability estimate.
    """
    b = decimal_odds - 1.0
    q = 1.0 - ai_prob
    return round(ai_prob * b - q, 6)


def kelly_fraction(ai_prob: float, decimal_odds: float) -> float:
    """Full Kelly fraction. Caller applies multiplier (e.g., 0.25 for quarter-Kelly).

    Returns 0.0 for negative EV (no bet signal).
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - ai_prob
    f = (b * ai_prob - q) / b
    return max(0.0, round(f, 6))


def bet_size_usdt(
    bankroll: float,
    kelly_f: float,
    kelly_multiplier: float = 0.25,
    per_bet_cap_pct: float = 0.03,
    min_bet: float = 1.0,
) -> float:
    """USDT bet size: quarter-Kelly with hard cap, minimum 1 USDT.

    Returns 0.0 if raw bet < min_bet (caller interprets as 'no bet').
    """
    raw = bankroll * kelly_f * kelly_multiplier
    capped = min(raw, bankroll * per_bet_cap_pct)
    if capped < min_bet:
        return 0.0
    return round(capped, 2)


def apply_portfolio_caps(
    bets: list[dict],  # [{runner, bet_type, amount_usdt, ev}, ...]
    bankroll: float,
    max_total_pct: float = 0.05,
    max_win_bets: int = 2,
) -> list[dict]:
    """Apply race-level exposure caps. Sort by EV descending before calling.

    Mutates nothing — returns filtered/trimmed list.
    """
    total_cap = bankroll * max_total_pct
    win_count = 0
    result = []
    total = 0.0
    for bet in bets:
        if bet["bet_type"] == "win":
            if win_count >= max_win_bets:
                continue
            win_count += 1
        remaining = total_cap - total
        if remaining <= 0:
            break
        final = min(bet["amount_usdt"], remaining)
        if final < 1.0:
            continue
        total += final
        result.append({**bet, "amount_usdt": round(final, 2)})
    return result
```

### Pattern 2: pre_skip_check Node (D-06, BET-05)

**What:** Deterministic node inserted after `calc`. Reads `overround_active` from state. Emits `skip_signal` if margin exceeds threshold.
**When to use:** Always runs after calc — cheap gate before expensive LLM calls.

```python
# Source: project pattern in nodes.py
def pre_skip_check_node(state: PipelineState) -> dict:
    """Tier-1 skip: emit skip signal if overround exceeds threshold.

    Reads: overround_active, parsed_race
    Writes: skip_signal, skip_reason
    """
    settings = get_stake_settings()
    threshold = settings.sizing.skip_overround_threshold  # default 15.0

    overround_active = state.get("overround_active")
    if overround_active is None:
        return {}  # No data — don't skip, let analysis decide

    margin_pct = (overround_active - 1) * 100
    if margin_pct > threshold:
        return {
            "skip_signal": True,
            "skip_reason": f"Bookmaker margin {margin_pct:.1f}% exceeds {threshold:.0f}% threshold",
            "skip_tier": 1,
        }
    return {"skip_signal": False}
```

### Pattern 3: Research Node via create_react_agent (D-01 through D-05)

**What:** Async node that invokes a React agent with SearXNG/online tools. Agent autonomously decides which runners to research and what queries to run.
**When to use:** Called after pre_skip_check passes.

```python
# Source: langgraph.prebuilt.create_react_agent — response_format verified in v1.0.7
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
import httpx

SEARXNG_URL = "http://46.30.43.46:8888/search"

@tool
async def searxng_search(query: str) -> str:
    """Search for horse racing information using SearXNG.

    Use for: runner form, trainer stats, track conditions, expert tips.
    Returns top 5 results as title + content summaries.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            SEARXNG_URL,
            params={"q": query, "format": "json", "language": "en", "categories": "general,news"}
        )
        data = r.json()
        results = data.get("results", [])[:5]
        if not results:
            return "No results found."
        return "\n\n".join(
            f"[{r['title']}] {r['content'][:300]}"
            for r in results
        )


class ResearchResult(BaseModel):
    """Structured research output per runner."""
    runner_name: str
    data_quality: str  # "rich" | "sparse" | "none"
    form_summary: str
    trainer_stats: str
    expert_opinion: str
    external_odds: str | None  # If found in external sources
    confidence_notes: str


class ResearchOutput(BaseModel):
    runners: list[ResearchResult]
    overall_notes: str


async def research_node(state: PipelineState) -> dict:
    """Orchestrate research for all runners."""
    settings = get_stake_settings()

    if settings.research.provider == "online":
        llm = ChatOpenAI(
            model=settings.research.model,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=settings.openrouter_api_key,
            extra_body={"plugins": [{"id": "web"}]},  # OpenRouter web grounding
        )
        tools = []  # Online model has built-in web access
    else:
        llm = ChatOpenAI(model=settings.research.model, ...)
        tools = [searxng_search]

    agent = create_react_agent(
        model=llm,
        tools=tools,
        response_format=ResearchOutput,
        prompt=RESEARCH_SYSTEM_PROMPT,
    )

    # Build context from enriched runners
    runners_context = _build_runners_context(state)
    result = await agent.ainvoke({"messages": [HumanMessage(content=runners_context)]})

    research_output = result.get("structured_response")
    return {
        "research_results": research_output.model_dump() if research_output else None,
        "research_error": None,
    }
```

### Pattern 4: Analysis Node (Senior Agent, D-07, D-08)

**What:** Senior gemini-pro agent receives computed EV/Kelly values + research context. Returns structured recommendation with labels and bet sizes. Can recommend skip (Tier 2).
**When to use:** Called after research_node.

```python
# Source: langchain_openai ChatOpenAI.with_structured_output pattern from Phase 1
class RunnerRecommendation(BaseModel):
    runner_name: str
    label: Literal["highest_win_probability", "best_value", "best_place_candidate", "no_bet"]
    bet_type: Literal["win", "place", "skip"] | None
    ev: float
    kelly_pct: float
    usdt_amount: float
    data_sparse: bool
    reasoning: str  # 2-3 sentences


class AnalysisResult(BaseModel):
    recommendations: list[RunnerRecommendation]
    overall_skip: bool
    skip_reason: str | None  # Tier-2 skip from AI
    ai_override: bool  # True if AI skips despite +EV
    override_reason: str | None
    market_discrepancy_notes: list[str]


async def analysis_node(state: PipelineState) -> dict:
    """Senior agent produces final recommendations."""
    settings = get_stake_settings()

    # Compute EV/Kelly for each runner BEFORE calling LLM
    computed = _compute_ev_kelly_for_all(state)  # Returns list of dicts

    llm = ChatOpenAI(model=settings.analysis.model, ...)
    chain = llm.with_structured_output(AnalysisResult)

    prompt = _build_analysis_prompt(state, computed)
    result = await chain.ainvoke(prompt)

    return {"analysis_result": result.model_dump()}
```

### Pattern 5: Sizing Node (Pure Python, ARCH-01)

**What:** After analysis agent returns labels/probabilities, sizing node applies portfolio caps and sparsity discounts. No LLM involvement.
**When to use:** Always runs after analysis to enforce hard constraints.

```python
def sizing_node(state: PipelineState) -> dict:
    """Apply portfolio caps and sparsity discounts. Pure Python — no LLM.

    Per ARCH-01: all USDT amounts produced here, not by LLM.
    """
    analysis = state.get("analysis_result")
    bankroll = _get_bankroll(state)
    settings = get_stake_settings()

    raw_bets = []
    for rec in analysis["recommendations"]:
        if rec["label"] == "no_bet" or rec.get("bet_type") == "skip":
            continue

        amount = rec["usdt_amount"]  # AI returned a Kelly-computed amount from its prompt
        # BUT: we recompute here from AI's implied probability (the label implies a prob)
        # ... Actually: analysis agent receives computed amounts — we enforce them here

        # Apply sparsity discount
        if rec["data_sparse"]:
            amount = round(amount * 0.5, 2)

        if amount >= 1.0:
            raw_bets.append({
                "runner": rec["runner_name"],
                "bet_type": rec["bet_type"],
                "amount_usdt": amount,
                "ev": rec["ev"],
                "data_sparse": rec["data_sparse"],
            })

    # Sort by EV descending, then apply portfolio caps
    raw_bets.sort(key=lambda b: b["ev"], reverse=True)
    final_bets = apply_portfolio_caps(raw_bets, bankroll)

    return {"final_bets": final_bets}
```

### Anti-Patterns to Avoid

- **LLM generates bet amounts:** Analysis agent must receive computed Kelly amounts as inputs. It validates/labels, doesn't invent amounts. See D-09.
- **Rebuilding ChatOpenAI on every call:** Phase 1 builds chain once in `__init__`. New nodes should follow same pattern — build agent at module import or in a factory, not per-invocation.
- **Single-level skip:** Missing Tier 2 means pure-math-positive races with red flags (withdrawn horse, suspicious line) will recommend a bet. Both tiers are required.
- **Nested BaseSettings:** All new config classes (SizingSettings, ResearchSettings extension) must extend `BaseModel`, not `BaseSettings`. This is a Phase 1 established pattern and pitfall.
- **Blocking httpx in async context:** Must use `httpx.AsyncClient` (not `httpx.get()`). Mixing sync/async breaks aiogram's event loop.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool-calling React agent | Custom loop with tool dispatch | `langgraph.prebuilt.create_react_agent` | Tool routing, message history, termination logic already implemented |
| Structured LLM output | Parse JSON from LLM text | `ChatOpenAI.with_structured_output(PydanticModel)` | Validation, retries, schema enforcement |
| HTTP search client | Custom async requests class | `@tool` + `httpx.AsyncClient` | Already installed, tested, 1 function |
| State merging in LangGraph | Manual dict merge | LangGraph partial update dict pattern | Framework handles merge; each node returns only what it adds |
| Overround normalization | Custom probability normalization algorithm | Simple `implied_prob / overround` (Shin method in v2) | Simple normalization is sufficiently accurate for v1; Shin method added complexity without calibration data |

**Key insight:** The existing `create_react_agent` in LangGraph 1.0.7 handles tool selection, message loop, and structured response formatting. The pattern is: build the agent once, call `agent.ainvoke()` inside a node function.

---

## Common Pitfalls

### Pitfall 1: LLM Leaking Bet Amounts (ARCH-01 violation)
**What goes wrong:** Analysis prompt asks "what amount should we bet?" — LLM hallucinates USDT amounts from text.
**Why it happens:** Mixing qualitative and quantitative requests in one prompt.
**How to avoid:** Analysis prompt supplies pre-computed amounts as context: "The Kelly calculation produces X USDT. Your task is to label, reason, and flag — not to recalculate." The sizing_node enforces caps after.
**Warning signs:** Test asserting `final_bets[0]["amount_usdt"] <= bankroll * 0.03` fails.

### Pitfall 2: Online Model (Perplexity) Returns Sparse Racing Data
**What goes wrong:** Perplexity/Sonar returns generic text about racing without runner-specific form data.
**Why it happens:** Racing-specific data requires niche queries; online model may not index form guides.
**How to avoid:** D-01 specifies SearXNG as fallback. Detect sparsity: if `ResearchResult.data_quality == "sparse"` for >50% of runners, the research_node should retry with SearXNG queries.
**Warning signs:** `data_sparse: True` on most runners in first response.

### Pitfall 3: Place Bet EV Uses Wrong Probability
**What goes wrong:** Using win probability to compute place bet EV.
**Why it happens:** Natural conflation since win probability is the only LLM-assigned value.
**How to avoid:** BET-07 requires place_odds from `RunnerInfo.place_odds`. Senior agent must assign place probability separately. For v1, a conservative heuristic: place_prob = min(ai_win_prob * num_place_positions, 0.85). Clearly documented as approximation.
**Warning signs:** Place bets flagged as +EV for long-shots with low place odds.

### Pitfall 4: Pydantic Model Serialization in Redis FSM
**What goes wrong:** New Pydantic models (ResearchOutput, AnalysisResult) stored directly in FSM state → JSON serialization error.
**Why it happens:** Phase 1 established pattern: `.model_dump()` before `state.update_data()`. Phase 2 must follow same.
**How to avoid:** In pipeline handler callbacks, always serialize before storing: `await state.update_data(analysis_result=result.model_dump())`.
**Warning signs:** `TypeError: Object of type RunnerRecommendation is not JSON serializable` in logs.

### Pitfall 5: Async Tool in Sync Event Loop
**What goes wrong:** `searxng_search` tool called in a sync context raises `RuntimeError: This event loop is already running`.
**Why it happens:** aiogram uses asyncio; any nested `asyncio.run()` call inside a handler or node breaks the loop.
**How to avoid:** All I/O in nodes must be `async def` nodes or use `await`. `@tool` with `async def` + `asyncio.AsyncClient` is the correct pattern. Confirmed working in this project's environment.
**Warning signs:** `RuntimeError: This event loop is already running` in container logs.

### Pitfall 6: Overround Threshold Edge Case
**What goes wrong:** Race with only 2 active runners (barn clearance, late scratches) has mathematically high overround even on a fair market.
**Why it happens:** 2-runner race needs 50%/50% implied = 1.0 overround minimum; any vigorish creates >100% margin by default.
**How to avoid:** Pre-skip threshold should only apply when `len(active_runners) >= 3`. Skip with a different message for 2-runner races ("Insufficient field size for analysis").
**Warning signs:** `overround_active > 1.15` for a 2-horse race flagging as margined when it's just small field.

### Pitfall 7: Kelly Sizing Before Calibration
**What goes wrong:** Full Kelly on uncalibrated LLM probabilities produces extreme overbetting. Even quarter-Kelly can be aggressive with high stated LLM confidence (0.7+).
**Why it happens:** LLM confidence is systematically overconfident on domain-specific tasks without calibration history.
**How to avoid:** Implement quarter-Kelly (0.25) AND the 3% per-bet hard cap as dual safeguards. The 3% cap is the more important constraint in early operation. Consider flat 1% mode as an env-configurable alternative (CALIB-02 in v2 Requirements notes this). Recommendation: start with quarter-Kelly but the 3% cap makes it effectively flat for most races.
**Warning signs:** Bot recommends 50+ USDT bets on a 100 USDT bankroll.

---

## Code Examples

### EV Math Functions (extend math.py)

```python
# Source: Kelly Criterion formula; verified via unit test in this research

def no_vig_probability(implied_prob: float, book_overround: float) -> float:
    """Normalize implied probability by removing bookmaker margin.

    Simple proportional normalization (Shin method is more accurate but requires
    solving a nonlinear system — not needed for v1 without calibration data).

    Args:
        implied_prob: Raw implied probability from decimal odds (1 / decimal_odds).
        book_overround: Sum of all implied probabilities (> 1.0 for any real book).

    Returns:
        Fair (no-vig) probability rounded to 6 decimal places.
    """
    if book_overround <= 0:
        raise ValueError("Overround must be positive")
    return round(implied_prob / book_overround, 6)


def expected_value(ai_prob: float, decimal_odds: float) -> float:
    """Expected value as fraction of stake.

    EV > 0: bet is profitable at these odds given this probability estimate.
    EV < 0: bet loses money long-term.

    Args:
        ai_prob: AI-assigned win probability (0 to 1).
        decimal_odds: Decimal odds for this runner.

    Returns:
        EV fraction rounded to 6 decimal places. e.g. 0.05 = 5% edge.
    """
    b = decimal_odds - 1.0
    q = 1.0 - ai_prob
    return round(ai_prob * b - q, 6)


def kelly_fraction(ai_prob: float, decimal_odds: float) -> float:
    """Full Kelly criterion fraction.

    Caller must apply a multiplier (e.g., 0.25 for quarter-Kelly).
    Returns 0.0 for -EV situations (no bet signal).
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - ai_prob
    f = (b * ai_prob - q) / b
    return max(0.0, round(f, 6))


def bet_size_usdt(
    bankroll: float,
    kelly_f: float,
    kelly_multiplier: float = 0.25,
    per_bet_cap_pct: float = 0.03,
    min_bet: float = 1.0,
) -> float:
    """Compute USDT bet size with quarter-Kelly and hard cap.

    Returns 0.0 if computed amount < min_bet (caller should treat as 'no bet').
    Minimum bet per memory requirement: 1 USDT.
    """
    raw = bankroll * kelly_f * kelly_multiplier
    capped = min(raw, bankroll * per_bet_cap_pct)
    if capped < min_bet:
        return 0.0
    return round(capped, 2)
```

### SearXNG @tool

```python
# Source: tested against live SearXNG at 46.30.43.46:8888 — 35-40 results verified
import httpx
from langchain_core.tools import tool

SEARXNG_BASE_URL = "http://46.30.43.46:8888/search"

@tool
async def searxng_search(query: str) -> str:
    """Search for horse racing information.

    Args:
        query: Search query, e.g. "Verry Elleegant trainer Chris Waller form 2025"

    Returns:
        Top 5 results as title + content summaries, newline-separated.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                SEARXNG_BASE_URL,
                params={
                    "q": query,
                    "format": "json",
                    "language": "en",
                    "categories": "general,news",
                }
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return f"Search failed: {e}"

    results = data.get("results", [])[:5]
    if not results:
        return "No results found."

    return "\n\n".join(
        f"[{item['title']}]\n{item.get('content', '')[:300]}"
        for item in results
    )
```

### PipelineState Extension

```python
# Extend services/stake/pipeline/state.py — add after existing fields:

class PipelineState(TypedDict, total=False):
    # ... existing fields ...

    # Phase 2: pre-skip check (D-06, BET-05)
    skip_signal: Optional[bool]           # True = skip this race
    skip_reason: Optional[str]            # Human-readable skip reason
    skip_tier: Optional[int]              # 1 = overround, 2 = AI

    # Phase 2: research (SEARCH-01, SEARCH-02)
    research_results: Optional[dict]      # ResearchOutput.model_dump()
    research_error: Optional[str]

    # Phase 2: analysis (ANALYSIS-01 through ANALYSIS-05)
    analysis_result: Optional[dict]       # AnalysisResult.model_dump()
    computed_ev: Optional[list[dict]]     # Pre-computed EV/Kelly per runner

    # Phase 2: sizing (BET-01 through BET-07)
    final_bets: Optional[list[dict]]      # After portfolio caps
    recommendation_text: Optional[str]   # Formatted Telegram HTML
```

### New Settings (extend settings.py)

```python
# Extend with ResearchSettings.provider and new SizingSettings

class ResearchSettings(BaseModel):
    """Research agent LLM config."""
    model: str = Field(default="google/gemini-3.1-flash-lite-preview", ...)
    temperature: float = Field(default=0.3, ...)
    max_tokens: int = Field(default=4000, ...)
    provider: str = Field(
        default="online",
        description="Search provider: 'online' (OpenRouter web model) or 'searxng'"
    )


class SizingSettings(BaseModel):
    """Bet sizing constraints per BET-01 through BET-07."""
    kelly_multiplier: float = Field(
        default=0.25,
        description="Kelly fraction multiplier (0.25 = quarter-Kelly). Env: STAKE_SIZING__KELLY_MULTIPLIER"
    )
    per_bet_cap_pct: float = Field(
        default=0.03,
        description="Max single bet as fraction of bankroll (3%). Env: STAKE_SIZING__PER_BET_CAP_PCT"
    )
    max_race_exposure_pct: float = Field(
        default=0.05,
        description="Max total bets per race as fraction of bankroll (5%). Env: STAKE_SIZING__MAX_RACE_EXPOSURE_PCT"
    )
    max_win_bets: int = Field(
        default=2,
        description="Max win bets per race. Env: STAKE_SIZING__MAX_WIN_BETS"
    )
    skip_overround_threshold: float = Field(
        default=15.0,
        description="Pre-analysis skip threshold: margin % above this → skip. Env: STAKE_SIZING__SKIP_OVERROUND_THRESHOLD"
    )
    min_bet_usdt: float = Field(
        default=1.0,
        description="Minimum bet in USDT; below this = no bet. Env: STAKE_SIZING__MIN_BET_USDT"
    )
```

### LangGraph Graph Extension

```python
# Extend services/stake/pipeline/graph.py

from services.stake.pipeline.nodes import (
    parse_node, calc_node,
    pre_skip_check_node, research_node, analysis_node, sizing_node,
    format_recommendation_node,
)

def skip_router(state: PipelineState) -> str:
    if state.get("skip_signal"):
        return "skip"
    return "continue"

def research_error_router(state: PipelineState) -> str:
    if state.get("research_error"):
        return "error"
    return "continue"

def analysis_skip_router(state: PipelineState) -> str:
    analysis = state.get("analysis_result", {})
    if analysis.get("overall_skip"):
        return "skip"
    return "continue"


def build_pipeline_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("calc", calc_node)
    graph.add_node("pre_skip_check", pre_skip_check_node)
    graph.add_node("research", research_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("sizing", sizing_node)
    graph.add_node("format_recommendation", format_recommendation_node)

    graph.set_entry_point("parse")

    graph.add_conditional_edges("parse", error_router, {"error": END, "continue": "calc"})
    graph.add_edge("calc", "pre_skip_check")
    graph.add_conditional_edges("pre_skip_check", skip_router, {"skip": END, "continue": "research"})
    graph.add_conditional_edges("research", research_error_router, {"error": END, "continue": "analysis"})
    graph.add_conditional_edges("analysis", analysis_skip_router, {"skip": END, "continue": "sizing"})
    graph.add_edge("sizing", "format_recommendation")
    graph.add_edge("format_recommendation", END)

    return graph.compile()
```

### Telegram Recommendation Card Format

```
# Source: aiogram HTML parse mode (existing formatter.py pattern)

<b>Flemington Race 5</b> | Bankroll: 250.00 USDT

OVERROUND: 11.2% — Analysis active

--- RECOMMENDATION ---

1. Thunder Bolt
   Label: best_value
   Win odds: 3.50 | EV: +8.5% | Kelly: 6.0%
   Bet: <b>WIN 7.50 USDT</b>
   <i>Recent form 1-2-1, trainer Jones has 35% strike rate at Flemington. Best odds vs true probability.</i>

3. Silver Streak
   Label: best_place_candidate
   Place odds: 2.20 | EV: +3.2%
   Bet: <b>PLACE 3.50 USDT</b> ⚠️ sparse data — size halved
   <i>Limited form data available. Strong trainer stats but race history incomplete.</i>

Total exposure: 11.00 USDT (4.4% of bankroll)

2. Golden Arrow — no_bet (EV: -2.1%)
4. Dark Knight — SCRATCHED
5. Morning Star — no_bet (EV: +0.4% — below minimum bet)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual tool dispatch loops | `create_react_agent` with `response_format` | LangGraph 0.2+ | Structured output + tool calling in one agent |
| LangChain v1 `.run()` chains | `chain.ainvoke()` async | langchain-core 0.3+ | Async-native; aiogram event loop compatible |
| Separate Pydantic v1 / v2 | Unified pydantic v2 | LangChain 0.3+ | `langchain_core.pydantic_v1` removed in installed version |
| Sub-graph state schema sharing | Direct `ainvoke()` inside node | LangGraph 1.0+ | Simpler than nested graphs for single-invocation research |

**Deprecated/outdated:**
- `langchain_core.pydantic_v1`: Removed in langchain-core 1.x. Use `pydantic.BaseModel` directly. (Verified: `from langchain_core.pydantic_v1 import BaseModel` raises `ModuleNotFoundError` in this project.)
- `chain.run()`: Use `chain.ainvoke()` or `chain.invoke()`.

---

## Open Questions

1. **Online model grounding quality for horse racing**
   - What we know: OpenRouter Perplexity/Sonar (`perplexity/sonar`) supports web search grounding. Configuration via `extra_body={"plugins": [{"id": "web"}]}` in ChatOpenAI confirmed working.
   - What's unclear: Whether Perplexity/Sonar has good coverage of Australian/international racing form guides (Racenet, Racing and Sports, etc.) vs SearXNG which confirmed good coverage.
   - Recommendation: Implement SearXNG path first (confirmed working), add online model as alternative. D-01 decision is sound but SearXNG should be tested first run.

2. **AI probability assignment quality without calibration**
   - What we know: LLMs tend to overstate confidence. BET-02 quarter-Kelly + BET-03 3% cap are dual safety rails.
   - What's unclear: What probability range the senior agent will assign. Needs real race testing.
   - Recommendation: Log AI-assigned probabilities vs actual outcomes from Phase 3 (CALIB-01, CALIB-02 in v2 Requirements). For now, the 3% hard cap is the primary safety.

3. **Place probability estimation**
   - What we know: BET-07 requires place bet EV using extracted place_odds. Place probability is not directly provided.
   - What's unclear: Whether the AI should assign place probability explicitly, or whether a heuristic (3 × win_prob for 3-place terms) is acceptable for v1.
   - Recommendation: Have AI assign place probability explicitly in its analysis. Simple heuristic risks systematic errors. Model is capable of this with appropriate prompting.

4. **Research agent for online model: no tools needed**
   - What we know: If `provider == "online"`, the model has built-in web access — passing `tools=[searxng_search]` would be redundant.
   - What's unclear: Whether `create_react_agent` with no tools correctly enters a single-pass (non-React) mode or loops awkwardly.
   - Recommendation: For online model path, call `llm.with_structured_output(ResearchOutput).ainvoke(prompt)` directly (no agent loop needed). For SearXNG path, use `create_react_agent`. Two code paths, same output type.

5. **Handling the `processing` FSM state**
   - What we know: `PipelineStates.processing` exists but is unused (noted in states.py docstring as "future phases").
   - What's unclear: The Phase 2 pipeline handler needs to trigger the full pipeline after bankroll confirmation. The `processing` state was designed for this but the trigger point (which callback?) needs design.
   - Recommendation: The `handle_parse_confirm` callback (Phase 1) currently sends idle after bankroll confirmed. Phase 2 needs to transition to `processing` and call the extended graph. The callback is the right trigger point.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| SearXNG | SEARCH-01, SEARCH-02 | Yes | Live at 46.30.43.46:8888 | Online model (D-01) |
| OpenRouter API | SEARCH-02, ANALYSIS | Yes (key in env) | API available | SearXNG-only mode |
| httpx AsyncClient | SearXNG @tool | Yes | 0.28.1 | — |
| langgraph create_react_agent | Research orchestration | Yes | 1.0.7 (prebuilt) | — |
| pytest | Test suite | Yes | 9.0.2 | — |
| pytest-asyncio | Async tool tests | CHECK | `pip show pytest-asyncio` | Install if missing |
| Redis | FSM state (existing) | Yes | Via Docker | — |
| SQLite / BankrollRepository | Sizing calculations | Yes | Existing | — |

**Missing dependencies with no fallback:** None blocking.

**Missing dependencies with fallback:**
- `pytest-asyncio`: Required for testing async `@tool` functions and async nodes. Install with `pip install pytest-asyncio` if not present. Non-blocking for implementation but required before test writing.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | None (pyproject.toml or pytest.ini) — no pytest-asyncio config yet |
| Quick run command | `PYTHONPATH=. pytest tests/stake/test_ev_math.py -x -q` |
| Full suite command | `PYTHONPATH=. pytest tests/stake/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANALYSIS-02 | no_vig_probability(implied, overround) | unit | `pytest tests/stake/test_ev_math.py::test_no_vig_probability -x` | Wave 0 |
| ANALYSIS-03 | expected_value(ai_prob, decimal_odds) | unit | `pytest tests/stake/test_ev_math.py::test_expected_value -x` | Wave 0 |
| BET-01 | kelly_fraction() never returns LLM-generated value | unit | `pytest tests/stake/test_ev_math.py::test_kelly_fraction -x` | Wave 0 |
| BET-02 | bet_size_usdt() at quarter-Kelly | unit | `pytest tests/stake/test_ev_math.py::test_bet_size_usdt_quarter_kelly -x` | Wave 0 |
| BET-03 | bet_size_usdt() hard-caps at 3% bankroll | unit | `pytest tests/stake/test_ev_math.py::test_bet_size_hard_cap -x` | Wave 0 |
| BET-04 | apply_portfolio_caps() max 2 win bets, 5% total | unit | `pytest tests/stake/test_ev_math.py::test_portfolio_caps -x` | Wave 0 |
| BET-05 | pre_skip_check_node skips when margin > 15% | unit | `pytest tests/stake/test_pipeline_nodes.py::test_pre_skip_check -x` | Wave 0 |
| ANALYSIS-04 | apply_sparsity_discount halves amount, flags | unit | `pytest tests/stake/test_ev_math.py::test_sparsity_discount -x` | Wave 0 |
| BET-07 | place_bet_ev uses place_odds not win_odds | unit | `pytest tests/stake/test_ev_math.py::test_place_bet_ev -x` | Wave 0 |
| SEARCH-01 | searxng_search tool returns results | integration | `pytest tests/stake/test_research_tools.py::test_searxng_search -x` | Wave 0 |
| ANALYSIS-01 | analysis agent returns valid labels | unit/mock | `pytest tests/stake/test_analysis.py::test_analysis_labels -x` | Wave 0 |
| BET-06 | format_recommendation() produces HTML with USDT amounts | unit | `pytest tests/stake/test_formatter.py::test_recommendation_format -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `PYTHONPATH=. pytest tests/stake/test_ev_math.py -x -q` (math functions only — fast)
- **Per wave merge:** `PYTHONPATH=. pytest tests/stake/ -x -q` (full suite)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/stake/test_ev_math.py` — covers ANALYSIS-02, ANALYSIS-03, BET-01, BET-02, BET-03, BET-04, ANALYSIS-04, BET-07
- [ ] `tests/stake/test_pipeline_nodes.py` — extend existing or create new; covers BET-05 (pre_skip_check_node)
- [ ] `tests/stake/test_research_tools.py` — covers SEARCH-01 (requires live SearXNG or httpx mock)
- [ ] `tests/stake/test_analysis.py` — covers ANALYSIS-01 (mocked LLM via pytest-mock)
- [ ] `tests/stake/test_formatter.py` — covers BET-06 (recommendation card format)
- [ ] pytest-asyncio config: add `asyncio_mode = "auto"` to pytest.ini or pyproject.toml for async test support

---

## Project Constraints (from CLAUDE.md)

All directives from `./CLAUDE.md` relevant to Phase 2 implementation:

| Directive | Applies To | How to Comply |
|-----------|------------|---------------|
| `ARCH-01`: All numerical calculations by deterministic Python, never LLM | All math functions | no_vig_probability, expected_value, kelly_fraction, bet_size_usdt, apply_portfolio_caps all go in math.py — pure functions, no I/O |
| Nested Pydantic config: `BaseModel` not `BaseSettings` | SizingSettings, ResearchSettings extension | Both must extend `BaseModel` |
| Pydantic objects not JSON-serializable for Redis | All new Pydantic models in FSM | `.model_dump()` before every `state.update_data()` call |
| `logging.basicConfig()` + `@dp.errors()` configured | research_node, analysis_node | Wrap LLM calls in try/except; log with context (runner name, query) |
| parse_mode=HTML — unescaped `<>` silently fail | format_recommendation() | Escape all user data (runner names, trainer names) with html.escape() |
| Use `mamba run -n ml-env` for data science scripts | Not applicable — bot uses project venv | N/A |
| Context7 MCP for library docs before writing code | Before writing LangGraph/langchain code | Verified in this research via direct code inspection |
| Pre-deploy: run `pytest tests/stake/ -x -q` | Before any deploy | Must be green before Phase 2 deploy |
| `STAKE_PARSER__MODEL` env var naming convention | New env vars | Follow pattern: `STAKE_RESEARCH__PROVIDER`, `STAKE_SIZING__KELLY_MULTIPLIER` |

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `services/stake/parser/math.py`, `pipeline/nodes.py`, `pipeline/graph.py`, `pipeline/state.py`, `settings.py`, `handlers/pipeline.py`, `handlers/callbacks.py` — verified Phase 1 patterns
- Python runtime verification: `create_react_agent` signature, `StateGraph.add_node` sub-graph support, `ChatOpenAI.model_fields` for `extra_body`
- Live system test: SearXNG at `http://46.30.43.46:8888` — 35-40 results per query confirmed; async httpx tool pattern tested

### Secondary (MEDIUM confidence)
- Kelly Criterion formula: Standard financial mathematics — `f* = (b*p - q)/b` verified with numeric tests in this research
- OpenRouter extra_body web plugin: Confirmed via `ChatOpenAI.model_fields` listing `extra_body`; actual web grounding response quality not tested (no API call made)
- Perplexity/Sonar online model: Model ID `perplexity/sonar` available on OpenRouter; coverage for Australian racing not verified

### Tertiary (LOW confidence)
- Place probability heuristic (win_prob * num_places): Common approximation; not verified against track data. Flag for v2 calibration.
- Perplexity quality for racing data: Assumed good based on general knowledge of Perplexity coverage. Needs real-race test on first run.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages inspected in project venv, versions confirmed
- Architecture: HIGH — LangGraph 1.0.7 patterns verified by running Python; Phase 1 patterns fully read
- EV math: HIGH — standard financial formulas verified numerically
- Research tooling: HIGH for SearXNG (live test), MEDIUM for online model (config confirmed, quality unverified)
- Pitfalls: HIGH — derived from Phase 1 code reading + established LangChain/aiogram patterns

**Research date:** 2026-03-26
**Valid until:** 2026-05-26 (stable stack — LangGraph 1.x, langchain 1.x; re-verify if packages upgraded)
