# Phase 1: Foundation and Parser - Research

**Researched:** 2026-03-24
**Domain:** aiogram 3 FSM + LangGraph pipeline + LLM structured extraction + SQLite schema
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** New standalone Docker service (`services/stake/`) — completely separate from existing telegram service, not an extension
- **D-02:** Same Telegram bot token — this service replaces the existing bot entirely
- **D-03:** Reuse existing infrastructure: Redis for pub/sub and state, SQLite for persistence, Docker Compose on Meridian
- **D-04:** Branch isolation: new `stake-advisor` branch, no changes to existing services
- **D-05:** LLM-based parser converts raw arbitrary text paste into structured output (Pydantic model)
- **D-06:** Parser model is configurable via env/config — cheap model (e.g., gemini-flash or similar), set in settings not hardcoded
- **D-07:** Full extraction — extract everything available in the paste (race-level fields, per-runner fields, market context fields as documented in CONTEXT.md)
- **D-08:** Fields not present in the paste are marked null — LLM adapts to whatever Stake.com format is pasted
- **D-09:** Derived numerical values (implied probability, overround, odds drift %, recalculated overround after scratches) calculated by deterministic Python functions — NOT by LLM (ARCH-01)
- **D-10:** Scratched runners get `status: "scratched"`, excluded from all calculations, flagged in output
- **D-11:** Parser scans paste for any balance/bankroll mention — if found, triggers confirmation branch
- **D-12:** If no bankroll in paste and no DB record — bot asks explicitly before pipeline continues
- **D-13:** `/balance` command (or menu equivalent) to set/view bankroll manually
- **D-14:** Current USDT balance shown in header of every bot response
- **D-15:** Bankroll persists in SQLite, survives bot restarts
- **D-16:** User can set desired stake size as % of bankroll
- **D-17:** Pipeline shows progressive messages — each step sends status updates
- **D-18:** Use all Telegram features: inline keyboards, reply markup, formatted messages (Markdown/HTML), callback buttons
- **D-19:** `/help` command with full explanation
- **D-20:** Statistics and bankroll accessible via dedicated menu/commands
- **D-21:** Intuitive interface — obvious without reading docs
- **D-22:** Parse confirmation step: bot displays formatted race summary, user confirms (inline keyboard) before continuing
- **D-23:** LangGraph for pipeline orchestration (already installed, supports future agent mode)
- **D-24:** FSM state persists through bot restarts (RedisStorage backend)
- **D-25:** Only one active pipeline session per user; duplicate paste triggers warning
- **D-26:** User can `/cancel` active pipeline at any time
- **D-27:** Append-only JSON-lines log file on server
- **D-28:** Each entry covers: raw input, parsed output, user confirmation/changes

### Claude's Discretion

- Specific Telegram message formatting and layout design
- FSM state names and transition diagram
- Audit log file location and rotation policy
- Error messages and recovery flows
- Exact inline keyboard layouts and button text
- How to handle ambiguous paste data (ask user vs best-guess)
- Loading/processing indicators style

### Deferred Ideas (OUT OF SCOPE)

- Web research data (Phase 2): detailed race history, jockey/trainer stats, sectional times, track bias, weather, pace maps
- Derived analysis features (Phase 2): consistency score, pace pressure score, draw advantage score
- Market movement tracking (Phase 2+): strong odds movements over time
- Statistics viewing (Phase 3): full P&L stats, period analysis, win rate, ROI
- Agent mode (v2): AGENT-01 explicitly deferred

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INPUT-01 | User can paste raw Stake.com text into Telegram chat | aiogram Message handler with F.text filter (verified) |
| INPUT-02 | User can send .txt file with race data | aiogram Document handler with F.document filter; Bot.download() (verified) |
| PARSE-01 | LLM extracts structured race info from raw paste | ChatOpenAI.with_structured_output() + Pydantic v2 model (verified) |
| PARSE-02 | Parser model configurable via env/config | Pydantic Settings nested config pattern (already in codebase) |
| PARSE-03 | LLM scans for bankroll/balance mention in paste | Single parse call can return both race data and detected_bankroll field |
| PARSE-04 | Bot displays parsed summary for user confirmation | aiogram FSM state + inline keyboard Confirm/Cancel (verified pattern) |
| PARSE-05 | Odds normalization: decimal/fractional/American → decimal; implied prob; overround; unit tested | Deterministic Python functions (math verified) — pytest needed (not installed) |
| PARSE-06 | Runner status field active/scratched; scratches excluded; overround recalculated | Pydantic model field with validator; Python filtering logic |
| BANK-01 | Bankroll stored in SQLite (USDT) | New `stake_bankroll` table in races.db via migrations.py pattern |
| BANK-02 | Bankroll found in paste → confirmation branch | FSM branch state based on parse result |
| BANK-03 | No bankroll anywhere → bot asks explicitly | FSM guard condition before continuing |
| BANK-04 | Current USDT balance in every response header | Helper function reads from DB, prepended to all message texts |
| BANK-05 | User can update balance via "balance: 150" or command | Command handler + message pattern handler |
| PIPELINE-01 | Step-by-step progressive updates | await message.answer() at each LangGraph node transition |
| PIPELINE-02 | Ambiguous data → clarifying question | FSM pause state; LangGraph conditional edge |
| PIPELINE-03 | /cancel active pipeline at any time | Command handler calls state.clear() |
| PIPELINE-04 | FSM state persists through bot restarts | RedisStorage backend confirmed available (aiogram 3.24.0) |
| PIPELINE-05 | One session per user; duplicate warns | Guard check on state before accepting new paste |
| AUDIT-01 | Append-only JSON-lines log per pipeline run | Python's built-in file I/O with 'a' mode; jsonlines pattern |

