# Stack Research: AI Betting Advisor Pipeline

**Project:** Stake.com Horse Racing Advisor Bot
**Researched:** 2026-03-23
**Overall Confidence:** HIGH (existing codebase + verified docs)

---

## Framework Decision (CRITICAL)

### The Surprising Finding: LangGraph Is Already Here

The existing repo (`src/agents/base.py`) already uses **LangGraph** with `StateGraph`, `TypedDict` state, and node-based pipeline orchestration. The `BaseRaceAgent` builds a 4-node graph (generate_search_queries → web_search → deep_analysis → structured_output) and runs it via `workflow.ainvoke()`. Structured output uses `llm.with_structured_output(StructuredBetOutput)` from `langchain_openai`.

This fundamentally changes the framework decision from "which to choose" to "should we continue using what exists, or replace it."

### Framework Comparison

| Criterion | LangGraph (existing) | PydanticAI v1 | Plain asyncio |
|-----------|---------------------|---------------|---------------|
| **Already in repo** | YES — `base.py`, `StateGraph` | No | Partially (Telegram service) |
| **Pipeline support** | Native (DAG of nodes) | Via `pydantic-graph` module | Manual coroutine chaining |
| **Agent mode** | Native (conditional edges, tool loops) | Native (`agent.run()` with tools) | Manual tool dispatch loop |
| **Structured output** | `llm.with_structured_output()` on ChatOpenAI | First-class `output_type=MyModel` | Manual JSON parse + validate |
| **OpenRouter compat** | YES — via `ChatOpenAI` with custom `base_url` | YES — OpenAI-compatible client | YES |
| **Type safety** | Medium (TypedDict state) | HIGH (full Pydantic v2) | Low |
| **Async native** | YES (`ainvoke`) | YES | YES |
| **Dual mode (pipeline + agent)** | YES — same graph, add conditional edges | YES — same `Agent`, toggle tools | NO — two separate implementations |
| **Maturity** | LangGraph 1.0 shipped Oct 2025 | PydanticAI v1.0 shipped Sept 2025 | N/A |
| **New dep weight** | Already installed | New dependency | No new dep |

### Recommendation: Continue with LangGraph, Extend It

**Rationale:**

1. **Zero migration cost.** LangGraph is already wired into `BaseRaceAgent`. The new service shares the same Docker image, same `src/` package, same OpenRouter pattern via `ChatOpenAI`. Replacing it would require rewriting working code with no user-facing benefit.

2. **Pipeline-first maps perfectly.** The Stake advisor's fixed pipeline (parse → research → analyse → size bet) is exactly the LangGraph DAG pattern already proven in this repo. The 4-step `StateGraph` in `base.py` is a direct template.

3. **Agent mode is a small extension.** LangGraph's conditional edges let a node route to different nodes based on LLM output. To add agent mode (v2), add a `route_next_action` node that calls the LLM with available tool descriptions and returns the next node name. The pipeline becomes a graph with a decision loop. No framework swap needed.

4. **PydanticAI is better on paper but worse in practice here.** PydanticAI v1 has cleaner type safety and a nicer API. However: (a) it is a new dependency on a memory-constrained server (2 vCPU, 4GB RAM); (b) it would split the codebase — existing agents in LangGraph, new service in PydanticAI; (c) OpenRouter compatibility requires explicit `base_url` config that is already solved in the existing `ChatOpenAI` setup.

5. **Plain asyncio is wrong for dual-mode.** Pipeline and agent mode share 90% of logic. Without a graph abstraction, you end up maintaining two divergent code paths. LangGraph gives a single representation that covers both.

**The one valid reason to consider PydanticAI:** If structured output validation failures become a recurring pain point, add `instructor` (not full PydanticAI) as a thin auto-retry wrapper. Monitor in Phase 1; switch if needed.

---

## Core Libraries

