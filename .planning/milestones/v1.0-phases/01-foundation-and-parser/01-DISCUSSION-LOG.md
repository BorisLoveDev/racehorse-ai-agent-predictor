# Phase 1: Foundation and Parser - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 01-foundation-and-parser
**Areas discussed:** Parse structure, Telegram conversation flow, Service architecture, Bankroll management

---

## Parse Output Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Full extraction | Race name, track, surface, distance, race time, place terms, plus per-runner: number, name, jockey, trainer, weight, barrier, odds, status. Overround calculated automatically. | ✓ |
| Minimal extraction | Race name, track, plus per-runner: number, name, odds, status. Skip jockey/trainer/weight/barrier. | |
| Adaptive extraction | Extract everything available, mark missing fields as null. | |

**User's choice:** Full extraction — with extensive additional fields
**Notes:** User provided a detailed 3-tier field list:
1. **From paste directly:** Platform, region/track, race number/name, date, distance, time to start, runner count, bet types, per-runner (number, name, barrier, weight, jockey, trainer, form string, opening odds, current win/place odds, market rank, tags/badges, running style, tips), place payout rule, big bet activity
2. **From web research (Phase 2):** Detailed race history, track/distance/surface-specific history, speed figures, career stats, jockey/trainer stats, sectional times, market movements
3. **Nice-to-have derived features (Phase 2+):** Pace map, track bias, weather, class changes, derived scores (consistency, pace pressure, draw advantage)

Scope boundary confirmed: Phase 1 parser extracts only what's in the paste. Lists 2 and 3 are Phase 2 web research.

---

## Telegram Conversation Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Progressive messages | Each pipeline step sends a new message | |
| Single message, edit-in-place | One message updated as pipeline progresses | |
| Hybrid | Edit during processing, new message for results | |

**User's choice:** Claude's discretion — design the best possible UX
**Notes:** User wants all Telegram features utilized: inline keyboards, reply markup, formatted messages, buttons, menus. Must include /help command. Statistics accessible. Interface should be "obvious" and intuitive. User explicitly delegated UX design decisions to Claude.

---

## Service Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| New standalone service | Separate services/stake/ with own Dockerfile, main.py, FSM. Shares Redis + SQLite. | ✓ |
| Extend existing telegram service | Add Stake handlers to existing service. | |
| Same bot token, separate service | New service on same token via router separation. | |

**User's choice:** New standalone service, replaces existing bot, same token
**Notes:** User confirmed: completely new service. Reuse Redis/SQLite. This service REPLACES the existing bot — same Telegram bot token. User mentioned willingness to move to separate project if needed, but prefers keeping in same repo.

---

## Bankroll Interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Inline + command | Parser checks paste for balance, confirms with user. Plus /balance command. | ✓ |
| Command only | Only /balance command, no paste extraction. | |
| Auto-extract, no confirm | Auto-update from paste without asking. | |

**User's choice:** Inline + command (first option)
**Notes:** User confirmed full approach. Additional requirement captured: user wants to set desired stake size as % of bankroll (not just absolute USDT amount). Wants a dedicated menu for bankroll management where balance and stake percentage are easily adjustable.

---

## Claude's Discretion

- Telegram message formatting and layout design
- FSM state names and transitions
- Audit log format details
- Error handling and recovery flows
- Inline keyboard layouts
- Ambiguous paste handling strategy
- Processing indicators

## Deferred Ideas

- Web research for runner history/stats — Phase 2
- Derived analysis features (pace scores, consistency) — Phase 2
- Market movement tracking — Phase 2+
- Full P&L statistics — Phase 3
- Agent mode — v2
