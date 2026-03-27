# Phase 1: Foundation and Parser - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

User pastes raw Stake.com race text into Telegram bot. Bot parses it via configurable LLM into structured output, normalizes odds to decimal, calculates overround/implied probabilities via deterministic Python, handles scratched runners, manages bankroll (auto-extract from paste + manual command), displays parsed summary for user confirmation, and logs every pipeline run to audit trail. This is the new Stake advisor service replacing the existing bot on the same token.

</domain>

<decisions>
## Implementation Decisions

### Service Architecture
- **D-01:** New standalone Docker service (`services/stake/`) — completely separate from existing telegram service, not an extension
- **D-02:** Same Telegram bot token — this service replaces the existing bot entirely
- **D-03:** Reuse existing infrastructure: Redis for pub/sub and state, SQLite for persistence, Docker Compose on Meridian
- **D-04:** Branch isolation: new `stake-advisor` branch, no changes to existing services

### Parse Model and Structure
- **D-05:** LLM-based parser converts raw arbitrary text paste into structured output (Pydantic model)
- **D-06:** Parser model is configurable via env/config — cheap model (e.g., gemini-flash or similar), set in settings not hardcoded
- **D-07:** Full extraction — extract everything available in the paste:
  - **Race-level:** platform, sport, region/track, race number/name, date, distance, time to start, runner count, available bet types (Fixed, JP-SP, Trifecta, Exacta, Quinella), place payout rule
  - **Per-runner:** number, name, barrier/draw, weight, jockey, trainer, form string, opening odds (OP), current win odds, place odds, market rank/favouritism, tags/badges (Top Tip, Drawn Well, Speed Rating etc.), running style (Leader/Early Speed/Midfield/Off-Pace), tips/preview text
  - **Market context:** big bet activity feed, user activity, bet slip info if present
- **D-08:** Fields not present in the paste are marked null — LLM adapts to whatever Stake.com format is pasted
- **D-09:** Derived numerical values calculated by deterministic Python functions (ARCH-01), NOT by LLM:
  - Implied probability per runner (from odds)
  - Overround per market
  - Odds drift % (opening vs current)
  - Recalculated overround after scratches excluded
- **D-10:** Scratched runners get `status: "scratched"`, excluded from all calculations, flagged in output

### Bankroll Management
- **D-11:** Parser scans paste for any balance/bankroll mention — if found, triggers confirmation branch (user confirms/updates before continuing)
- **D-12:** If no bankroll in paste and no DB record — bot asks explicitly before pipeline continues
- **D-13:** `/balance` command (or menu equivalent) to set/view bankroll manually at any time
- **D-14:** Current USDT balance shown in header of every bot response
- **D-15:** Bankroll persists in SQLite, survives bot restarts
- **D-16:** User can set desired stake size as % of bankroll (not just absolute amount)

### Telegram UX
- **D-17:** Pipeline shows progressive messages — each step sends status updates in chat
- **D-18:** Use all Telegram features: inline keyboards for confirmations, reply markup, formatted messages (Markdown/HTML), callback buttons
- **D-19:** `/help` command with full explanation of all bot features and commands
- **D-20:** Statistics and bankroll accessible via dedicated menu/commands
- **D-21:** Intuitive, obvious interface — user should understand what to do without reading docs
- **D-22:** Parse confirmation step: bot displays formatted race summary, user must confirm (inline keyboard) before pipeline continues

### Pipeline & FSM
- **D-23:** LangGraph for pipeline orchestration (already installed, supports future agent mode)
- **D-24:** FSM state persists through bot restarts (RedisStorage backend)
- **D-25:** Only one active pipeline session per user; duplicate paste triggers warning
- **D-26:** User can `/cancel` active pipeline at any time

### Audit Trail
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — Full v1 requirements; Phase 1 covers INPUT-01/02, PARSE-01-06, BANK-01-05, PIPELINE-01-05, AUDIT-01
- `.planning/REQUIREMENTS.md` §Architectural Rules — ARCH-01: all numerical calculations by deterministic Python, never LLM

