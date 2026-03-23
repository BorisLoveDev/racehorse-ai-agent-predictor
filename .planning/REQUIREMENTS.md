# Requirements: Stake Horse Racing Advisor Bot

**Defined:** 2026-03-23
**Core Value:** Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.

---

## v1 Requirements

### Input & Parsing

- [ ] **INPUT-01**: User can paste raw Stake.com page text directly into Telegram chat
- [ ] **INPUT-02**: User can send a .txt file with Stake.com race data
- [ ] **PARSE-01**: Cheap LLM extracts structured race info from raw paste (runners, odds, track name, race time, surface/track condition, coverage/place terms)
- [ ] **PARSE-02**: Parser is configurable — cheap model selection set via env/config (not hardcoded)
- [ ] **PARSE-03**: During parse step, LLM also scans for any bankroll/balance mention in the pasted text
- [ ] **PARSE-04**: Bot displays parsed summary to user for confirmation before proceeding to analysis

### Bankroll Management

- [ ] **BANK-01**: Bankroll stored in SQLite (USDT), updated after each resolved bet result
- [ ] **BANK-02**: If bankroll found in pasted text during parse → triggers separate confirmation branch asking user to confirm/update
- [ ] **BANK-03**: If no bankroll in text and no DB record → bot asks user explicitly ("What is your current balance?")
- [ ] **BANK-04**: Current balance shown in header of every bot response
- [ ] **BANK-05**: User can explicitly update balance: "balance: 150" or dedicated command

### Web Research

- [ ] **SEARCH-01**: Web research step searches for each runner's form, trainer stats, expert opinions, recent race history
- [ ] **SEARCH-02**: Search provider configurable: SearXNG (default) or OpenRouter online model — via env var

### Analysis

- [ ] **ANALYSIS-01**: AI produces structured analysis with favorite, dark horse, confidence per runner, and reasoning
- [ ] **ANALYSIS-02**: Overround/margin calculated from parsed odds; no-vig (fair) probability derived for each runner
- [ ] **ANALYSIS-03**: EV calculated using AI probability vs no-vig probability (not vs raw implied probability)

### Bet Sizing & Recommendations

- [ ] **BET-01**: Bet sizing uses Kelly criterion; default fraction = quarter Kelly (0.25×); configurable via env
- [ ] **BET-02**: Hard cap: never recommend more than 3% of bankroll per bet regardless of Kelly output
- [ ] **BET-03**: Skip signal issued when bookmaker margin makes bet structurally -EV (configurable threshold, default >15% overround)
- [ ] **BET-04**: Final output shows exact USDT amounts per bet type (win, place, exacta as applicable)
- [ ] **BET-05**: Place bet payout calculated using correct terms extracted from parse (not assumed as win odds)

### Pipeline UX

- [ ] **PIPELINE-01**: Pipeline runs step-by-step with progressive Telegram updates — user sees each step completing
- [ ] **PIPELINE-02**: If any step's data is ambiguous, bot asks user clarifying question before continuing
- [ ] **PIPELINE-03**: User can /cancel active pipeline at any time
- [ ] **PIPELINE-04**: Pipeline state persists through bot restarts (RedisStorage FSM backend)
- [ ] **PIPELINE-05**: Only one active pipeline session per user; duplicate paste triggers warning

### Results

- [ ] **RESULT-01**: User can submit race result as flexible text (e.g. "3,5,11,12" or "horse name won" or screenshot)
- [ ] **RESULT-02**: LLM parses result input into structured finishing order; asks for clarification if ambiguous
- [ ] **RESULT-03**: System evaluates each bet in the recommendation against actual result; calculates P&L

### Reflection

- [ ] **REFLECT-01**: After each evaluated result, AI writes a structured reflection entry to `mindset.md` on server
- [ ] **REFLECT-02**: Reflection asks "what went wrong even in winning bets" (calibration-aware, not just win/loss)
- [ ] **REFLECT-03**: `mindset.md` content injected into analysis system prompt (last 20 reflections + principles section)

### Statistics

- [ ] **STATS-01**: User can request P&L stats in Telegram (total, by period, win rate, ROI)

---

## v2 Requirements

### Agent Mode

- **AGENT-01**: LLM autonomously decides which tools to call and in what order (vs fixed pipeline)
- **AGENT-02**: Mode toggle in Telegram menu (pipeline mode / agent mode)
- **AGENT-03**: A/B comparison: track pipeline mode vs agent mode performance separately

### Advanced Analysis

- **ANALYSIS-04**: Multi-model consensus — Gemini + Grok analyze in parallel, recommendations merged
- **ANALYSIS-05**: Calibration tracking — after 50+ bets, map raw LLM confidence to calibrated probability; switch to Kelly on calibrated probs

### Bankroll

- **BANK-06**: Calibration-based stake sizing — flat 1% until 50+ resolved bets, then Kelly with calibrated probabilities

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic bet placement | No bookmaker API; recommendations only |
| TabTouch scraping | Existing system handles this; no overlap |
| Multi-sport (football, tennis, etc.) | Horse racing only for v1; different parsing + analysis required |
| Multiple users | Single-user personal tool; no auth needed |
| Real-time odds monitoring | Manual input model; no scraping |
| Full Kelly sizing | Dangerous without calibrated probabilities — hard-blocked in v1 |
| Mobile app | Telegram is the interface |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INPUT-01, INPUT-02 | Phase 1 | Pending |
| PARSE-01, PARSE-02, PARSE-03, PARSE-04 | Phase 1 | Pending |
| BANK-01, BANK-02, BANK-03, BANK-04, BANK-05 | Phase 1 | Pending |
| PIPELINE-01, PIPELINE-02, PIPELINE-03, PIPELINE-04, PIPELINE-05 | Phase 1 | Pending |
| SEARCH-01, SEARCH-02 | Phase 2 | Pending |
| ANALYSIS-01, ANALYSIS-02, ANALYSIS-03 | Phase 2 | Pending |
| BET-01, BET-02, BET-03, BET-04, BET-05 | Phase 2 | Pending |
| RESULT-01, RESULT-02, RESULT-03 | Phase 3 | Pending |
| REFLECT-01, REFLECT-02, REFLECT-03 | Phase 3 | Pending |
| STATS-01 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-23*
*Last updated: 2026-03-23 after initial definition*