</phase_requirements>

---

## Summary

Phase 1 builds a new `services/stake/` Docker service that replaces the existing Telegram bot. The service uses aiogram 3's FSM with RedisStorage to maintain user pipeline state across bot restarts, and LangGraph to orchestrate a multi-step parse-confirm-bankroll pipeline. The highest-risk component is the LLM parser: Stake.com's paste format is unknown until real data arrives, so the parser prompt will need iteration with actual paste data.

The existing codebase provides strong reusable patterns: aiogram callback/keyboard architecture (services/telegram/), LangGraph StateGraph workflow (src/agents/base.py), Pydantic Settings with env prefix (src/config/settings.py), SQLite migration pattern (src/database/migrations.py), and the Repository pattern (src/database/repositories.py). All required libraries are already installed and verified working. No new dependencies are needed for Phase 1 — only pytest for unit tests (currently absent from requirements.txt and the venv).

The two-layer architecture (aiogram FSM handles Telegram interaction state; LangGraph handles pipeline logic within a session) keeps concerns clean and matches the existing codebase's patterns.

**Primary recommendation:** Build `services/stake/` as a self-contained service mirroring the structure of `services/telegram/` — same import patterns, same Pydantic Settings extension, same Docker target — with aiogram 3 FSM driving UX states and LangGraph running the parse pipeline internally.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiogram | 3.24.0 (installed) | Telegram bot framework | Already in project; FSM + RedisStorage confirmed working |
| langgraph | 1.0.7 (installed) | Pipeline orchestration (StateGraph) | Already chosen (D-23); already in project |
| redis (asyncio) | 7.1.0 (installed) | FSM persistence (RedisStorage) | RedisStorage import verified; same Redis container |
| pydantic v2 | 2.5.0+ (installed) | Structured LLM output model | with_structured_output() uses Pydantic JSON schema |
| pydantic-settings | 2.1.0+ (installed) | Env-based configuration | Existing RACEHORSE_ prefix pattern to extend |
| langchain-openai | 0.0.5+ (installed) | LLM client (OpenRouter) | ChatOpenAI.with_structured_output() verified |
| sqlite3 | built-in | Bankroll + parsed races persistence | Existing races.db; new tables via migrations.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | NOT INSTALLED | Unit tests for odds normalization (PARSE-05) | Must add for Wave 0 — required by nyquist_validation |
| jsonlines | standard (use json + 'a' mode) | Audit log (AUDIT-01) | Use stdlib json.dumps() + newline; no extra dep needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LangGraph for pipeline | Raw async functions | LangGraph provides state persistence, conditional edges, future agent mode toggle — matches D-23 |
| RedisStorage FSM backend | MemoryStorage | MemoryStorage lost on restart — PIPELINE-04 requires persistence |
| ChatOpenAI.with_structured_output | Manual JSON parsing | Structured output is typed and validated; manual parsing brittle for arbitrary Stake.com formats |

**Installation (add to requirements.txt):**
```bash
pytest>=7.0.0
```

**Version verification (conducted 2026-03-24):**
- aiogram: 3.24.0 (pip show)
- langgraph: 1.0.7 (pip show)
- redis: 7.1.0 (pip show)
- pytest: NOT INSTALLED — must add to requirements.txt

