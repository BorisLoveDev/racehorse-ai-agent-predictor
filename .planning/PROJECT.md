# Stake Horse Racing Advisor Bot

## What This Is

A Telegram-driven AI betting advisor for horse racing on Stake.com. The user pastes raw page text from Stake.com directly into the bot, and the system runs it through a multi-step analysis pipeline: parsing odds → web research → AI analysis → bankroll-aware bet sizing → results tracking → reflective learning. Built as a service in the racehorse-agent repo on Meridian (Docker + Coolify).

## Core Value

Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.

## Requirements

### Validated

- ✓ OpenRouter API integration — existing infra
- ✓ SearXNG web search on Meridian — existing infra
- ✓ Telegram bot with aiogram, keyboards, callbacks — existing pattern
- ✓ SQLite persistence — existing pattern
- ✓ Docker Compose + Coolify deployment — existing infra
- ✓ Redis for FSM state persistence — existing infra
- ✓ **INPUT-01, INPUT-02**: Paste text or .txt file into Telegram — v1.0
- ✓ **PARSE-01–06**: LLM extraction, configurable model, odds normalization, scratched runners — v1.0
- ✓ **BANK-01–05**: SQLite bankroll, auto-detect from text, explicit update, balance header — v1.0
- ✓ **SEARCH-01, SEARCH-02**: Web research with configurable provider (SearXNG/OpenRouter) — v1.0
- ✓ **ANALYSIS-01–05**: Betting labels, overround math, EV vs no-vig, uncertainty discount, market discrepancy — v1.0
- ✓ **BET-01–07**: Deterministic Kelly sizing, portfolio caps, skip signal, USDT amounts, place payout — v1.0
- ✓ **PIPELINE-01–05**: Progressive updates, clarification, cancel, persistence, one-session guard — v1.0
- ✓ **AUDIT-01**: Append-only JSONL audit trail — v1.0
- ✓ **RESULT-01–03**: Flexible result text, LLM parse, P&L evaluation — v1.0
- ✓ **TRACK-01**: Placed vs tracked marking; stats use placed only — v1.0
- ✓ **REFLECT-01–03**: AI reflection to mindset.md, calibration-aware, lesson extraction + injection — v1.0
- ✓ **STATS-01**: /stats with all-time, 30-day, 7-day P&L — v1.0
- ✓ **RISK-01**: Drawdown circuit breaker at 20% from peak with unlock button — v1.0
- ✓ **ARCH-01**: All math is deterministic Python, LLM never generates bet amounts — v1.0

### Active

- [ ] **AGENT-01**: (v2) Agent mode — LLM autonomously decides which tools to call
- [ ] **AGENT-02**: Mode toggle in Telegram (pipeline / agent)
- [ ] **AGENT-03**: A/B comparison: pipeline vs agent mode performance tracking
- [ ] **MULTI-01**: Multi-model consensus — parallel analysis, merged recommendations
- [ ] **CALIB-01**: Calibration tracking — after 50+ bets, map confidence to calibrated probability
- [ ] **CALIB-02**: Calibration-based stake sizing — flat 1% until calibrated, then Kelly
- [ ] **MARKET-01**: Live odds freshness guard

### Out of Scope

- TabTouch scraping — manual-input only (Stake.com anti-bot)
- Automatic bet placement — no bookmaker API
- Multi-sport — horse racing only
- Multiple users — single-user personal tool
- Real-time odds monitoring — manual input model
- Full Kelly sizing — dangerous without calibration, hard-blocked
- Mobile app — Telegram is the interface
- Live odds reprice — requires API access

## Current State

**v1.0 MVP shipped 2026-03-27**

- 5,435 LOC Python (`services/stake/`), 3,589 LOC tests (`tests/stake/`)
- 210 unit tests passing
- 3 Docker containers: redis, searxng, stake
- Stack: Python 3.11, aiogram 3, LangChain/LangGraph, OpenRouter, Redis (FSM), SQLite
- Deployed on Meridian via Coolify

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Horse racing only (v1) | Focus scope, reuse existing AI knowledge | ✓ Good — shipped full pipeline |
| Manual input vs scraping | Stake.com anti-bot protection | ✓ Good — paste UX works |
| Pipeline-first, agent-mode later | Lower risk, working v1 faster | ✓ Good — pipeline proven, agent mode is v2 |
| LangGraph as framework | Already installed, zero migration, supports dual pipeline/agent | ✓ Good — clean node composition |
| SearXNG as default search | Already on Meridian, free | ⚠️ Revisit — defaulted to OpenRouter online for simpler dev |
| ARCH-01: Deterministic math | LLM hallucinating amounts is dangerous for betting | ✓ Good — enforced across all phases |
| Quarter-Kelly default (0.25×) | Conservative sizing for uncalibrated model | ✓ Good — configurable via STAKE_SIZING__* |
| Reflection with lesson injection | Learning loop improves analysis over time | ✓ Good — top-5 rules + last-3 failures injected |

## Constraints

- **Tech Stack**: Python 3.11, aiogram 3, LangGraph, OpenRouter, SQLite, Docker
- **Deployment**: Meridian server (2 vCPU, 4GB RAM) via Coolify
- **Cost**: Per-race analysis ~$0.01–0.05 (gemini-flash models)
- **Single user**: No auth, single chat ID in env

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-03-27 after v1.0 milestone*