### Project context
- `.planning/PROJECT.md` — Vision, constraints, existing infrastructure details, framework decision (LangGraph)
- `.planning/PROJECT.md` §Constraints — Meridian server limits (2 vCPU, 4GB RAM), cost target (~$0.05-0.10/race)

### Existing patterns
- `services/telegram/main.py` — Existing aiogram bot patterns (callbacks, handlers, inline keyboards) — reference for Telegram UX conventions
- `services/telegram/callbacks.py` — CallbackData classes with 64-byte Telegram limit
- `services/telegram/keyboards.py` — Inline keyboard builder patterns
- `src/agents/base.py` — LangGraph workflow pattern (StateGraph, state machine design)
- `src/config/settings.py` — Pydantic Settings pattern with env prefix, nested delimiter
- `src/database/repositories.py` — Repository pattern for SQLite data access
- `src/database/migrations.py` — Schema migration pattern
- `src/models/bets.py` — Pydantic model examples for structured data

### Codebase maps
- `.planning/codebase/ARCHITECTURE.md` — System architecture overview
- `.planning/codebase/CONVENTIONS.md` — Naming, code style, import conventions
- `.planning/codebase/STRUCTURE.md` — Directory layout and file purposes

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **aiogram patterns** (`services/telegram/`): Existing bot with inline keyboards, callback handlers, formatted messages — direct reference for new Stake service UX
- **Pydantic Settings** (`src/config/settings.py`): Env-based config with `RACEHORSE_` prefix, nested delimiter `__` — extend for Stake-specific settings (parser model, bankroll defaults)
- **Repository pattern** (`src/database/repositories.py`): Data access layer for SQLite — extend for bankroll table and parsed race storage
- **Migration pattern** (`src/database/migrations.py`): Schema creation — add Stake-specific tables
- **LangGraph workflow** (`src/agents/base.py`): StateGraph pattern — adapt for pipeline FSM
- **Logging** (`src/logging_config.py`): Centralized logging with service formatter — reuse for stake service
- **Docker Compose** (`docker-compose.yml`): Add new service definition alongside existing ones

### Established Patterns
- **Redis pub/sub**: Services communicate via channels — stake service can use same pattern
- **Async/await everywhere**: All I/O operations are async (Playwright, Redis, HTTP)
- **Pydantic models for data validation**: Structured output models with field validators
- **CallbackData 64-byte limit**: Telegram callback data must use short prefixes

### Integration Points
- **Redis**: FSM state storage (RedisStorage), potential pub/sub for inter-service communication
- **SQLite `races.db`**: New tables for bankroll, parsed races, audit trail
- **Docker Compose**: New service entry in `docker-compose.yml`
- **Shared base image**: `Dockerfile.base` with Python dependencies

</code_context>

<specifics>
## Specific Ideas

- Parser must handle arbitrary text format — Stake.com pages may vary by region (Asia/Sonoda example provided), LLM must adapt
- Extract tags/badges that Stake.com shows (Top Tip, Drawn Well, Speed Rating) — these are useful signals for Phase 2 analysis
- Running style data (Leader/Early Speed/Midfield/Off-Pace) should be captured when present
- Big bet activity and user activity feeds should be captured as market context signals
- Place payout rule must be extracted explicitly (e.g., "three place dividends paid") — critical for Phase 2 bet sizing
- User wants menu-driven bankroll management — easy to set current balance and desired stake percentage
- User emphasizes: "it should be obvious how to use" — UX quality is a priority

</specifics>

<deferred>
## Deferred Ideas

- **Web research data** (Phase 2): Detailed race history per runner, jockey/trainer stats, career stats, sectional times, track bias, weather, pace maps — all come from web search, not paste parsing
- **Derived analysis features** (Phase 2): Consistency score, pace pressure score, draw advantage score, trainer/jockey form scores — calculated from research data
- **Market movement tracking** (Phase 2+): Strong odds movements over time, pari-mutuel SP/closing odds — requires multiple data points beyond single paste
- **Statistics viewing** (Phase 3): Full P&L stats, period analysis, win rate, ROI
- **Agent mode** (v2): LLM autonomously decides tool sequence — AGENT-01 explicitly deferred

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-parser*
*Context gathered: 2026-03-24*