---

## Architecture Patterns

### Recommended Project Structure

```
services/stake/
├── main.py               # Entry point: Dispatcher + RedisStorage + router registration
├── states.py             # StatesGroup FSM definitions (PipelineStates)
├── handlers/
│   ├── __init__.py
│   ├── commands.py       # /start, /help, /cancel, /balance handlers
│   ├── pipeline.py       # Text paste + document message handlers, FSM transitions
│   └── callbacks.py      # Inline keyboard callback handlers (confirm, bankroll)
├── keyboards/
│   ├── __init__.py
│   └── stake_kb.py       # InlineKeyboardBuilder functions for parse confirmation
├── pipeline/
│   ├── __init__.py
│   ├── graph.py          # LangGraph StateGraph definition (parse → confirm → bankroll)
│   ├── nodes.py          # Individual pipeline node functions
│   └── state.py          # TypedDict for LangGraph pipeline state
├── parser/
│   ├── __init__.py
│   ├── llm_parser.py     # LLM extraction via ChatOpenAI.with_structured_output()
│   ├── models.py         # Pydantic models: ParsedRace, RunnerInfo, MarketContext
│   └── math.py           # Deterministic odds normalization functions (ARCH-01)
├── bankroll/
│   ├── __init__.py
│   └── repository.py     # BankrollRepository: SQLite CRUD for stake_bankroll table
├── audit/
│   ├── __init__.py
│   └── logger.py         # Append-only JSON-lines audit logger
├── callbacks.py          # CallbackData classes (64-byte limit, short prefixes)
└── settings.py           # StakeSettings extending base; STAKE_ env prefix

src/database/
└── stake_migrations.py   # New tables: stake_bankroll, stake_parsed_races, stake_audit_runs
```

### Pattern 1: aiogram FSM with RedisStorage

**What:** aiogram 3 StatesGroup defines named states; RedisStorage persists state keyed by user_id across bot restarts.

**When to use:** All interactive multi-step Telegram flows where user must confirm/respond between steps.

**Example:**
```python
# Source: aiogram 3.24.0 — verified locally
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import redis.asyncio as aioredis

class PipelineStates(StatesGroup):
    idle = State()
    parsing = State()
    awaiting_parse_confirm = State()
    awaiting_bankroll_confirm = State()
    awaiting_bankroll_input = State()

# Initialization (in main.py)
redis_client = aioredis.from_url("redis://redis:6379")
storage = RedisStorage(redis=redis_client, state_ttl=86400, data_ttl=86400)
dp = Dispatcher(storage=storage)

# Handler pattern
@router.message(PipelineStates.idle, F.text)
async def handle_paste(message: Message, state: FSMContext):
    await state.set_state(PipelineStates.parsing)
    await state.update_data(raw_input=message.text)
    await message.answer("Parsing race data...")
    # ... run LangGraph pipeline step
```

### Pattern 2: LangGraph Pipeline for Parse Step

**What:** LangGraph StateGraph with typed state dict orchestrates parse → derived_calculations → bankroll_check nodes. Telegram FSM calls into graph; each node can emit progress messages.

**When to use:** When steps need conditional routing (bankroll found vs not found), future agent mode upgrade, or state checkpointing.

**Example:**
```python
# Source: LangGraph 1.0.7 — verified locally
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List

class PipelineState(TypedDict):
    raw_input: str
    parsed_race: Optional[dict]        # From LLM parser
    detected_bankroll: Optional[float] # From LLM scanner
    runners_active: List[dict]         # After scratch exclusion
    overround: Optional[float]         # From math.py
    bankroll_confirmed: bool
    parse_confirmed: bool

def parse_node(state: PipelineState) -> PipelineState:
    """LLM extracts structured race from raw paste."""
    # ... ChatOpenAI.with_structured_output(ParsedRace).invoke(...)
    return {**state, "parsed_race": parsed}

def calc_node(state: PipelineState) -> PipelineState:
    """Deterministic Python: implied probs, overround, scratch exclusion."""
    # ... odds_math.normalize() etc.
    return {**state, "runners_active": active, "overround": ovr}

def bankroll_router(state: PipelineState) -> str:
    if state["detected_bankroll"] is not None:
        return "await_bankroll_confirm"
    if not state.get("db_bankroll"):
        return "ask_bankroll"
    return "pipeline_ready"

graph = StateGraph(PipelineState)
graph.add_node("parse", parse_node)
graph.add_node("calc", calc_node)
graph.add_conditional_edges("calc", bankroll_router, {
    "await_bankroll_confirm": END,
    "ask_bankroll": END,
    "pipeline_ready": END,
})
graph.set_entry_point("parse")
app = graph.compile()
```

