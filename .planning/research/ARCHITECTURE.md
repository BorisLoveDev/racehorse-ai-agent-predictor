# Architecture Research: AI Betting Advisor

**Domain:** Interactive AI betting advisor with user-in-the-loop pipeline
**Researched:** 2026-03-23
**Overall confidence:** HIGH (patterns drawn from existing codebase + verified LangGraph/aiogram docs)

---

## Component Overview

The new `stake-advisor` service sits alongside the existing five-service system as a **6th Docker service**. It does NOT replace or modify existing services.

### New Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **AdvisorBot** | `services/stake-advisor/main.py` | aiogram Dispatcher, FSM setup, Redis storage wiring |
| **PipelineRunner** | `services/stake-advisor/pipeline/runner.py` | Executes 8 steps sequentially; yields step results back to caller |
| **Pipeline Steps** | `services/stake-advisor/pipeline/steps/` | One file per step; each step is also a callable tool for agent mode |
| **SessionStore** | `services/stake-advisor/session.py` | Read/write `AdvisorSession` via aiogram RedisStorage (FSMContext) |
| **AgentExecutor** | `services/stake-advisor/agent/executor.py` | LangGraph ReAct loop that calls pipeline steps as tools (v2 only) |
| **BankrollRepo** | `services/stake-advisor/db/bankroll.py` | USDT balance CRUD in SQLite (new table, same `races.db`) |
| **MindsetStore** | `services/stake-advisor/mindset.py` | Read/write `mindset.md` on disk; inject into reflection prompt |
| **Handlers** | `services/stake-advisor/handlers/` | aiogram message + callback handlers per conversation state |
| **Keyboards** | `services/stake-advisor/keyboards.py` | Inline keyboards reusing existing aiogram patterns |

### Shared Infrastructure (reused, unchanged)

| Resource | What it provides |
|----------|-----------------|
| `src/agents/base.py` | `BaseRaceAgent`, `AgentState`, LangGraph workflow — reuse as-is |
| `src/web_search/` | `WebResearcher` with SearXNG/DuckDuckGo — call directly |
| `src/database/repositories.py` | Add new repos; don't break existing ones |
| `src/config/settings.py` | Extend with `STAKE_ADVISOR__*` prefix block |
| Redis container | Used for aiogram FSMContext storage (new keyspace, no collision) |
| SQLite `races.db` | Add `advisor_sessions`, `advisor_bankroll` tables via new migration |

---

## Data Flow

```
USER (Telegram)
    │
    │ pastes raw Stake.com text
    ▼
[STEP 1: PARSE]          Extract race name, runners, odds from raw text
    │                    → ParsedRace model
    ▼
[STEP 2: CLEAN]          LLM removes noise, normalizes runner names/odds
    │                    → CleanedRace model (or passthrough if clean enough)
    ▼
[STEP 3: SEARCH]         WebResearcher queries SearXNG for each runner
    │                    → List[SearchResult]
    ▼
[STEP 4: ANALYZE]        BaseRaceAgent-derived agent runs deep analysis
    │                    → AnalysisReport (text + confidence per runner)
    ▼
[STEP 5: BANK_FETCH]     Read current bankroll from SQLite
    │                    → BankrollState (balance, currency, unit_size)
    ▼
[STEP 6: BET_SIZE]       Kelly criterion sizing on top of AnalysisReport
    │                    → BetRecommendation (skip / exact USDT amounts per bet type)
    ▼
[STEP 7: FORMAT]         Compose Telegram message with bets + bankroll header
    │                    → FormattedMessage sent to user
    ▼
USER (Telegram)
    │
    │ pastes race result (later, maybe hours)
    ▼
[STEP 8: REFLECT]        Evaluate prediction, update bankroll, append to mindset.md
                         → ReflectionSummary sent to user
```

Each step receives an `AdvisorSession` (typed state object) and returns an updated `AdvisorSession`.

---

## Dual-Mode Design

### The Pattern: Steps as Async Functions AND LangChain Tools

Every pipeline step is a pure async function:

```python
async def step_parse(session: AdvisorSession) -> AdvisorSession: ...
async def step_search(session: AdvisorSession) -> AdvisorSession: ...
```

**Pipeline mode** calls them in sequence:

```python
PIPELINE_STEPS = [step_parse, step_clean, step_search, step_analyze,
                  step_bank_fetch, step_bet_size, step_format]

async def run_pipeline(session: AdvisorSession, on_step_done=None) -> AdvisorSession:
    for step_fn in PIPELINE_STEPS:
        session = await step_fn(session)
        if on_step_done:
            await on_step_done(session)  # streams intermediate result to Telegram
    return session
```

**Agent mode** wraps each step as a LangChain `@tool`:

```python
from langchain_core.tools import tool

@tool
async def parse_race_data(raw_text: str) -> str:
    """Parse raw Stake.com race page text into structured race data."""
    session = AdvisorSession(raw_input=raw_text)
    session = await step_parse(session)
    return session.parsed_race.model_dump_json()
```

