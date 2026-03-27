# Phase 3: Results, Reflection and Stats - Research

**Researched:** 2026-03-27
**Domain:** Result evaluation, P&L tracking, AI reflection/lesson extraction, statistics, drawdown circuit breaker
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** LLM-based result parsing — reuse the same `StakeParser` pattern for flexible text input ("3,5,11,12" or "horse name won"), with ambiguity detection and clarification flow via FSM `awaiting_clarification` state.

**D-02:** Results linked to recommendations via `run_id` from `stake_pipeline_runs` — reference stored in FSM state after recommendation display, matched on result submission.

**D-03:** Placed/tracked distinction presented as inline keyboard on the recommendation message itself — user taps "Placed" or "Tracked" before submitting results. New `st:` callback prefix, follows existing callback pattern.

**D-04:** P&L stored in new SQLite table (`stake_bet_outcomes`) alongside existing tables, following the migration and repository patterns. Each row links to a pipeline run and records per-bet outcome (win/loss, amount won/lost).

**D-05:** `stake_bankroll` table gets a `peak_balance_usdt` column for drawdown tracking (RISK-01).

**D-06:** Use configurable model for reflections — new `ReflectionSettings` nested BaseModel in `StakeSettings`, defaulting to the analysis model but independently configurable.

**D-07:** Dual storage: `mindset.md` server-side markdown file for human-readable reflection log + SQLite `stake_lessons` table for queryable structured lessons.

**D-08:** Lessons injected into analysis prompt: top-5 extracted rules + last-3 failure modes queried from `stake_lessons` and appended to `_build_analysis_prompt()`.

**D-09:** Early pipeline check before analysis — read peak balance from bankroll table, compare with current balance. If ≥20% drawdown, short-circuit to skip message without running expensive LLM steps. Follows existing `pre_skip_check_node` pattern.

**D-10:** 20% threshold configurable via env var. Deterministic math only (ARCH-01).

### Claude's Discretion

- Exact SQLite schema for `stake_bet_outcomes` and `stake_lessons` tables
- Result parsing prompt design
- `mindset.md` format and reflection prose style
- Telegram message formatting for result confirmation and stats display
- How to handle partial results (e.g., user only knows winner, not full finishing order)
- Stats display layout and which metrics to show for STATS-01
- FSM state names and transitions for the result submission flow

### Deferred Ideas (OUT OF SCOPE)

None — analysis stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESULT-01 | User can submit race result as flexible text (e.g. "3,5,11,12" or "horse name won" or screenshot) | `StakeParser` pattern + new `ResultParser` following same `with_structured_output` chain |
| RESULT-02 | LLM parses result input into structured finishing order; asks for clarification if ambiguous | Ambiguity detection via `ParsedResult` model fields; FSM `awaiting_result_clarification` state mirrors existing `awaiting_clarification` |
| RESULT-03 | System evaluates each bet in the recommendation against actual result; calculates P&L | Pure Python evaluation in `evaluate_bets_node`; P&L stored in `stake_bet_outcomes` |
| TRACK-01 | Each recommendation can be marked `placed` or `tracked`; P&L stats use `placed` only; model quality metrics use both | `TrackingCB` with `st:` prefix on recommendation message; `is_placed` column in `stake_bet_outcomes` |
| REFLECT-01 | After each evaluated result, AI writes a structured reflection entry to `mindset.md` on server | `ReflectionWriter` class appending to `data/mindset.md` |
| REFLECT-02 | Reflection explicitly asks "what went wrong even in winning bets" (calibration-aware, not just win/loss) | System prompt design forces calibration framing |
| REFLECT-03 | After each reflection, AI extracts one structured lesson (error tag + rule sentence); top-5 rules + last-3 failures injected into next race's analysis prompt | `LessonExtractor` → `stake_lessons` table; query in `_build_analysis_prompt()` |
| STATS-01 | User can request P&L stats (total, by period, win rate, ROI) for `placed` bets at any time | `/stats` command handler + SQL aggregation queries on `stake_bet_outcomes` |
| RISK-01 | Drawdown circuit breaker: if bankroll drops ≥20% from peak, all recommendations become "SKIP (drawdown protection)" until user manually unlocks | `drawdown_check_node` before `pre_skip_check_node`; `peak_balance_usdt` in `stake_bankroll`; unlock via `/unlock_drawdown` command |
</phase_requirements>

---

## Summary

