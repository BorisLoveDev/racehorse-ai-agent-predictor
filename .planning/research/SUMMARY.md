# Research Summary: Stake Horse Racing Advisor Bot

**Project:** Stake Horse Racing Advisor Bot
**Domain:** Interactive AI betting advisor — manual input, multi-step pipeline, bankroll management
**Researched:** 2026-03-23
**Confidence:** HIGH

## Executive Summary

This is a Telegram-based interactive AI advisor for horse racing on Stake.com. The user pastes raw race page text into the bot; the system runs it through a fixed 8-step pipeline (parse → clean → research → analyse → bankroll fetch → Kelly sizing → format → reflect). The recommended approach is to build this as a 6th Docker service in the existing repo, reusing LangGraph (already installed), the existing `BaseRaceAgent`, `WebResearcher`, aiogram, RedisStorage FSM, and the SQLite repository pattern. The framework question that was listed as "pending research" in PROJECT.md is resolved: continue with LangGraph. There is zero migration cost and the dual pipeline/agent-mode architecture is a natural extension of what already exists.

The highest-risk feature is PARSE-01: Stake.com paste format is unknown until real data arrives, and every downstream step depends on its output. Use LLM-first extraction (not regex) validated with Pydantic, with explicit user confirmation of the parsed race structure before the pipeline continues. The second critical risk cluster is financial math: EV calculations that do not strip bookmaker margin, incorrect Kelly formula (using decimal odds as `b` instead of `decimal - 1`), and applying Kelly sizing before the AI has a calibrated track record (minimum 50 resolved bets). These are not implementation details — they are the difference between a trustworthy advisor and one that accelerates bankroll ruin.

Agent mode (AGENT-01) is explicitly v2. Mixing LLM-driven tool selection into the pipeline before it is fully validated is a documented anti-pattern (creates hybrid code harder to debug than either pure mode). Every pipeline step should be written as a standalone async function callable from both the sequential runner and a future LangGraph ReAct loop. Build the pipeline completely, observe it on real races, then add agent mode without rewriting the steps.

---

## Key Findings

### Recommended Stack

The framework decision that was open in PROJECT.md is settled. LangGraph is already installed and already used in `src/agents/base.py` as a 4-node `StateGraph`. Building the advisor service on LangGraph continues the existing pattern, avoids a new dependency on the memory-constrained Meridian server (2 vCPU, 4GB RAM), and delivers the dual pipeline/agent-mode design without code duplication. PydanticAI v1 is technically cleaner but would split the codebase and is a new dependency for no user-visible gain. Plain asyncio cannot serve both modes without duplicating 90% of logic.

Conversation state is managed via aiogram FSM with `RedisStorage` (Redis is already running on Meridian). Bankroll and completed sessions persist to SQLite using the existing `repositories.py` pattern. A `pipeline_running` FSM state acts as a lock preventing duplicate pipeline submissions. The reflection journal (`mindset.md`) is written to a Docker volume and injected as a system-prompt prefix.

**Core technologies:**
- `langgraph` >= 1.0: Pipeline DAG + future agent mode graph — already installed, zero migration cost
- `langchain-openai` + `langchain-core`: `ChatOpenAI` with OpenRouter `base_url` — already wired in `base.py`
- `aiogram` 3.x with `RedisStorage`: Telegram FSM, inline keyboards, Scenes for state isolation — already installed
- `pydantic` >= 2.0: Model validation for all structured outputs (`ParsedRace`, `BetRecommendation`, etc.) — already installed
- `httpx`: Async HTTP for SearXNG queries — already used
- Kelly criterion: Implement inline (5 lines of math). No library needed.

**What to skip:**
- `pydantic-ai`: Splits codebase, new dep, no gain
- `crewai`, `haystack`, `autogen`: Wrong abstraction for this use case
- `MemoryStorage` (aiogram): Lost on restart — `RedisStorage` only

### Expected Features