| Library | Version | Purpose | Confidence |
|---------|---------|---------|-----------|
| `langgraph` | >=1.0 (Oct 2025) | Pipeline DAG + agent mode graph | HIGH — already installed |
| `langchain-openai` | >=0.2 | `ChatOpenAI` with OpenRouter `base_url` | HIGH — already used in `base.py` |
| `langchain-core` | >=0.3 | `BaseMessage`, `ChatPromptTemplate` | HIGH — already used |
| `aiogram` | 3.x (3.25+ current) | Telegram bot, FSM state, inline keyboards | HIGH — already installed |
| `pydantic` | >=2.0 | Model validation for all structured outputs | HIGH — already installed |
| `redis` | >=5.0 | FSM state storage + pub/sub message bus | HIGH — already running on Meridian |
| `aiosqlite` | >=0.20 | Async SQLite access | MEDIUM — pattern in `repositories.py` |
| `instructor` | >=1.0 (optional) | Structured LLM output with auto-retry | MEDIUM — standby only |
| `httpx` | >=0.27 | SearXNG HTTP requests (async) | HIGH — already used |

### What NOT to Use

| Library | Verdict | Reason |
|---------|---------|--------|
| `pydantic-ai` | Skip for v1 | New dep, splits codebase, no gain over existing LangGraph + pydantic |
| `crewai` | Skip | Heavyweight multi-agent; overkill for single-user bot |
| `haystack` | Skip | NLP pipeline; wrong abstraction |
| `autogen` | Skip | Multi-agent conversation; wrong pattern |
| `keeks` / `kelly-criterion` | Skip | Library for a 5-line formula — implement inline |
| `LangChain chains` (old) | Skip | Superseded by LangGraph in this repo |
| `nest_asyncio` | Skip | Workaround for sync nodes — use `async def` from start |
| `MemoryStorage` (aiogram) | Skip | Lost on restart — use `RedisStorage` |

---

## Bankroll Management

### Recommendation: Implement Kelly Directly (No Library)

```python
def kelly_fraction(win_probability: float, decimal_odds: float) -> float:
    b = decimal_odds - 1.0  # net profit per unit staked
    p = win_probability
    q = 1.0 - p
    return max(0.0, (b * p - q) / b)

def recommended_stake(
    bankroll_usdt: float,
    win_probability: float,
    decimal_odds: float,
    fraction: float = 0.25   # quarter-Kelly by default
) -> float:
    k = kelly_fraction(win_probability, decimal_odds)
    return round(bankroll_usdt * k * fraction, 2)

def expected_value(win_probability: float, decimal_odds: float) -> float:
    return win_probability * (decimal_odds - 1.0) - (1.0 - win_probability)
```

**Quarter-Kelly (fraction=0.25) as default:** Full Kelly requires perfectly calibrated probabilities. Horse racing model error is high. Quarter-Kelly is the professional standard — reduces bet sizes 4x, dramatically lowers ruin risk. Confidence: HIGH.

---

## Conversation State (Multi-Message Telegram Flow)

### Pattern: aiogram FSM with RedisStorage

```python
from aiogram.fsm.storage.redis import RedisStorage

storage = RedisStorage(
    redis=aioredis.from_url("redis://redis:6379"),
    state_ttl=86400,   # 24h — races don't span longer
    data_ttl=86400,
)
dp = Dispatcher(storage=storage)
```

Use aiogram 3 **Scenes** to isolate pipeline handlers from global commands (available since aiogram 3.20). Prevents `/menu` and other global handlers from interrupting mid-pipeline.

**State machine:**

```python
class AdvisorPipeline(StatesGroup):
    waiting_for_paste     = State()
    parsing               = State()
    researching           = State()
    analysing             = State()
    awaiting_confirmation = State()
    awaiting_result       = State()
    reflecting            = State()
```

---

## Sources

- [PydanticAI v1 announcement](https://pydantic.dev/articles/pydantic-ai-v1) — Sept 2025
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [ZenML: PydanticAI vs LangGraph](https://www.zenml.io/blog/pydantic-ai-vs-langgraph)
- [Langfuse agent framework comparison 2025](https://langfuse.com/blog/2025-03-19-ai-agent-comparison)
- [aiogram FSM Storages docs](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html)
- [aiogram Scenes docs](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/scene.html)
- [Instructor + OpenRouter](https://python.useinstructor.com/integrations/openrouter/)
- Existing codebase: `src/agents/base.py` (LangGraph StateGraph already implemented)