Phase 3 adds a result feedback loop to a working analysis pipeline. The pipeline already produces structured `final_bets` (list of dicts); Phase 3 closes the loop by accepting a result, evaluating those bets against it, recording P&L, writing a reflection, and extracting a reusable lesson. All new code follows the same patterns already established in Phases 1 and 2.

The core technical challenges are: (1) designing a result parsing model that handles partial results (user may only know the winner), (2) correctly mapping bet outcomes to Stake.com bet types (win vs place, which have different payout structures), (3) the lesson injection pipeline (reflection → extraction → structured storage → prompt injection), and (4) the drawdown circuit breaker requiring a new column on the singleton bankroll table and an early pipeline exit.

The most important constraint is ARCH-01: all P&L arithmetic (payout calculation, ROI, drawdown %) must be pure Python. LLM is used only for result text parsing, reflection writing, and lesson extraction — never for any numeric outcome.

**Primary recommendation:** Build Phase 3 as four independent plan units: (1) result input and FSM flow, (2) P&L evaluation and storage, (3) reflection and lesson extraction pipeline, (4) stats command and drawdown circuit breaker. Each unit can be verified independently before the next is built.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiogram | 3.x (already installed) | FSM states, callback handlers, inline keyboards | Already in use; no new dep |
| langchain-openai | already installed | `ChatOpenAI.with_structured_output` for result parsing and reflection | Same pattern as parse_node, analysis_node |
| pydantic | already installed | `ParsedResult`, `LessonEntry` structured output models | Established pattern |
| sqlite3 | stdlib | New tables: `stake_bet_outcomes`, `stake_lessons`, `stake_bankroll` column | Same migration pattern |

### No New Dependencies Required

All libraries needed for Phase 3 are already installed. No `pip install` steps are required.

**Installation:**
```bash
# No new packages. Existing venv is sufficient.
source venv/bin/activate
```

---

## Architecture Patterns

### Recommended New Module Structure

```
services/stake/
├── results/                    # NEW — result evaluation domain
│   ├── __init__.py
│   ├── models.py               # ParsedResult, BetOutcome, LessonEntry Pydantic models
│   ├── parser.py               # ResultParser (mirrors StakeParser pattern)
│   ├── evaluator.py            # evaluate_bets() — pure Python P&L math (ARCH-01)
│   └── repository.py          # BetOutcomesRepository — CRUD for stake_bet_outcomes
├── reflection/                 # NEW — reflection and lesson extraction
│   ├── __init__.py
│   ├── writer.py               # ReflectionWriter — appends to mindset.md
│   ├── extractor.py            # LessonExtractor — LLM structured lesson extraction
│   └── repository.py          # LessonsRepository — CRUD for stake_lessons
├── bankroll/
│   ├── repository.py           # EXTEND: add peak_balance, drawdown methods
│   └── migrations.py           # EXTEND: add peak_balance_usdt col, new tables
├── pipeline/
│   ├── nodes.py                # EXTEND: add drawdown_check_node, result evaluation nodes
│   ├── state.py                # EXTEND: add result/reflection/drawdown fields
│   └── graph.py                # EXTEND or NEW: result processing flow (handler-based, not graph)
├── handlers/
│   └── results.py              # NEW — result submission handler, /stats command
├── keyboards/
│   └── stake_kb.py             # EXTEND: add tracking_kb(), stats_kb(), unlock_drawdown_kb()
├── callbacks.py                # EXTEND: add TrackingCB (st: prefix), StatsCB, DrawdownCB
└── states.py                   # EXTEND: add result submission FSM states
data/
└── mindset.md                  # Created at first reflection write (auto-created)
```

### Pattern 1: Result Parsing (mirrors StakeParser)

**What:** `ResultParser` wraps `ChatOpenAI.with_structured_output(ParsedResult)`. Same constructor pattern as `StakeParser`.
**When to use:** User submits result text in `awaiting_result` state.

```python
# Source: mirrors services/stake/parser/llm_parser.py
class ResultParser:
    def __init__(self, settings=None):
        self.settings = settings or get_stake_settings()
        self.llm = ChatOpenAI(
            model=self.settings.reflection.model,  # cheap model sufficient
            temperature=0.0,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
        ).with_structured_output(ParsedResult)

    async def parse(self, raw_result_text: str) -> ParsedResult:
        return await self.llm.ainvoke([
            SystemMessage(content=RESULT_PARSE_SYSTEM_PROMPT),
            HumanMessage(content=raw_result_text),
        ])
```

### Pattern 2: ParsedResult Model (new contract)

**What:** Structured output model for result text. Handles partial results.