PARSE-01 is the most fragile feature and unblocks everything downstream. It warrants iteration time before treating it as done. Use LLM-based extraction from the start; confirm parsed output with the user before the pipeline proceeds.

**Must have (table stakes) — v1:**
- INPUT-01: Raw Stake.com text paste ingestion
- PARSE-01: LLM-based race + odds extraction, Pydantic-validated, user-confirmed
- ANALYSIS-01: Single-model AI recommendation (Gemini first; Grok addable once pipeline stable)
- BET-02: -EV skip signal with overround explanation (builds trust immediately)
- BANK-01 + BANK-03: Bankroll CRUD in SQLite, shown in every response header
- BET-01 + BET-03: Quarter-Kelly sizing with hard 3% bankroll cap, displayed as % and absolute USDT
- RESULT-01: Result paste back to bot, P&L evaluation
- STATS-01: Session and all-time P&L in Telegram
- PIPELINE-01: Step-by-step progress visible in chat (editing same message per stage)

**Should have (differentiators) — add after core pipeline stable:**
- SEARCH-01: Per-participant web research via SearXNG (WebResearcher already exists)
- REFLECT-01: AI reflection journal to `mindset.md` after each result — meaningful after 10+ tracked races
- CLEAN-01: LLM noise removal pre-parse — test first if PARSE-01 handles real pastes without it
- Multi-model consensus (Gemini + Grok) — same orchestrator pattern already used in existing services

**Defer to v2+:**
- AGENT-01: Autonomous LLM tool selection — explicitly post-pipeline
- INPUT-02: File upload — convenience only, paste covers the case
- SEARCH-02: Search provider toggle — SearXNG is already running and sufficient

**Anti-features (do not build):**
- Auto-scraping Stake.com (anti-bot protection)
- Automatic bet placement (no API, legal risk)
- Multi-sport, multi-user, scheduled monitoring

### Architecture Approach

The new `stake-advisor` service is a standalone 6th Docker service. It shares the `src/` package (agents, web search, config, logging) read-only and adds new SQLite tables (`advisor_sessions`, `advisor_bankroll`) via a new migration. It never touches existing services. The core design is `AdvisorSession` — a Pydantic model that accumulates state across all 8 pipeline steps. This object is serialised as JSON into aiogram `FSMContext` (RedisStorage) so it survives bot restarts. Bankroll and completed sessions go to SQLite for durability beyond Redis TTL.

**Major components:**
1. `AdvisorBot` (`services/stake-advisor/main.py`) — Dispatcher, FSM wiring, RedisStorage
2. `PipelineRunner` (`pipeline/runner.py`) — sequential async step executor, streams progress to Telegram
3. Pipeline Steps (`pipeline/steps/`) — one file per step; each step is a pure `async def` callable from both runner and future LangGraph `@tool` wrappers
4. `SessionStore` (`session.py`) — reads/writes `AdvisorSession` via FSMContext
5. `BankrollRepo` (`db/bankroll.py`) — SQLite CRUD for USDT balance
6. `MindsetStore` (`mindset.py`) — reads/appends `mindset.md`; injects last 20 reflections into analysis prompt
7. `AgentExecutor` (`agent/executor.py`) — v2 only; LangGraph ReAct loop wrapping steps as `@tool`
8. Handlers + Keyboards — aiogram message/callback handlers, reusing existing patterns from Telegram service

### Critical Pitfalls

1. **Bookmaker margin not stripped before EV calculation** — Always compute overround first (`sum(1/odds) - 1`); use no-vig probability in EV; hard-flag races where overround > 15%. The BET-02 skip signal must be triggered by margin math, not AI confidence alone. (Phase 1/2)

2. **Kelly formula applied with wrong `b` value** — `b = decimal_odds - 1` (net profit), not `decimal_odds`. Default quarter-Kelly (0.25x multiplier). Hard cap: never exceed 3% of bankroll regardless of Kelly output. Do not apply Kelly sizing at all until 50+ resolved bets provide calibration data; use flat 1% of bankroll until then. (Phase 2)

