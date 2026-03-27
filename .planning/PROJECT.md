# Stake Horse Racing Advisor Bot

## What This Is

A Telegram-driven AI betting advisor for horse racing on Stake.com. The user pastes raw page text from Stake.com directly into the bot, and the system runs it through a multi-step analysis pipeline: parsing odds → web research → AI analysis → bankroll-aware bet sizing → results tracking → reflective learning. Built as a new branch/service in the existing racehorse-agent repo, sharing infrastructure (OpenRouter, SearXNG, Telegram bot token, SQLite, Docker on Meridian).

## Core Value

Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.

## Requirements

### Validated

- ✓ OpenRouter API integration (multi-model via `src/agents/`) — existing
- ✓ SearXNG web search container on Meridian (port 8080 internal / 8888 external) — existing
- ✓ Telegram bot with aiogram, inline keyboards, callback handlers — existing pattern
- ✓ SQLite persistence via `src/database/repositories.py` — existing
- ✓ Docker Compose deployment on Meridian via Coolify — existing
- ✓ Redis pub/sub message bus — existing infrastructure

### Active

- [ ] **INPUT-01**: User can paste raw Stake.com page text into Telegram chat
- [ ] **INPUT-02**: User can send a .txt file with Stake.com race data
- [ ] **PARSE-01**: Parser extracts race name, participants, odds from raw text
- [ ] **CLEAN-01**: Optional LLM-based cleanup step removes noise from raw paste
- [ ] **SEARCH-01**: Web research step finds form, trainer stats, expert opinions for race participants
- [ ] **SEARCH-02**: Search provider configurable: SearXNG (default) or OpenRouter online model
- [ ] **ANALYSIS-01**: AI analyzes all gathered data and produces structured recommendation (favorite, dark horse, skip signal)
- [ ] **BANK-01**: Bankroll stored in SQLite (USDT), updated after each resolved bet
- [ ] **BANK-02**: Bankroll auto-extracted from dialog context; bot asks if not found
- [ ] **BANK-03**: Current balance shown in every response header
- [ ] **BET-01**: Bet sizing calculated using professional bankroll management (Kelly criterion or similar)
- [ ] **BET-02**: Bot recommends skipping when bookmaker margin makes bet -EV
- [ ] **BET-03**: Final recommendation shows exact amounts per bet type
- [x] **RESULT-01**: User pastes race result back to bot; system evaluates prediction accuracy — Validated in Phase 03
- [x] **REFLECT-01**: After each result, AI writes reflection to `mindset.md` on server — Validated in Phase 03
- [x] **STATS-01**: Session and historical P&L visible in Telegram — Validated in Phase 03
- [ ] **PIPELINE-01**: Full pipeline runs step-by-step in Telegram conversation
- [ ] **AGENT-01**: (v2) Agent mode — LLM autonomously decides which tools to call and in what order

### Out of Scope

- TabTouch scraping — this system is manual-input only (Stake.com has anti-bot protection)
- Automatic bet placement — recommendations only, no API to bookmaker
- Multi-sport support — horse racing only for v1
- Multiple users — single-user bot (personal tool)
- Auto-monitoring / scheduled triggers — user-initiated per race

## Context

**Existing infrastructure reused:**
- OpenRouter API key + existing agent patterns (`src/agents/BaseAgent`, `StructuredBet`)
- SearXNG container already running on Meridian
- aiogram Telegram bot patterns (callbacks, keyboards, inline menus)
- SQLite + repositories pattern
- Docker Compose + Coolify on Meridian (46.30.43.46)

**Key difference from existing system:**
- Existing system: fully automated TabTouch scraper → auto-analysis → push notifications
- New system: manual Stake.com input → interactive pipeline → user-in-the-loop

**Framework decision pending research:**
- Current system uses plain asyncio (no agent framework)
- Need to evaluate: LangChain/LangGraph, PydanticAI, plain asyncio, or OpenRouter tool-use
- Decision criteria: best fit for pipeline + agent dual-mode, tool use quality, complexity

**Bankroll model:**
- Unit: USDT
- Extracted from dialog context first; DB fallback; explicit "balance: X" command
- All recommendations expressed as % of bank + absolute USDT amount

## Constraints

- **Tech Stack**: Python 3.13+, aiogram, OpenRouter API, SQLite, Docker — consistent with existing repo
- **Deployment**: Meridian server (2 vCPU, 4GB RAM) — no heavy ML models locally
- **Cost**: Per-race analysis cost should stay under existing agent cost profile (~$0.05–0.10)
- **Single user**: No auth required, single chat ID in env
- **Branch isolation**: New `stake-advisor` branch — no changes to existing services

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Horse racing only (v1) | Focus scope, reuse existing AI knowledge | — Pending |
| Manual input vs scraping | Stake.com anti-bot protection makes scraping unreliable | ✓ Good |
| Pipeline-first, agent-mode later | Lower risk, working v1 faster, agent mode built on proven pipeline | — Pending |
| SearXNG as default search | Already running on Meridian, free, no API key needed | — Pending |
| Framework choice | Undecided — research required before planning | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after Phase 03 completion — results, reflection, stats all verified*