The `AgentExecutor` in v2 provides these tools to a LangGraph ReAct loop.

### Why This Pattern Works

- Steps remain pure async functions — testable in isolation
- No code duplication between modes
- Pipeline ships in v1; agent mode addable in v2 without rewriting steps

---

## State Management

### Decision: aiogram RedisStorage for FSMContext

```python
from aiogram.fsm.storage.redis import RedisStorage

storage = RedisStorage(
    redis=aioredis.from_url("redis://redis:6379"),
    state_ttl=86400,   # 24h
    data_ttl=86400,
)
```

**What lives in FSMContext:**
- Current `FSMState` (e.g., `AdvisorStates.waiting_for_result`)
- `AdvisorSession` serialized as JSON

**What lives in SQLite:**
- Bankroll balance (persistent, survives Redis flush)
- Completed session records (for P&L stats)

### Session State Object

```python
class AdvisorSession(BaseModel):
    raw_input: str = ""
    parsed_race: Optional[ParsedRace] = None
    cleaned_race: Optional[CleanedRace] = None
    search_results: Optional[list[SearchResult]] = None
    analysis_report: Optional[AnalysisReport] = None
    bankroll: Optional[BankrollState] = None
    bet_recommendation: Optional[BetRecommendation] = None
    result_input: Optional[str] = None
    reflection: Optional[ReflectionSummary] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    race_id: Optional[str] = None
```

### FSM States

```python
class AdvisorStates(StatesGroup):
    idle = State()
    waiting_for_race_input = State()
    pipeline_running = State()      # lock: prevents duplicate submissions
    waiting_for_result = State()    # recommendation sent, awaiting result paste
    reflecting = State()
```

---

## Reflection System

### What mindset.md Is

A persistent file the AI reads before each analysis and appends to after each result evaluation. Injected into the system prompt as "institutional memory."

### File Location

```yaml
# docker-compose.yml
stake-advisor:
  volumes:
    - advisor_data:/data/advisor
# mindset.md lives at /data/advisor/mindset.md
```

### Structure

```markdown
# Advisor Mindset

## Betting Principles
- Stake.com odds on international races have higher margin — raise skip threshold
- Short fields (< 7 runners) show better prediction accuracy

## Track Notes
- Flemington 1200m: barrier 1-4 heavily favored on good tracks

## Recent Reflections

### 2026-03-21 | Race: Flemington R3
**Predicted:** Horse 3 to win (confidence 0.72)
**Actual:** Horse 7 won
**P&L:** -$1.80
**Reflection:** Underestimated closer in fast-pace scenario.
**Principle added:** Exclude wet-track-specialist form when track is rated Good/Firm.
```

### MindsetStore Interface

```python
class MindsetStore:
    def read(self, max_reflections: int = 20) -> str: ...
    def append_reflection(self, entry: ReflectionEntry) -> None: ...
    def update_principles(self, new_principles: list[str]) -> None: ...
```

Inject only last 20 reflections + all principles into analysis prompt.

---

## Suggested Build Order

### Phase 1: Foundation
1. `AdvisorSession` model
2. `BankrollRepo` — SQLite migration + CRUD
3. `MindsetStore` — file read/write
4. FSM setup — `AdvisorStates`, RedisStorage wiring

### Phase 2: Pipeline Steps
5. `step_parse` — unblocks all downstream
6. `step_clean` — passthrough stub initially
7. `step_search` — wraps existing `WebResearcher`
8. `step_analyze` — adapts `BaseRaceAgent` to `AdvisorSession`
9. `step_bank_fetch` + `step_bet_size`
10. `step_format`

### Phase 3: Pipeline Runner + Telegram Handlers
11. `PipelineRunner` — sequential executor
12. `handlers/race_input.py` — paste handler
13. `handlers/result_input.py` — result handler

### Phase 4: Reflect + Stats
14. `step_reflect` + stats handler

### Phase 5: Agent Mode (v2)
15. `@tool` wrappers around each step
16. `AgentExecutor` — LangGraph ReAct loop
17. Mode toggle via Redis key + bot menu

---

## Component Boundaries

**Advisor service owns:** All `services/stake-advisor/`, new SQLite tables, `mindset.md` volume, Redis FSM keys.

**Borrows read-only:** `src/agents/base.py`, `src/web_search/`, `src/config/settings.py`, `src/logging_config.py`.

**Never touches:** `services/monitor/`, `services/orchestrator/`, `services/results/`, existing Telegram service, `tabtouch_parser.py`, existing DB tables.

---

## Sources

- [LangGraph Workflows and Agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [Pipeline of Agents Pattern — DEV Community](https://dev.to/vitaliihonchar/pipeline-of-agents-pattern-building-maintainable-ai-workflows-with-langgraph-1e50)
- [aiogram FSM Storages](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html)
- [Agentic AI Reflection Pattern — DeepLearning.AI](https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection/)
- Existing codebase: `src/agents/base.py` (LangGraph StateGraph, dual sync/async already implemented)