3. **PARSE-01 LLM hallucinating missing race data** — Prompt must say "extract only what is present; return null if ambiguous." Show parsed result to user before pipeline continues. Never treat first-pass parse as ground truth. (Phase 1)

4. **Stake.com paste format is unstable** — Scratched runners appear as SCR (must exclude from EV), multiple odds per runner, odds format ambiguity (decimal/fractional/moneyline), mobile vs desktop paste differences. LLM-based cleanup is more robust than regex. Validate with strict Pydantic after cleanup. (Phase 1)

5. **Pipeline state lost on bot restart or concurrent submissions** — FSM state + `AdvisorSession` must be in RedisStorage from day one. Gate all handlers via FSM state — prevent new pipeline while one is running. Session ID (UUID) per pipeline run. (Phase 1, before any pipeline step is written)

6. **Reflection log inflating AI confidence after win streaks** — Reflection prompt must explicitly ask what went wrong even on winning bets. Store reflections in SQLite with timestamps; active context = last 20 entries + rolling summary. `mindset.md` is human-readable export only. (Phase 3)

7. **Introducing partial agent behaviour before pipeline is proven** — Hybrid pipeline/agent code is harder to debug than either pure form. Agent mode behind a feature flag. Pipeline must be fully tested on real races before any `@tool` wrapper is written. (Phase 4+)

---

## Implications for Roadmap

### Phase 1: Foundation and Parser

**Rationale:** PARSE-01 unblocks everything. Every downstream step requires a `ParsedRace`. The FSM state design must also be in place before any pipeline step is written — retrofitting FSM later is significantly harder. These two pieces are the load-bearing foundation.

**Delivers:** Working paste ingestion, LLM-based race/odds extraction with user confirmation, FSM state machine, RedisStorage wiring, SQLite migration for `advisor_bankroll` and `advisor_sessions`, Docker service skeleton.

**Features addressed:** INPUT-01, PARSE-01, CLEAN-01 (as a pass-through stub initially), BANK-01, PIPELINE-01 (structural only)

**Pitfalls to avoid:**
- Set up FSM and RedisStorage before writing any step — never retrofit
- LLM cleanup prompt: "extract only what is present" — no hallucination
- Show parsed race to user before pipeline continues
- Scratcher detection mandatory at parse time

**Research flag:** Needs per-phase research. Stake.com paste format is unknown until real data arrives. Plan one iteration cycle with real paste samples before treating PARSE-01 as done.

---

### Phase 2: EV Engine and Bet Sizing

**Rationale:** Once parsing is reliable, the financial math layer is the highest-value and highest-risk addition. This phase is the core proposition — without correct EV and Kelly sizing, the bot gives worse advice than a coin flip. Get the math right before adding AI analysis.

**Delivers:** Overround detection, no-vig probability calculation, -EV skip signal with margin explanation, quarter-Kelly sizing with hard 3% cap, bankroll display in every message, USDT bet amounts.

**Features addressed:** BET-01, BET-02, BET-03, BANK-02, BANK-03

**Stack elements used:** Kelly formula implemented inline (5 lines). Pydantic models for `BetRecommendation`. Flat 1% bankroll sizing until calibration data exists (50+ resolved bets).

**Pitfalls to avoid:**
- `b = decimal_odds - 1`, never `b = decimal_odds`
- No-vig probability before EV, not raw implied probability
- Place bet payout = `(win_odds - 1) / 4 + 1` for standard terms — separate function per bet type
- Hard 3% bankroll cap regardless of Kelly output
- Unit-test Kelly and EV functions with known inputs before deploying

**Research flag:** Standard mathematical patterns — no additional research needed. Unit tests are the validation mechanism.

---

### Phase 3: AI Analysis and Full Pipeline

