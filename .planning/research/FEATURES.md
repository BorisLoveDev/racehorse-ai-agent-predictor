# Feature Landscape

**Domain:** Telegram AI Betting Advisor — manual-input horse racing analysis with bankroll management
**Project:** Stake Horse Racing Advisor Bot
**Researched:** 2026-03-23
**Confidence:** HIGH (features derived from explicit PROJECT.md requirements + ecosystem research)

---

## Table Stakes

Features users expect. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Raw text input parsing | Core premise — user pastes Stake.com page text | Medium | Must handle noise, formatting artifacts, partial data |
| Structured bet recommendation | Without this it is just commentary, not a betting advisor | High | Must produce specific horse numbers + amounts |
| Bankroll-aware bet sizing | Raw "bet on horse 3" is useless without sizing context | Medium | Kelly/fractional Kelly; show % AND absolute USDT |
| Skip / no-bet signal | Honest signal when margin makes bet -EV is a differentiator from dumb tipsters | Low | Should explain why (margin too high, no edge found) |
| Current balance shown in every response | User always knows their risk context | Low | Header of every message; ask if not known |
| Result input and P/L tracking | Closing the loop — did the bot make money? | Medium | User pastes result back; bot evaluates and logs |
| Session P/L summary | User needs to know if the bot is profitable | Low | Per-session and all-time |

## Differentiators

Features that set this product apart. Not expected by default, but valued highly once present.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Web research step per race | Contextualized tips vs. generic LLM guessing | Medium | SearXNG already running; ResearchAgent pattern exists |
| Reflective learning journal (mindset.md) | Bot improves over time; not a stateless tipster | Medium | AI writes structured reflection after each result; persisted on server |
| -EV detection with margin explanation | Teaches the user, not just tells them | Low | Calculate implied probability, remove vig, compare to LLM estimate |
| Multi-model consensus (Gemini + Grok) | Reduces single-model overconfidence | Medium | Same pattern as existing orchestrator; apply to Stake advisor |
| Fractional Kelly with configurable fraction | Risk-controlled sizing that survives variance | Low | Default quarter Kelly (0.25x); user-adjustable |
| Step-by-step pipeline visible in chat | User sees research → analysis → sizing steps; not a black box | Low | Send intermediate Telegram messages per stage |
| File input (.txt) fallback | Handles long race pages that exceed message limits | Low | Standard aiogram file handler |
| Search provider choice (SearXNG vs OpenRouter online) | Flexibility when SearXNG is down; matches existing config pattern | Low | Toggle via env var or bot command |

## Anti-Features

Features to explicitly NOT build in v1. Building them creates scope creep or fragile dependencies.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-scraping Stake.com | Anti-bot protection makes it unreliable; breaks often | Manual paste — explicitly in scope |
| Automatic bet placement | No API to Stake.com; legal risk; scope explosion | Recommendations only; user executes manually |
| Multi-sport support | Different form factors, different analysis heuristics; dilutes quality | Horse racing only for v1 |
| Multi-user support | Auth complexity; personal tool; single TELEGRAM_CHAT_ID | Single-user by design |
| Scheduled auto-monitoring | Stake.com has no public race feed we can poll reliably | User-initiated per race only |
| Full agent autonomy (v1) | Autonomous tool-calling is opaque, harder to debug and trust | Pipeline-first (AGENT-01 is explicitly v2) |
| Persist raw paste data long-term | PII / gambling data exposure risk; large storage overhead | Store structured output only (bets, outcomes, reflections) |
| Odds comparison across bookmakers | Scope expansion; requires multiple scrapers | Single source (Stake.com data user provides) |

## Feature Dependencies

```
INPUT-01/INPUT-02 (receive raw data)
  → PARSE-01 (extract race structure)
    → CLEAN-01 (optional LLM noise removal — improves PARSE-01 reliability)
    → SEARCH-01 (web research per participant — needs parsed names)
      → ANALYSIS-01 (AI recommendation — needs parsed data + research)
        → BET-02 (-EV detection — needs odds from PARSE-01 + AI probability from ANALYSIS-01)
        → BANK-01/BANK-02/BANK-03 (bankroll context — parallel to analysis)
          → BET-01/BET-03 (Kelly sizing — needs bankroll + AI probability + odds)
            → RESULT-01 (user pastes result — needs bet record from BET-03)
              → REFLECT-01 (reflection journal — needs result + original analysis)
                → STATS-01 (P/L summary — aggregates all RESULT-01 records)

PIPELINE-01 (wraps the above sequence into visible Telegram UX)
AGENT-01 (v2 — replaces the fixed pipeline with LLM-driven tool selection)
```

## MVP Recommendation

Prioritize this minimal set for a working, trustworthy v1:

1. **INPUT-01** — Text paste ingestion (file upload can come later)
2. **PARSE-01** — Reliable race + odds extraction (most fragile step; needs iteration)
3. **ANALYSIS-01** — Single-model AI analysis (Gemini only first; add Grok once pipeline works)
4. **BET-02** — -EV skip signal (builds trust; prevents bad bets immediately)
5. **BANK-01 + BANK-03** — Bankroll storage and display (makes sizing meaningful)
6. **BET-01 + BET-03** — Fractional Kelly sizing with USDT amounts
7. **RESULT-01** — Result paste and P/L logging (closes the feedback loop)
8. **STATS-01** — Basic P/L summary in Telegram