```python
# Confidence decision: LOW = insufficient data for place evaluation
class ParsedResult(BaseModel):
    finishing_order: list[int] = Field(
        description="Runner numbers in finishing order (1st, 2nd, 3rd...). May be partial.",
        default_factory=list
    )
    finishing_names: list[str] = Field(
        description="Runner names in finishing order if numbers not given.",
        default_factory=list
    )
    is_partial: bool = Field(
        description="True if only winner known, not full order",
        default=False
    )
    confidence: Literal["high", "low"] = Field(
        description="high=clear result, low=ambiguous input",
        default="high"
    )
    raw_text: str = Field(description="Original user input preserved for audit")
```

### Pattern 3: P&L Evaluator (pure Python, ARCH-01)

**What:** `evaluate_bets()` takes `final_bets` and `ParsedResult`, returns `list[BetOutcome]`.
**Never** calls LLM.

```python
# Source: ARCH-01 — pure Python evaluation
def evaluate_bet(bet: dict, result: ParsedResult) -> BetOutcome:
    """Returns BetOutcome with profit_usdt, won flag, reason."""
    runner_num = bet["runner_number"]
    bet_type = bet["bet_type"]   # "win" | "place"
    amount = bet["usdt_amount"]
    decimal_odds = bet["decimal_odds"]  # stored at recommendation time
    place_odds = bet.get("place_odds_at_bet")

    winner = result.finishing_order[0] if result.finishing_order else None
    top_3 = set(result.finishing_order[:3])

    if bet_type == "win":
        won = (winner == runner_num)
        payout = amount * decimal_odds if won else 0.0
        profit = payout - amount
    elif bet_type == "place":
        won = (runner_num in top_3) and not result.is_partial
        payout = amount * (place_odds or 0.0) if won else 0.0
        profit = payout - amount
    else:
        won = False
        profit = 0.0

    return BetOutcome(
        runner_number=runner_num,
        runner_name=bet["runner_name"],
        bet_type=bet_type,
        amount_usdt=amount,
        won=won,
        profit_usdt=round(profit, 4),
    )
```

**Key insight on partial results:** When `is_partial=True`, only win bets can be evaluated. Place bets cannot be evaluated without full finishing order. These should be stored with `evaluable=False` and excluded from P&L totals.

### Pattern 4: Drawdown Check Node (mirrors pre_skip_check_node)

**What:** First node in `build_analysis_graph()`. Reads `peak_balance_usdt` and `balance_usdt` from bankroll table. Short-circuits to format_recommendation if drawdown ≥ threshold.

```python
# Source: mirrors services/stake/pipeline/nodes.py::pre_skip_check_node
def drawdown_check_node(state: PipelineState) -> dict:
    repo = BankrollRepository(get_stake_settings().database_path)
    peak = repo.get_peak_balance()
    current = repo.get_balance()

    if peak is None or current is None:
        return {}  # No data — cannot check

    drawdown_pct = ((peak - current) / peak) * 100.0
    threshold = get_stake_settings().risk.drawdown_threshold_pct  # default 20.0

    if drawdown_pct >= threshold:
        return {
            "skip_signal": True,
            "skip_reason": f"DRAWDOWN PROTECTION: balance {current:.2f} USDT is {drawdown_pct:.1f}% below peak {peak:.2f} USDT. Use /unlock_drawdown to override.",
            "skip_tier": 0,  # new tier for drawdown
        }
    return {}
```

### Pattern 5: Lesson Injection in Analysis Prompt

**What:** `_build_analysis_prompt()` in `nodes.py` extended to query `stake_lessons` and prepend top-5 rules + last-3 failure modes.

```python
# Extension to existing _build_analysis_prompt() in nodes.py
def _build_lessons_block(db_path: str) -> str:
    """Query stake_lessons for top-5 rules and last-3 failure modes."""
    repo = LessonsRepository(db_path)
    top_rules = repo.get_top_rules(limit=5)
    failure_modes = repo.get_recent_failures(limit=3)

    if not top_rules and not failure_modes:
        return ""

    lines = ["=== LEARNED LESSONS ==="]
    if top_rules:
        lines.append("Rules (most applied):")
        for rule in top_rules:
            lines.append(f"  [{rule['error_tag']}] {rule['rule_sentence']}")
    if failure_modes:
        lines.append("Recent failure modes:")
        for fail in failure_modes:
            lines.append(f"  [{fail['error_tag']}] {fail['rule_sentence']}")
    lines.append("")
    return "\n".join(lines)
```

### Pattern 6: FSM State Machine for Result Flow

**What:** New states added to `PipelineStates` StatesGroup.