### Pattern 3: LLM Structured Output via with_structured_output

**What:** `ChatOpenAI.with_structured_output(Pydantic Model)` forces LLM to return JSON matching the Pydantic schema. All fields absent from paste become `None` automatically.

**When to use:** Whenever LLM must return typed, validated data (PARSE-01 + D-08).

**Example:**
```python
# Source: langchain-openai — verified locally
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class RunnerInfo(BaseModel):
    number: int
    name: str
    barrier: Optional[int] = None
    weight: Optional[str] = None
    jockey: Optional[str] = None
    trainer: Optional[str] = None
    form_string: Optional[str] = None
    opening_odds: Optional[float] = None
    win_odds: Optional[float] = None       # Raw as found in paste
    win_odds_format: Optional[str] = None  # "decimal" | "fractional" | "american"
    place_odds: Optional[float] = None
    status: Literal["active", "scratched"] = "active"
    tags: Optional[List[str]] = None       # Top Tip, Drawn Well, Speed Rating

class ParsedRace(BaseModel):
    platform: Optional[str] = None
    track: Optional[str] = None
    race_number: Optional[str] = None
    race_name: Optional[str] = None
    distance: Optional[str] = None
    surface: Optional[str] = None
    place_terms: Optional[str] = None      # "three place dividends paid"
    runners: List[RunnerInfo]
    bet_types_available: Optional[List[str]] = None
    detected_bankroll: Optional[float] = None  # If any balance mention found

llm = ChatOpenAI(
    model="google/gemini-flash-1.5",   # Configurable via env
    openai_api_key=settings.api_keys.openrouter_api_key.get_secret_value(),
    openai_api_base="https://openrouter.ai/api/v1"
)
parser_chain = llm.with_structured_output(ParsedRace, method="json_schema")
result: ParsedRace = await parser_chain.ainvoke([
    SystemMessage(content=PARSE_SYSTEM_PROMPT),
    HumanMessage(content=raw_paste)
])
```

### Pattern 4: Deterministic Odds Math (ARCH-01)

**What:** Pure Python functions with no LLM involvement for all numerical derivations.

**When to use:** Every time odds appear — normalization, implied probability, overround.

**Example:**
```python
# Source: math verified locally — all outputs confirmed correct
def to_decimal(odds_value: str | float, fmt: str) -> float:
    """Convert any odds format to decimal."""
    if fmt == "decimal":
        return float(odds_value)
    if fmt == "fractional":
        parts = str(odds_value).split("/")
        return round(float(parts[0]) / float(parts[1]) + 1, 4)
    if fmt == "american":
        v = float(odds_value)
        if v > 0:
            return round(v / 100 + 1, 4)
        return round(100 / abs(v) + 1, 4)
    raise ValueError(f"Unknown odds format: {fmt}")

def implied_probability(decimal_odds: float) -> float:
    return round(1 / decimal_odds, 6)

def overround(decimal_odds_list: list[float]) -> float:
    """Sum of implied probabilities. >1.0 means bookmaker margin exists."""
    return round(sum(1 / o for o in decimal_odds_list), 4)

def recalculate_without_scratches(runners: list) -> float:
    active = [r for r in runners if r.status == "active"]
    return overround([r.decimal_odds for r in active])
```

### Pattern 5: SQLite New Tables via Existing Migration Pattern

**What:** New stake-specific tables added to existing `races.db` via a dedicated `stake_migrations.py` following the same `run_migrations()` pattern.

**When to use:** BANK-01 (bankroll), and audit log metadata (AUDIT-01 file path reference).

**Example schema:**
```sql
CREATE TABLE IF NOT EXISTS stake_bankroll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance_usdt REAL NOT NULL,
    stake_pct REAL DEFAULT 0.02,      -- Default 2% stake
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stake_pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input TEXT NOT NULL,
    parsed_race_json TEXT,
    user_confirmed INTEGER DEFAULT 0,
    bankroll_at_run REAL,
    audit_log_line INTEGER,            -- Line number in JSONL file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Pattern 6: Document (.txt) File Handling

**What:** aiogram handles document uploads via `F.document` filter. Bot downloads file content using `bot.download()`.

**When to use:** INPUT-02 — user sends .txt file instead of pasting.

**Example:**
```python
# Source: aiogram 3.24.0 — verified locally
from aiogram import F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
import io