Defer to later phases:
- **CLEAN-01** — LLM cleanup adds latency and cost; test first if PARSE-01 handles real pastes well enough without it
- **SEARCH-01/SEARCH-02** — Valuable but ~$0.01–0.05 per race; add after core pipeline is stable
- **REFLECT-01** — Meaningful only after 10+ tracked races; defer to Phase 2
- **INPUT-02** — File upload is convenience only; text paste covers the use case
- **AGENT-01** — Explicitly v2

## Notes on Specific Features

### PARSE-01 — The Highest-Risk Feature

Stake.com page structure is unknown until a real paste arrives. Two viable approaches:

1. **LLM-first**: Send raw paste to LLM with a prompt asking it to extract JSON (race name, runners, odds). High reliability, ~$0.001–0.005 cost per parse. Simple to implement.
2. **Regex/heuristic first**: Fast, zero-cost, brittle if format changes.

**Recommendation**: Use LLM for initial extraction (same model as CLEAN-01, reducing one round-trip). Validate with Pydantic. If extraction confidence is low, ask user to clarify.

### BET-02 — -EV Detection Formula

For each runner:
- AI-estimated win probability `p` (from ANALYSIS-01)
- Bookmaker decimal odds `d` (from PARSE-01)
- Bookmaker implied probability `q = 1/d`
- Overround detection: sum of all `q` > 1.0 means vig exists
- EV calculation: `EV = p * d - 1`
- Skip signal: `EV <= 0` or AI confidence below threshold (0.5)

**Recommendation**: Show overround % in skip messages. Educates the user and builds trust in the skip signal.

### BET-01 — Kelly Implementation

Full Kelly is too aggressive for model-estimated probabilities (model error inflates `p`). Use quarter Kelly by default:

```
f* = (p * b - q) / b      # b = decimal odds - 1, q = 1 - p
bet_fraction = f* * 0.25  # quarter Kelly
bet_usdt = bet_fraction * bankroll
```

Cap at 5% bankroll per bet regardless of Kelly output (prevents catastrophic single-race loss from model overconfidence). Configurable via env or bot command.

### REFLECT-01 — Reflection Journal

After each RESULT-01, the AI writes a structured entry to `mindset.md` on the server. Entry includes:
- What the analysis predicted vs. what happened
- Whether the skip signal would have been correct
- One specific thing to adjust in future analysis prompts
- Running assessment of which race types / track conditions the model handles poorly

This file is read back into context for future races (as a "memory" injection into the system prompt). Confidence is LOW that this materially improves short-run accuracy but it surfaces patterns over 20+ races.

### PIPELINE-01 — Telegram UX Design

User sees progress via staged messages (not a single long wait):

```
[1/4] Parsing race data...        ← immediate
[2/4] Researching participants... ← after parse succeeds
[3/4] Running analysis...         ← after research
[4/4] Calculating bet sizing...   ← after analysis
--- RECOMMENDATION ---
```

Each step edits the previous message (Telegram `edit_message_text`) to avoid flooding. On error at any step, shows which step failed and what to retry.

## Feature Sizing Estimates

| Feature | Relative Effort | Risk |
|---------|-----------------|------|
| INPUT-01 text parsing | Small | Low |
| PARSE-01 LLM extraction | Medium | Medium — Stake format unknown |
| CLEAN-01 noise removal | Small | Low |
| SEARCH-01 web research | Small (ResearchAgent reuse) | Low |
| ANALYSIS-01 AI recommendation | Small (BaseRaceAgent reuse) | Low |
| BANK-01/02/03 bankroll CRUD | Small | Low |
| BET-01/02/03 Kelly sizing | Small | Low |
| RESULT-01 result input | Small | Low |
| REFLECT-01 mindset journal | Medium | Medium — LLM write quality |
| STATS-01 P/L display | Small | Low |
| PIPELINE-01 UX integration | Medium | Low |
| INPUT-02 file upload | Small | Low |
| AGENT-01 autonomous mode | Large | High |

## Sources

- PROJECT.md requirements list (HIGH confidence — canonical source)
- Kelly Criterion: [Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion), [Quant Matter](https://quantmatter.com/kelly-criterion-formula/), [betstamp](https://betstamp.app/education/kelly-criterion)
- Fractional Kelly rationale: [Matthew Downey analysis](https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html)
- LLM self-reflection in agents: [arxiv 2405.06682](https://arxiv.org/pdf/2405.06682) (MEDIUM confidence — academic, not betting-specific)
- AI horse racing features landscape: [horseracingsense.com](https://horseracingsense.com/ai-in-horse-racing-betting-and-training/), [biz4group.com](https://www.biz4group.com/blog/build-an-ai-virtual-horse-racing-betting-app) (LOW confidence — marketing content, used for feature enumeration only)
- Existing codebase patterns: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md` (HIGH confidence)