```python
# Extension to services/stake/states.py
class PipelineStates(StatesGroup):
    # ... existing states ...
    awaiting_placed_tracked = State()     # After recommendation — user chooses Placed/Tracked
    awaiting_result = State()             # After Placed/Tracked — waiting for result text
    awaiting_result_clarification = State()  # Ambiguous result — asking user to clarify
    confirming_result = State()           # User confirms parsed result before evaluation
```

**Flow diagram:**
```
recommendation sent
    -> show Placed/Tracked keyboard  -> awaiting_placed_tracked
        -> user taps Placed/Tracked  -> store choice in FSM data
        -> awaiting_result: "Paste the finishing order when the race is done"
            -> user sends result text
            -> ResultParser.parse()
            -> if low confidence: awaiting_result_clarification
            -> if high confidence: confirming_result
                -> user confirms: evaluate_bets() -> store outcomes -> reflection -> back to idle
                -> user rejects: back to awaiting_result
```

### Pattern 7: SQLite Schema Decisions (Claude's Discretion)

**`stake_bet_outcomes` table:**
```sql
CREATE TABLE IF NOT EXISTS stake_bet_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,                -- FK to stake_pipeline_runs.run_id
    is_placed INTEGER NOT NULL DEFAULT 0,   -- 1=placed, 0=tracked
    runner_name TEXT NOT NULL,
    runner_number INTEGER,
    bet_type TEXT NOT NULL,                 -- 'win' | 'place'
    amount_usdt REAL NOT NULL,
    decimal_odds REAL,                      -- odds at time of recommendation
    place_odds REAL,                        -- place odds at time of recommendation
    won INTEGER NOT NULL DEFAULT 0,         -- 1=won, 0=lost
    profit_usdt REAL NOT NULL,             -- negative on loss
    evaluable INTEGER NOT NULL DEFAULT 1,  -- 0 if partial result, can't evaluate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**`stake_lessons` table:**
```sql
CREATE TABLE IF NOT EXISTS stake_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_tag TEXT NOT NULL,               -- 1-line category e.g. "overconfidence_on_favourite"
    rule_sentence TEXT NOT NULL,           -- 1-sentence actionable rule
    is_failure INTEGER NOT NULL DEFAULT 0, -- 1 = failure mode, 0 = general rule
    application_count INTEGER DEFAULT 0,   -- incremented when injected into prompt
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**`stake_bankroll` schema extension:**
```sql
ALTER TABLE stake_bankroll ADD COLUMN peak_balance_usdt REAL;
-- Handled via migration with IF NOT EXISTS check on column
```

**Note on ALTER TABLE in SQLite:** SQLite does not support `ALTER TABLE ADD COLUMN IF NOT EXISTS` directly. The migration must check `PRAGMA table_info(stake_bankroll)` and only alter if the column is absent.

```python
# Safe migration pattern for adding column
cursor.execute("PRAGMA table_info(stake_bankroll)")
cols = [row[1] for row in cursor.fetchall()]
if "peak_balance_usdt" not in cols:
    cursor.execute("ALTER TABLE stake_bankroll ADD COLUMN peak_balance_usdt REAL")
```

### Anti-Patterns to Avoid

- **LLM-generated P&L:** Never use LLM to calculate profit or ROI. All numerical outcomes are Python (ARCH-01). LLM is used only to parse flexible text input into a structured `ParsedResult`.
- **Pydantic objects in Redis FSM:** All FSM state data must be `model_dump()` before storage. `ParsedResult` and `BetOutcome` must be stored as dicts, not Pydantic objects.
- **Blocking result evaluation:** Do NOT require full finishing order for all bets. Partial results are valid for win bets. Store `evaluable=0` for unevaluable bets rather than blocking the flow.
- **peak_balance_usdt update timing:** Peak must be updated AFTER balance is confirmed set, not before. Peak = max(current_peak, new_balance). If no peak exists, set peak = first balance.
- **Drawdown unlock persistence:** The unlock state must NOT be in-memory only. Store `drawdown_unlocked` flag in the bankroll table so it survives bot restarts. Reset to 0 when balance recovers above peak × 0.80.
- **mindset.md path hardcoding:** Use `settings.reflection.mindset_path` (or `audit.log_path` parent + `mindset.md`). Don't hardcode path in reflection writer.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Flexible result text parsing | Custom regex or string matching | `ChatOpenAI.with_structured_output(ParsedResult)` | Handles "3 won", "3,5,11", "Thunder won, Lightning 2nd" — edge cases are infinite |
| P&L statistics aggregation | Custom Python loops | SQL aggregation (`SUM`, `COUNT`, `AVG`, `GROUP BY`) in repository methods | SQLite handles this cleanly; Python loops over large result sets is fragile |
| Lesson storage and retrieval | In-memory dict or flat file | SQLite `stake_lessons` table | Queryable, sortable by application_count, persistent across restarts |
| FSM state machine | Custom state tracking dict | aiogram `StatesGroup` + `FSMContext` | Already in use; handles persistence via Redis |
| Reflection prose formatting | Template strings | LLM with calibration-aware system prompt | Reflection quality depends on the model's ability to identify non-obvious failures |