**Rationale:** With parsing and math correct, add the AI analysis layer. This is lower-risk than the math because `BaseRaceAgent` already exists and the LangGraph pattern is proven. The sequential pipeline runner also belongs here — it connects all steps into the Telegram UX flow.

**Delivers:** Working end-to-end pipeline for a race. User pastes data; bot returns specific bet recommendation with USDT amounts within ~30–60 seconds. Step-by-step progress visible in chat.

**Features addressed:** ANALYSIS-01, SEARCH-01, PIPELINE-01 (full), RESULT-01, STATS-01

**Architecture component:** `PipelineRunner` with `on_step_done` callback streaming intermediate messages. `step_search` wraps existing `WebResearcher`. `step_analyze` adapts `BaseRaceAgent` to `AdvisorSession`.

**Pitfalls to avoid:**
- Cache LLM outputs to SQLite immediately after generation — do not re-run LLM in later steps
- Web search queries must include race date/venue to avoid same-name horse data pollution
- Mark search as "low confidence" if no result found within 3 attempts with date proximity match
- Non-determinism: same session always reads from cache, never re-calls LLM

**Research flag:** Well-documented patterns (LangGraph, WebResearcher already proven). Skip research-phase. Monitor first-run latency — if > 60 seconds, investigate which step is blocking.

---

### Phase 4: Reflection and Learning Loop

**Rationale:** Meaningful only after 10+ tracked races. Build last because it reads from RESULT-01 data (Phase 3) and its output quality improves with volume. Implement reflections in SQLite first, `mindset.md` as export — not the other way around.

**Delivers:** Post-result AI reflection, `mindset.md` journal, rolling summary generation every 20 entries, calibration tracking (predicted confidence vs actual win rate), P&L summary enhancement.

**Features addressed:** REFLECT-01, enhanced STATS-01

**Pitfalls to avoid:**
- Reflection prompt: "What went wrong even on winning bets?" — explicit anti-inflation instruction
- Rolling summary every 20 reflections — prevent unbounded growth and context quality degradation
- Track calibration data in every entry, not just win/loss — needed to justify switching from flat to Kelly sizing
- Reflection context: last 20 entries + all active principles injected into analysis prompt

**Research flag:** LLM reflection quality for improving betting analysis is LOW-confidence academically (useful only after 20+ races). No additional research needed — observe in production.

---

### Phase 5: Agent Mode (v2)

**Rationale:** Build after the pipeline has been validated on real races. Agent mode wraps the same step functions as LangGraph `@tool` — no step rewriting required by design. The `AgentExecutor` is a LangGraph ReAct loop providing these tools to an LLM.

**Delivers:** LLM-autonomous tool selection mode, mode toggle via Redis key + bot menu, fallback to pipeline mode on agent error.

**Features addressed:** AGENT-01

**Pitfalls to avoid:**
- Agent mode behind a feature flag — never active while pipeline validation is ongoing
- Steps remain pure async functions — `@tool` wrappers are thin adapters only
- Do not add conditional pipeline logic in anticipation of agent mode — wait until v2

**Research flag:** LangGraph ReAct tool loop is well-documented. Skip research-phase. The main risk is LLM hallucinating tool calls — add validation that called tool name exists before executing.

---

### Phase Ordering Rationale

- **Parser first** because every step depends on it, and its format is unknown until real data arrives. Iteration time is built in by design.
- **Math layer second** because financial correctness is the entire value proposition. Getting EV/Kelly wrong in Phase 3 would require retroactively fixing all recommendations.
- **AI pipeline third** because `BaseRaceAgent` is low-risk (proven pattern), and the pipeline runner is straightforward once steps exist.
- **Reflection fourth** because it needs data volume to be meaningful and depends on RESULT-01 (Phase 3).
- **Agent mode last** because it is explicitly v2 and shares no code with the pipeline — it only wraps it.

### Research Flags