@router.message(PipelineStates.idle, F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if doc.mime_type not in ("text/plain",) and not doc.file_name.endswith(".txt"):
        await message.answer("Please send a .txt file with race data.")
        return
    buf = io.BytesIO()
    await bot.download(doc.file_id, destination=buf)
    raw_text = buf.getvalue().decode("utf-8")
    await state.update_data(raw_input=raw_text)
    # ... continue same as paste handler
```

### Pattern 7: Audit Log (AUDIT-01)

**What:** Append-only JSON-lines file written with stdlib `json` + Python file `'a'` mode. No extra dependency.

**When to use:** Every pipeline run — raw input + parsed output + confirmation outcome.

**Example:**
```python
# Source: Python stdlib — no dependency needed
import json
from datetime import datetime
from pathlib import Path

AUDIT_LOG_PATH = Path("/app/data/stake_audit.jsonl")

def write_audit_entry(entry: dict) -> None:
    entry["timestamp"] = datetime.utcnow().isoformat()
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

### Anti-Patterns to Avoid

- **LLM-generated numbers:** Never ask LLM to calculate odds, overround, or implied probability. LLM extracts raw text values only; Python math.py converts them (ARCH-01).
- **MemoryStorage for FSM:** Do not use aiogram's default MemoryStorage — state is lost on restart. RedisStorage required (PIPELINE-04).
- **Hardcoded parser model:** Parser model ID must come from settings, not be a string literal (D-06, PARSE-02).
- **Single monolithic handler:** Do not put all pipeline logic in one message handler. Use LangGraph nodes and FSM states to separate concerns.
- **Same callback prefix as existing service:** The existing telegram service uses `m:`, `r:`, `s:`, `c:`, `d:` prefixes. New stake service must use different prefixes (e.g., `sk:`, `sp:`, `sb:`) if running concurrently (D-02 says same token, same bot — but since it *replaces* the existing bot, prefix collision is not a production concern; still use distinct naming for clarity).
- **Blocking sync code in async handlers:** All DB access, file I/O, and LLM calls must be async or run via `asyncio.to_thread()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output | Custom JSON prompt + regex | `ChatOpenAI.with_structured_output(Pydantic)` | Handles schema enforcement, retries, validation automatically |
| FSM state persistence | Custom Redis key management | `aiogram.fsm.storage.redis.RedisStorage` | Handles key namespacing, TTL, serialization natively |
| Telegram inline keyboards | Manual `InlineKeyboardMarkup` dicts | `InlineKeyboardBuilder` + `CallbackData` classes | Type-safe, 64-byte enforcement, cleaner code (existing pattern) |
| Odds format detection | Regex guessing | LLM extracts `win_odds_format` field alongside the value | Format context is available in paste text; LLM reads it |
| Pipeline state machine | Custom dict + if/else | LangGraph `StateGraph` with conditional edges | Supports future agent mode (D-23), checkpointing, visualisation |

**Key insight:** The LLM parser is a format-adaptive extraction tool, not a computation engine. Everything the LLM extracts is a string or number from the paste; everything derived is Python.

---

## Common Pitfalls

### Pitfall 1: Stake.com Paste Format Unknown

**What goes wrong:** Parser prompt written against an assumed format fails on real paste; race summary shows null fields everywhere.

**Why it happens:** Stake.com UI varies by region (Asia/Sonoda example noted in CONTEXT.md), and the exact copy-paste output from a browser is unknown until the user submits one.

**How to avoid:** Design the parser prompt to be format-agnostic. Instruct LLM to find data wherever it appears. Add a `raw_unmatched_lines` field to capture anything not parsed — useful for debugging.

**Warning signs:** All runner fields except name/odds are null in first real test.

### Pitfall 2: Telegram 64-Byte Callback Limit

**What goes wrong:** Callback button silently never fires; Telegram rejects the keyboard on send.

**Why it happens:** `CallbackData.pack()` produces a string exceeding 64 bytes. aiogram does not raise an error at definition time.

**How to avoid:** Use short prefixes (2-3 chars). Test with `len(CallbackData(...).pack().encode('utf-8')) <= 64`. Confirmed pattern from existing service: `m:`, `r:`, `s:`, `c:`, `d:`.

**Warning signs:** Buttons render but callback handler never fires.

### Pitfall 3: FSM State Left Dirty After Error

**What goes wrong:** User gets stuck in `parsing` or `awaiting_parse_confirm` state after a LLM timeout or error. All future messages go to wrong handler.

**Why it happens:** Exception in pipeline handler does not call `state.clear()` or transition to idle.

**How to avoid:** Wrap all pipeline node calls in try/except. On any unhandled error: `await state.clear()`, send error message to user with instructions to start again.

**Warning signs:** User pastes new race data and bot says "I'm still processing a previous request" indefinitely.

### Pitfall 4: Fractional Odds as Float Precision

**What goes wrong:** `"11/4"` parsed as float `2.75` by LLM (losing format info); conversion to decimal uses wrong formula.

**Why it happens:** LLM coerces string to float if field type is `float`. Format context (fractional vs decimal) is lost.

**How to avoid:** Keep `win_odds` as `Optional[str]` in the Pydantic model, and use a separate `win_odds_format` field. Parse to float only in Python `math.py` after format is known.

### Pitfall 5: RedisStorage TTL Mismatch

**What goes wrong:** User session expires mid-pipeline (e.g., 30-minute break) and state silently disappears. Bot ignores subsequent callback button presses.

**Why it happens:** Default `state_ttl`/`data_ttl` in RedisStorage may be too short for a human interactive session.

**How to avoid:** Set `state_ttl=86400` (24h) and `data_ttl=86400` in `RedisStorage` constructor. Verified constructor signature accepts these parameters (2026-03-24).

### Pitfall 6: Docker Token Conflict

**What goes wrong:** Both existing telegram service and new stake service start simultaneously with the same bot token — Telegram allows only one webhook/polling session per token.

**Why it happens:** D-02 says same token; D-01 says separate service; branch isolation means docker-compose.yml for stake-advisor branch does NOT include the old telegram service target.

**How to avoid:** On the `stake-advisor` branch, the docker-compose.yml should either remove or comment out the `telegram` service. Verify during Docker Compose setup.

### Pitfall 7: Overround After Scratches

**What goes wrong:** Overround displayed on confirmation screen is calculated including scratched runners, giving false "low margin" signal.

**Why it happens:** Scratch exclusion step skipped or runs after overround calculation.

**How to avoid:** Always filter to `status == "active"` runners BEFORE any overround/implied probability calculation. Order: LLM parse → Python scratch exclusion → Python overround. Confirmed in PARSE-06 requirements.

---

## Code Examples

### Initializing Dispatcher with RedisStorage (main.py)

```python
# Source: aiogram 3.24.0 — verified locally
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

async def main():
    redis_client = aioredis.from_url("redis://redis:6379")
    storage = RedisStorage(
        redis=redis_client,
        state_ttl=86400,   # 24h
        data_ttl=86400
    )
    bot = Bot(
        token=settings.api_keys.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=storage)
    dp.include_router(commands_router)
    dp.include_router(pipeline_router)
    await dp.start_polling(bot)
```

### Cancelling Pipeline

```python
# Source: aiogram 3.24.0 — verified locally
from aiogram.filters import Command

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("No active pipeline to cancel.")
        return
    await state.clear()
    await message.answer(
        "<b>Pipeline cancelled.</b>\n\nPaste a new race to start again.",
        parse_mode=ParseMode.HTML
    )
```

### Duplicate Paste Guard (PIPELINE-05)

```python
# Guard: reject new paste if pipeline already active
@router.message(F.text, ~PipelineStates.idle)
async def handle_duplicate_paste(message: Message, state: FSMContext):
    await message.answer(
        "A pipeline is already running. Use /cancel to stop it, or wait for it to complete."
    )
```

### Bankroll Header Helper

```python
async def bankroll_header(repo: BankrollRepository) -> str:
    """Returns formatted balance line for prepending to all responses."""
    balance = await repo.get_balance()
    if balance is None:
        return "<b>Balance: Not set</b>"
    return f"<b>Balance: {balance:.2f} USDT</b>"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| aiogram 2.x FSM (dispatcher-level states) | aiogram 3.x StatesGroup + Router-scoped FSM | aiogram 3.0 (2022) | Router-scoped handlers, cleaner state management |
| MemoryStorage default | RedisStorage for persistence | aiogram 3.0 | Required for PIPELINE-04 |
| LangGraph 0.0.x (used in requirements.txt pin) | LangGraph 1.0.7 (installed) | 2024-2025 | StateGraph API stable; `END` and conditional edges unchanged |
| LangChain structured output via function calling | `with_structured_output(method="json_schema")` | LangChain 0.1+ | More reliable schema enforcement for Pydantic v2 |

**Deprecated/outdated:**
- `asyncio-redis` package: Listed in requirements.txt but overlaps with `redis[asyncio]`. aiogram RedisStorage uses `redis.asyncio`, not `asyncio-redis`. Do not use `asyncio-redis` for new stake service.

---

## Open Questions

1. **Stake.com paste format structure**
   - What we know: Format is unknown; varies by region; Stake.com shows race cards with runners, odds, tags (Top Tip, Drawn Well), running styles
   - What's unclear: Exact whitespace/tab structure, whether bet types appear as a table or sidebar, whether place odds are in the same table as win odds
   - Recommendation: Build the parser with a liberal prompt that captures everything, include a `raw_unmatched_text` debug field, and plan one iteration after first real paste test (noted as PARSE-01 risk in STATE.md)

2. **`win_odds_format` detection reliability**
   - What we know: LLM can read context ("evens", "4/1", "-150", "2.50") and infer format
   - What's unclear: If odds are only shown as bare numbers (e.g., "2.50") without explicit format markers, LLM may guess wrong between decimal 2.50 and fractional 3/2
   - Recommendation: Default to decimal format if no format indicators found; include format in confirmation display so user can spot errors before pipeline proceeds

3. **Branch strategy for docker-compose.yml**
   - What we know: D-01 says new service on `stake-advisor` branch; D-02 says same bot token (so existing telegram target must be disabled)
   - What's unclear: Whether to entirely remove existing telegram service from docker-compose on that branch or comment it out
   - Recommendation: Remove the `telegram` target service from docker-compose.yml on `stake-advisor` branch; add `stake` target. Note in commit message.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Containerization | Yes | 27.4.0 | — |
| Python 3 | All scripts | Yes | 3.13.12 | — |
| Redis (container) | FSM storage, pub/sub | Yes (Docker) | 7-alpine | — |
| aiogram | Telegram bot | Yes | 3.24.0 | — |
| langgraph | Pipeline orchestration | Yes | 1.0.7 | — |
| redis (py) | RedisStorage | Yes | 7.1.0 | — |
| langchain-openai | LLM parser | Yes | installed | — |
| OPENROUTER_API_KEY | LLM API calls | Yes (env SET) | — | — |
| TELEGRAM_BOT_TOKEN | Bot operation | Not in shell env | — | Must be in .env (Coolify env vars) |
| TELEGRAM_CHAT_ID | Bot operation | Not in shell env | — | Must be in .env (Coolify env vars) |
| pytest | Unit tests (PARSE-05) | NO | — | Must install; no fallback — tests required |

**Missing dependencies with no fallback:**
- `pytest` — Required for PARSE-05 odds normalization unit tests (nyquist_validation enabled). Must be added to `requirements.txt` and installed.

**Missing dependencies with fallback:**
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Not in current shell env but configured in Coolify UI (49 env vars) and local `.env` file. Not blocking for implementation.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (NOT YET INSTALLED — Wave 0 gap) |
| Config file | `pytest.ini` or `pyproject.toml` (none detected — Wave 0 gap) |
| Quick run command | `pytest tests/stake/ -x -q` |
| Full suite command | `pytest tests/stake/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PARSE-05 | `to_decimal(decimal)` returns correct value | unit | `pytest tests/stake/test_odds_math.py::test_decimal_passthrough -x` | No — Wave 0 |
| PARSE-05 | `to_decimal(fractional "5/1")` returns 6.0 | unit | `pytest tests/stake/test_odds_math.py::test_fractional_conversion -x` | No — Wave 0 |
| PARSE-05 | `to_decimal(fractional "11/4")` returns 3.75 | unit | `pytest tests/stake/test_odds_math.py::test_fractional_11_4 -x` | No — Wave 0 |
| PARSE-05 | `to_decimal(american +500)` returns 6.0 | unit | `pytest tests/stake/test_odds_math.py::test_american_positive -x` | No — Wave 0 |
| PARSE-05 | `to_decimal(american -150)` returns 1.6667 | unit | `pytest tests/stake/test_odds_math.py::test_american_negative -x` | No — Wave 0 |
| PARSE-05 | `overround([2.0, 2.0, 10.0])` returns 1.10 | unit | `pytest tests/stake/test_odds_math.py::test_overround -x` | No — Wave 0 |
| PARSE-06 | Scratched runners excluded from overround | unit | `pytest tests/stake/test_odds_math.py::test_overround_excludes_scratched -x` | No — Wave 0 |
| BANK-01 | BankrollRepository.get_balance() returns None on empty DB | unit | `pytest tests/stake/test_bankroll.py::test_empty_balance -x` | No — Wave 0 |
| BANK-01 | BankrollRepository.set_balance(100.0) persists | unit | `pytest tests/stake/test_bankroll.py::test_set_balance -x` | No — Wave 0 |
| AUDIT-01 | write_audit_entry() appends valid JSON line | unit | `pytest tests/stake/test_audit.py::test_audit_append -x` | No — Wave 0 |
| PARSE-01/04 | Full parse → confirm flow | smoke/manual | Manual: paste sample text into bot | N/A |
| PIPELINE-04 | FSM state survives bot restart | integration | Manual: set state, restart bot, verify state | N/A |

### Sampling Rate

- **Per task commit:** `pytest tests/stake/ -x -q`
- **Per wave merge:** `pytest tests/stake/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `pytest` — add to `requirements.txt` (`pytest>=7.0.0`) and install
- [ ] `tests/stake/__init__.py` — create test package
- [ ] `tests/stake/test_odds_math.py` — covers PARSE-05, PARSE-06
- [ ] `tests/stake/test_bankroll.py` — covers BANK-01
- [ ] `tests/stake/test_audit.py` — covers AUDIT-01
- [ ] `pytest.ini` or `[tool.pytest.ini_options]` in `pyproject.toml` — configure test discovery

---

## Project Constraints (from CLAUDE.md)

Directives extracted from project CLAUDE.md that the planner MUST verify compliance with:

| Directive | Impact on Phase 1 |
|-----------|-------------------|
| Python 3.11+ in Docker containers (3.11-slim base image) | New stake Dockerfile target uses same base image; Python 3.13 on dev host, 3.11 in container |
| All async/await for I/O (Playwright, Redis, HTTP) | All FSM handlers, DB access, LLM calls must be `async def` |
| Type hints mandatory in function signatures | All functions in parser/, bankroll/, pipeline/ must have typed signatures |
| PEP 8 + 4-space indentation | No deviation |
| Module-level docstrings in all .py files | Every new file needs triple-quote module docstring |
| `RACEHORSE_` env prefix + `__` nested delimiter | Extend for stake: e.g. `RACEHORSE_STAKE__PARSER_MODEL` |
| NEVER display credentials in output | API keys, bot tokens via SecretStr only |
| aiogram CallbackData prefix ≤ 64 bytes | Use short prefixes for all StakeCB classes |
| `src/logging_config.py` pattern for logging | Use `setup_logging("stake")` for all loggers |
| Docker Compose multi-target Dockerfile pattern | Add `stake` target to Dockerfile following existing pattern |
| GSD workflow enforcement — no direct file edits outside GSD commands | All implementation happens through `/gsd:execute-phase` |
| `mamba run -n ml-env` for data science scripts | Not applicable for this phase (no ML/data scripts) |
| Verification after code changes (rebuild, restart, verify_fixes.sh, check logs, DB integrity) | After each wave deployment on Meridian |

---

## Sources

### Primary (HIGH confidence)

- aiogram 3.24.0 — installed, verified locally: FSM, RedisStorage, StatesGroup, Document handler, Dispatcher signatures
- LangGraph 1.0.7 — installed, verified locally: StateGraph, END, conditional edges API
- langchain-openai — installed, verified locally: `with_structured_output(method="json_schema")` signature
- redis 7.1.0 — installed, verified locally: `RedisStorage` import OK
- services/telegram/main.py, callbacks.py, keyboards.py — codebase canonical reference
- src/agents/base.py — LangGraph workflow pattern reference
- src/config/settings.py — Pydantic Settings pattern reference
- src/database/migrations.py — SQLite migration pattern reference

### Secondary (MEDIUM confidence)

- CONTEXT.md + REQUIREMENTS.md — user decisions, locked choices; treat as authoritative project spec
- docker-compose.yml — existing service structure for new stake service integration

### Tertiary (LOW confidence)

- Stake.com paste format — entirely unknown; only described generically in CONTEXT.md specifics section. Treat parser prompt as experimental first iteration.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries installed, versions verified locally
- Architecture: HIGH — all patterns copied from working existing codebase or verified APIs
- Pitfalls: HIGH — derived from verified behavior (callback 64-byte limit, FSM TTL, async requirements)
- Parser effectiveness: LOW — Stake.com format unknown; first real paste may require prompt iteration

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable libraries; LOW caveat on Stake.com format remains until first real test)