**Key insight:** The LLM is most valuable for unstructured-to-structured conversion (result text → finishing order, reflection → lesson). All numerical outcomes are pure Python to comply with ARCH-01.

---

## Common Pitfalls

### Pitfall 1: Odds Not Stored at Recommendation Time
**What goes wrong:** When evaluating a bet outcome, you need the odds that were displayed at recommendation time. If you query the current database odds, they may differ.
**Why it happens:** This phase is built weeks after Phase 2; developers assume odds are in a queryable table.
**How to avoid:** Store `decimal_odds` and `place_odds` directly in `stake_bet_outcomes` at write time, copied from `final_bets` list (already has these values). Do not join back to another table.
**Warning signs:** P&L calculations that rely on odds from `enriched_runners` rather than `stake_bet_outcomes`.

### Pitfall 2: ALTER TABLE Fails on Existing Production Database
**What goes wrong:** `ALTER TABLE stake_bankroll ADD COLUMN peak_balance_usdt` raises `sqlite3.OperationalError: duplicate column name` on an existing database.
**Why it happens:** `CREATE TABLE IF NOT EXISTS` is idempotent; `ALTER TABLE` is not.
**How to avoid:** Use `PRAGMA table_info()` to check for column existence before altering. Already documented in Architecture Patterns above.
**Warning signs:** `OperationalError` in migration logs on service startup.

### Pitfall 3: Drawdown Unlock State Lost on Restart
**What goes wrong:** User unlocks drawdown protection, bot restarts, protection re-activates.
**Why it happens:** Unlock stored as FSM data in Redis, which has a 24h TTL (per `redis.state_ttl` setting).
**How to avoid:** Store `drawdown_unlocked` as a column in `stake_bankroll` table (SQLite, persistent). FSM is for pipeline-in-progress state only, not persistent app settings.
**Warning signs:** Users reporting repeated drawdown protection re-activation.

### Pitfall 4: Place Bet Evaluation With Partial Results
**What goes wrong:** User only knows the winner ("3 won"). System marks place bets for runner 3 as won because it's in position 1 — but also incorrectly tries to evaluate place bets for other runners against an incomplete top-3.
**Why it happens:** `is_partial` flag not checked before evaluating place bets.
**How to avoid:** When `result.is_partial is True`, set `evaluable=False` for all place bets and skip their P&L contribution. Only win bet for confirmed winner is evaluable.
**Warning signs:** ROI calculations that seem too high or low for place-heavy bet sets.

### Pitfall 5: HTML Escape in Reflection and Stats Output
**What goes wrong:** Runner names or reflection text containing `<` or `>` cause silent Telegram message failures.
**Why it happens:** LLM-generated text is passed directly to aiogram with `parse_mode="HTML"`.
**How to avoid:** `html.escape()` all LLM-generated strings before Telegram send. Already established pattern in `formatter.py`.
**Warning signs:** Bot sends empty or truncated messages after reflection or stats command.

### Pitfall 6: mindset.md File Path on Coolify
**What goes wrong:** `mindset.md` written to a path that is not in the Docker volume mount, so it disappears on container restart.
**Why it happens:** Path defaults to working directory, which is not persisted in Docker.
**How to avoid:** Store in the same directory as `stake_audit.jsonl` (i.e., the `data/` volume mount). Derive path from `settings.audit.log_path` parent directory.
**Warning signs:** mindset.md exists locally but is empty or absent after deploy.

### Pitfall 7: run_id Not Available When User Submits Result
**What goes wrong:** User submits result hours after recommendation. `run_id` is not in FSM state (expired TTL or bot restart).
**Why it happens:** Redis FSM TTL is 24 hours. Long-running sessions may lose state.
**How to avoid:** Store `run_id` in FSM data immediately after recommendation is sent. If `run_id` is absent when result is submitted, query `stake_pipeline_runs` for most recent run (fallback). Show user a confirmation step with race details so they can verify the correct run.
**Warning signs:** P&L outcomes linked to wrong pipeline run.

