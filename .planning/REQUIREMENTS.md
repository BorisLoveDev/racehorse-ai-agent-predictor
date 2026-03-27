# Requirements: Stake Horse Racing Advisor Bot

**Defined:** 2026-03-23
**Core Value:** Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.

---

## v1 Requirements

### Input & Parsing

- [x] **INPUT-01**: User can paste raw Stake.com page text directly into Telegram chat
- [x] **INPUT-02**: User can send a .txt file with Stake.com race data
- [x] **PARSE-01**: Cheap LLM extracts structured race info from raw paste (runners, odds, track name, race time, surface/track condition, coverage/place terms)
- [x] **PARSE-02**: Parser is configurable — cheap model selection set via env/config (not hardcoded)
- [x] **PARSE-03**: During parse step, LLM also scans for any bankroll/balance mention in the pasted text
- [x] **PARSE-04**: Bot displays parsed summary to user for confirmation before proceeding to analysis
- [x] **PARSE-05**: Odds normalization sublayer converts all formats (decimal / fractional / American) to a single decimal internal representation; calculates raw implied probability and overround per market; validates place terms; covered by unit tests
- [x] **PARSE-06**: Each parsed runner has a `status` field (`active` | `scratched`); scratched runners are excluded from EV calculations and flagged in output

### Bankroll Management

- [x] **BANK-01**: Bankroll stored in SQLite (USDT), updated after each resolved bet result
- [x] **BANK-02**: If bankroll found in pasted text during parse → triggers separate confirmation branch asking user to confirm/update
- [x] **BANK-03**: If no bankroll in text and no DB record → bot asks user explicitly before continuing
- [x] **BANK-04**: Current balance shown in header of every bot response
- [x] **BANK-05**: User can explicitly update balance: "balance: 150" or dedicated command

### Web Research

- [x] **SEARCH-01**: Web research step searches for each runner's form, trainer stats, expert opinions, recent race history
- [x] **SEARCH-02**: Search provider configurable: SearXNG (default) or OpenRouter online model — via env var

### Analysis

- [x] **ANALYSIS-01**: AI produces structured analysis using betting-relevant labels per runner: `highest_win_probability`, `best_value` (max edge vs market), `best_place_candidate`, `no_bet` — not narrative labels like "favorite" or "dark horse"
- [x] **ANALYSIS-02**: Overround/margin calculated from parsed odds; no-vig (fair) probability derived for each runner (deterministic Python, not LLM)
- [x] **ANALYSIS-03**: EV calculated using AI probability vs no-vig probability (not vs raw implied probability) (deterministic Python, not LLM)
- [x] **ANALYSIS-04**: If research returns sparse data for a runner (no recent form, no trainer info, contradictory sources) — bot applies 50% uncertainty discount to recommended sizing for that runner; flagged in output
- [x] **ANALYSIS-05**: If research finds significantly different odds for the same runner in external sources — bot includes a market discrepancy note in the analysis output

### Bet Sizing & Recommendations

- [x] **BET-01**: All EV, Kelly fraction, and USDT sizing calculations performed by deterministic Python functions — LLM receives computed numbers, never generates final bet amounts from text
- [x] **BET-02**: Bet sizing uses Kelly criterion; default fraction = quarter Kelly (0.25×); configurable via env
- [x] **BET-03**: Hard cap per single bet: never recommend more than 3% of bankroll regardless of Kelly output
- [x] **BET-04**: Max total exposure per race: sum of all recommended bets capped at 5% of bankroll; max 2 win bets per single race
- [x] **BET-05**: Skip signal issued when bookmaker margin makes bet structurally -EV (configurable threshold, default >15% overround)
- [x] **BET-06**: Final output shows exact USDT amounts per bet type (win, place, exacta as applicable)
- [x] **BET-07**: Place bet payout calculated using correct terms extracted from parse (not assumed as win odds)

### Pipeline UX

- [x] **PIPELINE-01**: Pipeline runs step-by-step with progressive Telegram updates — user sees each step completing
- [x] **PIPELINE-02**: If any step's data is ambiguous, bot asks user clarifying question before continuing
- [x] **PIPELINE-03**: User can /cancel active pipeline at any time
- [x] **PIPELINE-04**: Pipeline state persists through bot restarts (RedisStorage FSM backend)
- [x] **PIPELINE-05**: Only one active pipeline session per user; duplicate paste triggers warning