Phases needing deeper research during planning:
- **Phase 1:** Stake.com paste format is unknown. Plan one iteration cycle with real paste samples. LLM extraction prompt may need tuning based on actual format.

Phases with standard patterns (skip research-phase):
- **Phase 2:** Kelly/EV math is settled. Validate with unit tests, not research.
- **Phase 3:** LangGraph + WebResearcher patterns are proven in this codebase. Observe latency in production.
- **Phase 4:** Reflection quality is observable in production. No pre-research needed.
- **Phase 5:** LangGraph ReAct tool loop is documented. Standard implementation.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | LangGraph already installed and used. All libraries verified against existing codebase. Framework question definitively resolved. |
| Features | HIGH | Derived from explicit PROJECT.md requirements + standard betting advisor patterns. Anti-features and deferred scope well-reasoned. |
| Architecture | HIGH | Patterns drawn from existing working code (`base.py`, `repositories.py`, Telegram service). Component boundaries clear and non-overlapping. |
| Pitfalls | HIGH (math), MEDIUM (reflection) | EV/Kelly math pitfalls are mathematical facts. Reflection loop quality improvements are LOW-confidence academically — observable only in production. |

**Overall confidence:** HIGH

### Gaps to Address

- **Stake.com paste format:** The single largest unknown. No real paste sample was available during research. Phase 1 must treat PARSE-01 as experimental and plan an iteration cycle. CLEAN-01 may need to be activated immediately if raw parsing fails on first real data.

- **AI calibration timeline:** Kelly sizing should not activate until 50+ resolved bets. The bot will operate on flat 1% sizing initially. The transition trigger (how to auto-detect calibration threshold) needs to be specified during Phase 2 planning.

- **Place bet terms on Stake.com:** UK 1/4-odds convention assumed but not confirmed. Parser must extract explicit place terms from paste; if absent, prompt user before calculating place EV.

- **Reflection quality threshold:** Whether the `mindset.md` injection materially improves recommendations is empirically uncertain. Set a checkpoint at 20 races to evaluate and decide whether to continue or simplify.

---

## Sources

### Primary (HIGH confidence)
- Existing codebase — `src/agents/base.py`, `src/web_search/`, `services/telegram/`, `src/database/repositories.py`
- PROJECT.md — canonical requirements
- LangGraph 1.0 docs — StateGraph, conditional edges, tool wrapping
- aiogram 3.x docs — FSM Storages, Scenes, RedisStorage, CallbackData 64-byte limit

### Secondary (MEDIUM confidence)
- [ZenML: PydanticAI vs LangGraph](https://www.zenml.io/blog/pydantic-ai-vs-langgraph) — framework comparison
- [Langfuse agent framework comparison 2025](https://langfuse.com/blog/2025-03-19-ai-agent-comparison)
- [Fractional Kelly rationale](https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html) — quarter-Kelly standard
- [Mathematics of bookmaking — Wikipedia](https://en.wikipedia.org/wiki/Mathematics_of_bookmaking) — overround/margin formulas
- [Machine learning for sports betting: calibration — arXiv 2303.06021](https://arxiv.org/abs/2303.06021) — calibration vs accuracy ROI finding
- [Kelly Criterion — Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Agentic Design Patterns — DeepLearning.AI](https://www.deeplearning.ai/the-batch/agentic-design-patterns-part-2-reflection/) — reflection loop pattern

### Tertiary (LOW confidence)
- [arXiv 2405.06682](https://arxiv.org/pdf/2405.06682) — LLM self-reflection improving accuracy (academic, not betting-specific)
- [horseracingsense.com](https://horseracingsense.com/ai-in-horse-racing-betting-and-training/), [biz4group.com](https://www.biz4group.com/blog/build-an-ai-virtual-horse-racing-betting-app) — feature enumeration only (marketing content)

---
*Research completed: 2026-03-23*
*Ready for roadmap: yes*