---

## Code Examples

### Tracking Keyboard (New `st:` callback)

```python
# Source: mirrors services/stake/keyboards/stake_kb.py pattern
from services.stake.callbacks import TrackingCB

def tracking_kb() -> InlineKeyboardMarkup:
    """Placed/Tracked choice shown on recommendation message."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Placed (I bet this)", callback_data=TrackingCB(action="placed"))
    builder.button(text="Tracked (not bet)", callback_data=TrackingCB(action="tracked"))
    builder.adjust(2)
    return builder.as_markup()
```

```python
# New callback class in callbacks.py
class TrackingCB(CallbackData, prefix="st"):
    """Placed/tracked choice. 'st:placed' = 9 bytes — well under 64-byte limit."""
    action: str  # "placed" | "tracked"
```

### Stats Query Methods for `BetOutcomesRepository`

```python
# Source: STATS-01 — placed bets only for financial P&L
def get_total_stats(self) -> dict:
    """Total P&L, win rate, ROI for placed bets only."""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                COUNT(*) as total_bets,
                SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as wins,
                SUM(profit_usdt) as total_profit,
                SUM(amount_usdt) as total_staked
            FROM stake_bet_outcomes
            WHERE is_placed = 1 AND evaluable = 1
        """)
        row = cursor.fetchone()
        total = row[0] or 0
        wins = row[1] or 0
        profit = row[2] or 0.0
        staked = row[3] or 0.0
        return {
            "total_bets": total,
            "wins": wins,
            "win_rate": (wins / total * 100) if total > 0 else 0.0,
            "total_profit_usdt": round(profit, 2),
            "roi_pct": (profit / staked * 100) if staked > 0 else 0.0,
        }
    finally:
        conn.close()
```

### Drawdown Detection in BankrollRepository

```python
# New method in services/stake/bankroll/repository.py
def get_peak_balance(self) -> Optional[float]:
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT peak_balance_usdt FROM stake_bankroll WHERE id = 1")
        row = cursor.fetchone()
        return float(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()

def update_peak_if_higher(self, new_balance: float) -> None:
    """Update peak_balance_usdt if new_balance exceeds current peak."""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE stake_bankroll
            SET peak_balance_usdt = MAX(COALESCE(peak_balance_usdt, 0), ?)
            WHERE id = 1
        """, (new_balance,))
        conn.commit()
    finally:
        conn.close()
```

### ReflectionSettings (new nested BaseModel)

```python
# In settings.py — follows ParserSettings/ResearchSettings pattern exactly
class ReflectionSettings(BaseModel):
    """Reflection and lesson extraction LLM config."""
    model: str = Field(
        default="google/gemini-3.1-pro-preview",
        description="Model for reflection writing and lesson extraction (default: analysis model)"
    )
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=4000)
    mindset_path: str = Field(
        default="data/mindset.md",
        description="Path to the human-readable reflection log file"
    )
    drawdown_threshold_pct: float = Field(
        default=20.0,
        description="Drawdown % from peak that triggers circuit breaker (RISK-01, D-10)"
    )
```

```python
# Add to RiskSettings (or fold into ReflectionSettings as above)
# Add to StakeSettings:
reflection: ReflectionSettings = Field(default_factory=ReflectionSettings)
```

### Reflection System Prompt Design (REFLECT-01, REFLECT-02)

```
# REFLECTION_SYSTEM_PROMPT (calibration-aware)
You are a professional betting analyst reviewing a resolved horse racing bet.

Your job is to write a calibration-focused reflection. The goal is NOT to celebrate wins
or explain losses — it's to identify where the model's PROBABILITIES were wrong.

Even in a winning bet, ask:
- Was the assigned probability accurate, or did we just get lucky?
- Did research data justify the confidence level?
- Was the Kelly sizing appropriate given what we knew?

Required sections:
1. What happened (1-2 sentences — just the facts)
2. Probability calibration (was ai_win_prob realistic?)
3. What went wrong (even if we won — overconfidence, missing signals, bad data)
4. What the market knew that we missed

Be blunt. Self-serving explanations erode the model's ability to improve.
```

### Lesson Extraction Contract