### Audit Trail

- [x] **AUDIT-01**: Append-only log file records each pipeline run: raw input → parsed output → user confirmation/changes → recommendation → result (when submitted); stored as JSON lines on server

### Results

- [x] **RESULT-01**: User can submit race result as flexible text (e.g. "3,5,11,12" or "horse name won" or screenshot)
- [x] **RESULT-02**: LLM parses result input into structured finishing order; asks for clarification if ambiguous
- [x] **RESULT-03**: System evaluates each bet in the recommendation against actual result; calculates P&L
- [x] **TRACK-01**: Each recommendation can be marked `placed` (user actually bet) or `tracked` (recorded for calibration but not bet); P&L stats use `placed` only; model quality metrics use both

### Reflection

- [x] **REFLECT-01**: After each evaluated result, AI writes a structured reflection entry to `mindset.md` on server
- [x] **REFLECT-02**: Reflection explicitly asks "what went wrong even in winning bets" (calibration-aware, not just win/loss)
- [x] **REFLECT-03**: After each reflection, AI extracts one structured lesson: a free-text error tag (1 line) + a rule (1 sentence); top-5 extracted rules + last 3 failure modes are injected into the next race's analysis prompt — not raw reflection text

### Statistics & Risk Controls

- [x] **STATS-01**: User can request P&L stats in Telegram (total, by period, win rate, ROI) — `placed` bets only
- [x] **RISK-01**: Drawdown circuit breaker: if bankroll drops ≥20% from its peak value, system automatically enters skip-only mode; all recommendations output as "SKIP (drawdown protection)" until user manually unlocks

---

## Architectural Rules

These are not features — they are implementation constraints that apply across all phases.

- **ARCH-01 — Deterministic math engine**: All numerical calculations (implied probability, overround, no-vig probability, EV, Kelly fraction, USDT amounts) are performed by pure Python functions with no LLM involvement. LLM receives computed values as inputs to its analysis. LLM never generates final bet amounts from natural language.

---

## v2 Requirements

### Agent Mode

- **AGENT-01**: LLM autonomously decides which tools to call and in what order (vs fixed pipeline)
- **AGENT-02**: Mode toggle in Telegram menu (pipeline mode / agent mode)
- **AGENT-03**: A/B comparison: track pipeline mode vs agent mode performance separately

### Advanced Analysis

- **MULTI-01**: Multi-model consensus — Gemini + Grok analyze in parallel, recommendations merged
- **CALIB-01**: Calibration tracking — after 50+ bets, map raw LLM confidence to calibrated probability; switch to Kelly on calibrated probs
- **CALIB-02**: Calibration-based stake sizing — flat 1% until 50+ resolved bets, then Kelly with calibrated probabilities

### Market Data

- **MARKET-01**: Live odds freshness guard — detect and alert when odds at time of analysis differ significantly from odds at time of paste; full reprice requires API access

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
| Live odds reprice | Requires API access; v2+ when available |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INPUT-01, INPUT-02 | Phase 1 | Pending |
| PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05, PARSE-06 | Phase 1 | Pending |
| BANK-01, BANK-02, BANK-03, BANK-04, BANK-05 | Phase 1 | Pending |
| PIPELINE-01, PIPELINE-02, PIPELINE-03, PIPELINE-04, PIPELINE-05 | Phase 1 | Pending |
| AUDIT-01 | Phase 1 | Complete |
| SEARCH-01, SEARCH-02 | Phase 2 | Pending |
| ANALYSIS-01, ANALYSIS-02, ANALYSIS-03, ANALYSIS-04, ANALYSIS-05 | Phase 2 | Pending |
| BET-01, BET-02, BET-03, BET-04, BET-05, BET-06, BET-07 | Phase 2 | Pending |
| RESULT-01, RESULT-02, RESULT-03, TRACK-01 | Phase 3 | Pending |
| REFLECT-01, REFLECT-02, REFLECT-03 | Phase 3 | Pending |
| STATS-01, RISK-01 | Phase 3 | Pending |
| ARCH-01 | All phases | Pending |

**Coverage:**
- v1 requirements: 41 total (+ 1 arch rule)
- Mapped to phases: 41
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-23*
*Last updated: 2026-03-23 — amended v1.1: +8 requirements, REFLECT-03 revised, ARCH-01 added*