```python
class LessonEntry(BaseModel):
    """Structured lesson extracted from a reflection."""
    error_tag: str = Field(
        description="1-line category label for this type of error (e.g. 'overconfidence_on_short_odds')"
    )
    rule_sentence: str = Field(
        description="1 actionable rule sentence (e.g. 'Never exceed 15% of Kelly on runners with <5 races at distance')"
    )
    is_failure_mode: bool = Field(
        description="True if this is a failure mode (mistake to avoid), False if a positive rule to reinforce"
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Storing lessons as raw text files | SQLite queryable store with `application_count` | Phase 3 design | Enables `ORDER BY application_count DESC LIMIT 5` for most relevant lessons |
| Manual P&L tracking outside bot | `stake_bet_outcomes` table with `is_placed` flag | Phase 3 | Clean separation of placed (financial) vs tracked (model quality) |
| Drawdown check as post-analysis step | Pre-analysis short-circuit (before LLM) | Phase 3 design (D-09) | Saves API cost when drawdown is active |

---

## Open Questions

1. **Odds at recommendation time — storage gap**
   - What we know: `final_bets` list in pipeline result contains `decimal_odds` and `ev` but checking the model, `place_odds` are NOT currently in the `final_bets` dict keys (only `usdt_amount`, `ev`, `kelly_pct`, `bet_type`, `runner_name`, `runner_number`, `label`, `reasoning`, `data_sparse`).
   - What's unclear: Are `decimal_odds` and `place_odds_at_bet` accessible from FSM state when the result arrives?
   - Recommendation: Phase 3 must either (a) store odds into `stake_bet_outcomes` at the moment `final_bets` is produced (best), or (b) query `stake_pipeline_runs.parsed_race_json` to reconstruct odds at evaluation time (fragile). Option (a) is cleaner — add odds fields to the `final_bets` dict in `sizing_node` before they are stored in FSM.

2. **run_id linking — not yet written to FSM**
   - What we know: `stake_pipeline_runs` exists in migrations but the pipeline handlers don't currently INSERT a row or store `run_id` in FSM data.
   - What's unclear: Was this implemented in Phase 1/2 or deferred?
   - Recommendation: Plan should include a Wave 0 task that writes a row to `stake_pipeline_runs` on pipeline start (in `_run_analysis_inline`) and stores `run_id` in FSM state. Phase 3 result handler then reads `run_id` from FSM to link outcomes.

3. **Drawdown unlock persistence vs usability**
   - What we know: Storing `drawdown_unlocked` in SQLite is correct. But should it auto-reset when balance recovers to ≥80% of peak, or require explicit `/lock_drawdown` user action?
   - Recommendation: Auto-reset when balance recovers above `peak × (1 - threshold/100)`. Log the auto-reset to audit log. This avoids user confusion about whether protection is active.

4. **Stats period filter granularity**
   - What we know: STATS-01 requires "total, by period." Daily, weekly, monthly are the obvious periods.
   - Recommendation: Implement `/stats` with three views: all-time, last-30-days, last-7-days. Use `DATE(created_at)` filtering in SQL. More granularity can be added in a follow-up command.

---

## Environment Availability

Step 2.6: All dependencies are stdlib or already installed. No external tools required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | Yes | 3.13.3 | — |
| pytest | Testing | Yes | 9.0.2 | — |
| aiogram | FSM/handlers | Yes (installed) | 3.x | — |
| langchain-openai | Result parsing, reflection | Yes (installed) | existing | — |
| pydantic | Models | Yes (installed) | existing | — |
| sqlite3 | DB tables | Yes (stdlib) | stdlib | — |
| OpenRouter API | LLM calls | Configured | — | — |
| Redis | FSM storage | Yes (Docker) | — | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (pytest auto-discovers from project root) |
| Quick run command | `PYTHONPATH=. pytest tests/stake/ -x -q` |
| Full suite command | `PYTHONPATH=. pytest tests/stake/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESULT-01 | ResultParser accepts flexible text formats | unit | `pytest tests/stake/test_results.py::test_result_parser_flexible_input -x` | Wave 0 |
| RESULT-02 | ParsedResult marks low confidence on ambiguous input | unit | `pytest tests/stake/test_results.py::test_parsed_result_ambiguity -x` | Wave 0 |
| RESULT-03 | evaluate_bets() calculates correct P&L for win and place | unit | `pytest tests/stake/test_results.py::test_evaluate_bets_pl -x` | Wave 0 |
| RESULT-03 | evaluate_bets() returns evaluable=False for partial results | unit | `pytest tests/stake/test_results.py::test_evaluate_bets_partial -x` | Wave 0 |
| TRACK-01 | BetOutcomesRepository filters by is_placed in stats queries | unit | `pytest tests/stake/test_results.py::test_bet_outcomes_placed_filter -x` | Wave 0 |
| REFLECT-01 | ReflectionWriter appends to mindset.md in correct format | unit | `pytest tests/stake/test_reflection.py::test_reflection_writer_appends -x` | Wave 0 |
| REFLECT-03 | LessonExtractor returns LessonEntry with error_tag and rule_sentence | unit | `pytest tests/stake/test_reflection.py::test_lesson_extractor_structure -x` | Wave 0 |
| REFLECT-03 | _build_lessons_block() injects top-5 rules into prompt | unit | `pytest tests/stake/test_reflection.py::test_lessons_injected_in_prompt -x` | Wave 0 |
| STATS-01 | get_total_stats() returns correct totals for placed bets only | unit | `pytest tests/stake/test_results.py::test_stats_placed_only -x` | Wave 0 |
| RISK-01 | drawdown_check_node triggers skip at 20% drawdown | unit | `pytest tests/stake/test_results.py::test_drawdown_check_triggers -x` | Wave 0 |
| RISK-01 | drawdown_check_node does not trigger below 20% | unit | `pytest tests/stake/test_results.py::test_drawdown_check_no_trigger -x` | Wave 0 |
| RISK-01 | peak_balance updates when balance exceeds previous peak | unit | `pytest tests/stake/test_results.py::test_peak_balance_update -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `PYTHONPATH=. pytest tests/stake/ -x -q`
- **Per wave merge:** `PYTHONPATH=. pytest tests/stake/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/stake/test_results.py` — covers RESULT-01, RESULT-02, RESULT-03, TRACK-01, STATS-01, RISK-01
- [ ] `tests/stake/test_reflection.py` — covers REFLECT-01, REFLECT-03
- [ ] `services/stake/results/__init__.py` — package stub
- [ ] `services/stake/reflection/__init__.py` — package stub

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 3 |
|-----------|-------------------|
| ARCH-01: All numerical calculations in Python, never LLM | P&L math (profit, ROI, drawdown %) must be pure Python. LLM only for text→structured parsing and reflection prose. |
| Pydantic nested settings: nested classes = BaseModel not BaseSettings | `ReflectionSettings` and `RiskSettings` extend BaseModel |
| Pydantic objects NOT JSON-serializable for Redis FSM | All new state fields (`ParsedResult`, `BetOutcome`) stored as dicts via `model_dump()` |
| 64-byte callback limit | `TrackingCB` prefix `st:` + `action` must stay under 64 bytes: `st:placed` = 9 bytes, `st:tracked` = 10 bytes — safe |
| parse_mode=HTML — unescaped `<>` causes silent failures | `html.escape()` all LLM-generated text (reflection output, lesson sentences) before Telegram send |
| aiogram swallows errors — configure `@dp.errors()` | New handlers must not introduce unhandled exceptions; use try/except with fallback messages |
| venv required | `source venv/bin/activate` before any python test run |
| Context7 for library docs | Consult Context7 before using unfamiliar aiogram or LangChain APIs |
| Security: never display credentials | No tokens or API keys in any output |

---

## Sources

### Primary (HIGH confidence)

- Existing codebase — `services/stake/pipeline/nodes.py`, `state.py`, `graph.py`, `callbacks.py`, `states.py`, `bankroll/repository.py`, `bankroll/migrations.py`, `settings.py`, `audit/logger.py` — direct code inspection of all patterns to be reused
- SQLite documentation — `PRAGMA table_info()`, `ALTER TABLE`, `CREATE TABLE IF NOT EXISTS` — stdlib behavior
- Python stdlib `sqlite3` — aggregation queries (`SUM`, `COUNT`, `AVG`, `GROUP BY`)

### Secondary (MEDIUM confidence)

- Pydantic v2 `with_structured_output` pattern — verified in existing `llm_parser.py` and `analysis/models.py`; Phase 3 uses same pattern
- aiogram 3.x `StatesGroup` / `FSMContext` — verified in existing `states.py` and `pipeline.py`

### Tertiary (LOW confidence)

- None — all claims are verified from existing codebase or stdlib

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use, verified in codebase
- Architecture: HIGH — direct inspection of all patterns to be reused; no new architectural decisions
- Pitfalls: HIGH — most identified from direct code inspection (missing run_id, odds not in final_bets, ALTER TABLE idempotency)
- SQLite schemas (Claude's discretion areas): MEDIUM — schema is designed for correctness, but exact column set may be refined during planning

**Research date:** 2026-03-27
**Valid until:** 2026-05-27 (stable stack — Python, aiogram 3, SQLite; no fast-moving dependencies)
