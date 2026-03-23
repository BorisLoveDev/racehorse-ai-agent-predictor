# Pitfalls Research: AI Betting Advisor

**Domain:** AI betting advisor — manual input, Kelly sizing, reflection loop, Telegram interface
**Researched:** 2026-03-23
**Overall confidence:** HIGH (EV/Kelly math), MEDIUM (parsing, state), MEDIUM (reflection loops)

---

## EV & Payout Calculation Pitfalls

### CRITICAL — The "Won But Lost" Scenario: Ignoring Bookmaker Margin in EV

**What goes wrong:**
You win the bet (horse finishes first) but your total P&L is negative. This happens when the odds are below "fair value" due to the bookmaker's margin (overround), and EV is calculated using the raw implied probability from offered odds — not the true no-vig probability.

**Why it happens:**
Bookmaker odds always sum to more than 100% implied probability. For a 6-runner race, typical overround is 110–120%. If you convert offered odds directly to implied probability without stripping the margin, your EV looks positive when it's structurally negative.

```
Horse A offered at 3.00 (decimal) → raw implied prob = 33.3%
But true no-vig probability might only be 28% after removing margin.

EV = (0.333 × 2.00) − (0.667 × 1.00) = +0.00  → looks break-even
EV = (0.28  × 2.00) − (0.72  × 1.00) = −0.16  → actually -EV
```

**Prevention:**
1. Always compute overround first: `sum(1/decimal_odds for all runners) - 1.0`
2. No-vig probability: `implied_prob / overround_sum` for each runner
3. EV only positive if AI's estimated win probability exceeds no-vig probability
4. Hard rule: if overround > 15%, flag the race as likely -EV
5. BET-02 skip signal must be triggered by margin check, not just AI confidence

**Phase:** Phase 1 (parser), Phase 2 (EV engine). Margin calculation is a first-class function.

---

### CRITICAL — Place Bet Payout Misunderstanding

**What goes wrong:** Place bets pay a fraction of win odds. UK/Australian convention: `place payout = (win_odds - 1) / 4 + 1` for standard 3-place terms.

```
Horse at 10.0 decimal win odds
Place payout (1/4 odds, 3 places) = (10.0 - 1) / 4 + 1 = 3.25
Using 10.0 for place EV calculation is wrong by 3×.
```

**Prevention:** Parser must extract place terms from Stake.com text. EV engine uses place-specific payout per bet type. If place terms missing, prompt user before proceeding.

---

### MODERATE — Decimal vs Fractional Odds Off-by-One

`5/1 fractional = 6.00 decimal`, not 5.0. The +1 represents return of stake.

**Prevention:** Standardise to decimal at parse time. `decimal = (numerator / denominator) + 1`. Verify: 1/1 = 2.0.

---

## Kelly Criterion Pitfalls

### CRITICAL — Full Kelly on AI-Estimated Probabilities is Bankroll Ruin

**What goes wrong:** Full Kelly assumes perfect probability accuracy. Betting 2× Kelly (when true edge is half of estimated) has zero expected long-term growth. Betting more than 2× Kelly causes negative expected growth even with genuinely +EV bets.

```python
# WRONG: using raw decimal odds as b
b = decimal_odds

# CORRECT: b is net profit per unit staked
b = decimal_odds - 1
```

**Prevention:**
- Default quarter Kelly (0.25 multiplier)
- Hard cap: never bet more than 3% of bankroll regardless of Kelly output
- If raw Kelly fraction exceeds 0.30, add validation error before applying multiplier

**Phase:** Phase 2 (bet sizing). Unit-test with known inputs before deploying.

---

### CRITICAL — Applying Kelly When Edge is Unverified

**What goes wrong:** Kelly requires a calibrated edge. In early system, AI has zero track record. Applying Kelly to unverified AI probabilities is reckless sizing.

**Prevention:**
- Phase 1: use flat minimum stakes (1% of bankroll) until calibration data exists
- Switch to Kelly sizing only after 50+ resolved bets with tracked outcomes
- `calibration_confidence: LOW/MEDIUM/HIGH` flag based on resolved bet count

---

### MODERATE — Forgetting to Update Bankroll Before Each Calculation

Kelly must use current balance from SQLite every time. Never cache bankroll across Telegram sessions.

---

## AI Prediction Pitfalls

### CRITICAL — Calibration vs Accuracy: Wrong Metric Destroys ROI

**What goes wrong:** Research shows calibration-based model selection produces +34% ROI; accuracy-based selection produces -35% ROI. A 70% "accurate" model that isn't calibrated (70% confidence calls don't win 70% of the time) produces negative ROI.

**Consequence:** LLM confidence scores cannot be used directly in Kelly until calibrated against real outcomes. Treat them as relative rankings only until 50+ resolved bets.

**Phase:** Phase 3 (stats must record confidence). Phase 4 (reflection must compare predicted vs actual confidence).

---

### CRITICAL — Web Research Returns Data for Wrong Horse

Horse with same name from different race/year. AI confidently analyses incorrect data.

**Prevention:**
- Always include race date in search queries: `"Starlight" "Flemington" "March 2026"`
- At least one result must mention horse name AND a date within 7 days of the race
- If no recent result found within 3 attempts, mark research as "low confidence"

**Phase:** Phase 1 (parser must extract date/venue), Phase 2 (search query builder).

---

### MODERATE — Positive Win Streak Inflates AI Confidence via Reflection Log

After wins, reflection log fills with positive notes. AI reads its own log and becomes overconfident, leading to overbetting during lucky streaks — a feedback loop masquerading as skill.

**Prevention:**
- Reflection prompt must explicitly ask: "What did I get wrong even on winning bets?"
- Include calibration data in every reflection entry, not just win/loss
- Cap reflection context window to last 20 entries

---

### MODERATE — LLM Returns Structurally Valid but Logically Invalid Output

Horse number not in the race, confidence 1.3, bet type not offered at this bookmaker.

**Prevention:**
- Pydantic models for all AI outputs (pattern already used in `StructuredBet`)
- Domain validation: horse number must be in parsed runner list
- Validation failure → user-friendly error, not crash

---

## Text Parsing Pitfalls

### CRITICAL — Stake.com Text Paste is Unstructured and Unstable

Known failure modes:
1. Multiple odds per runner (win, place, each-way) — parser must not pick wrong one
2. Scratched runners may appear with "SCR" notation — must exclude from EV
3. Odds format ambiguity: `3/1` (fractional), `3.10` (decimal), `310` (moneyline)
4. Runner number vs barrier draw — critical for exacta/trifecta references
5. Race name truncation in copy-paste
6. Mobile vs desktop paste — extra newlines break fixed-position parsing

**Prevention:**
- Use LLM-based cleanup (CLEAN-01) as first stage — more robust than regex
- After LLM cleanup, validate with strict Pydantic model
- If validation fails, return failure reason to user with request to recheck paste
- Never use pure regex as primary parsing strategy

**Phase:** Phase 1 (critical). The entire pipeline depends on parse quality.

---

### MODERATE — LLM Cleanup Hallucinating Missing Data

If paste is ambiguous, LLM may invent plausible-sounding odds or horse names.

**Prevention:**
- Cleanup prompt: "Extract only what is present. If ambiguous or missing, return null. Do not infer or estimate."
- Show parsed result to user for confirmation before proceeding
- Sanity check: if parsed runner count is significantly less than expected, flag it

---

### MINOR — Unicode and Encoding Issues in Horse Names

Irish/French horse names with accents can garble in copy-paste.

**Prevention:** Normalise for search queries: `unicodedata.normalize('NFKD', name)`. Preserve original for display.

---

## Telegram State Pitfalls

### CRITICAL — Pipeline State Loses Context Between Messages

Bot restarts mid-pipeline, or user walks away. State is lost. User re-sends paste and creates duplicate session.

**Prevention:**
- Store pipeline state in SQLite + `RedisStorage` FSM backend from day one
- Session ID (UUID) per pipeline run
- If user sends new paste while in `AWAITING_RESULT`: prompt to abandon or enter result first

**Phase:** Phase 1. FSM design must happen before writing the first pipeline step.

---

### CRITICAL — Callback Data 64-Byte Limit (already documented in CLAUDE.md)

Race names, horse names, session references will silently truncate at 64 bytes.

**Prevention:**
- Never embed full text in callback data
- Use integer or UUID-prefix IDs referencing SQLite rows
- Short prefixes: `s:` (session), `a:` (action), `p:` (phase)

---

### MODERATE — Edit vs Delete+Send for Multi-Stage Messages

Editing a message that has a photo with a text-only message fails silently (documented in CLAUDE.md).

**Prevention:** Track `last_message_has_media` in session state. Always delete + send new when changing content type.

---

### MODERATE — User Interrupts Pipeline With Unrelated Command

User sends new paste or `/balance` while analysis is running. Second pipeline session opens and state corrupts.

**Prevention:**
- FSM state gates which handlers are active
- In `RESEARCHING`/`ANALYZING` states: only respond to `/cancel` and result input
- Never allow two active pipeline sessions simultaneously

---

## Pipeline / Agent Architecture Pitfalls

### CRITICAL — Introducing Partial Agent Behaviour Before Pipeline is Validated

The trap is adding "let the LLM decide" logic into the pipeline before it is proven, creating hybrid code harder to debug than either mode.

**Prevention:**
- Pipeline must be fully functional and tested before any agent-mode code
- Agent mode behind a feature flag or in a completely separate handler
- Shared components must be framework-agnostic functions callable from both modes

---

### CRITICAL — Non-Deterministic LLM Output Breaks Sequential Pipeline

Same race data sent to LLM twice may return different rankings/confidence. If user confirms step 3 analysis but step 5 re-runs LLM, they act on stale advice.

**Prevention:**
- Cache LLM outputs within a pipeline session to SQLite immediately after generation
- Subsequent steps read from cache, not from a new LLM call
- Only re-run LLM if user explicitly clicks "Reanalyse"

---

### MODERATE — Reflection Log Grows Without Bounds

After 200 races, old stale reflections dominate context. Token cost and context quality degrade.

**Prevention:**
- Store reflections in SQLite with timestamps, not only as a flat file
- Active context = last 20 reflections + a summarised meta-reflection generated every 20 entries
- `mindset.md` is a human-readable export only, not the primary context source

---

## Phase-Specific Warning Summary

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Parser | LLM cleanup hallucinating data | Explicit "extract only" prompt + user confirmation |
| Phase 1: Parser | Scratched runners in EV calc | Scratcher detection as mandatory parse step |
| Phase 1: FSM | Pipeline state lost on bot restart | RedisStorage FSM backend from day one |
| Phase 2: EV engine | Margin not stripped from implied prob | No-vig probability function as first-class utility |
| Phase 2: EV engine | Place bet payout miscalculation | Separate payout function per bet type with place terms |
| Phase 2: Kelly | Full Kelly on unverified AI probs | Quarter Kelly + hard 3% bankroll cap |
| Phase 2: AI | Non-deterministic outputs per step | Cache analysis output immediately after generation |
| Phase 3: Reflection | Positive feedback loop inflating confidence | Calibration-aware reflection prompt design |
| Phase 3: Reflection | Unbounded log file | SQLite-backed reflections + rolling summary |
| Phase 4: Agent mode | Premature agent code mixing with pipeline | Feature flag isolation; pipeline must be proven first |

---

## Sources

- [Mathematics of bookmaking — Wikipedia](https://en.wikipedia.org/wiki/Mathematics_of_bookmaking)
- [What is EV Betting — BetBurger](https://www.betburger.com/blog/what-is-ev-betting-expected-value)
- [Kelly Criterion — Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Why Fractional Kelly?](https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html)
- [Machine learning for sports betting: calibration — arXiv](https://arxiv.org/abs/2303.06021)
- [Agent Feedback Loops](https://tao-hpu.medium.com/agent-feedback-loops-from-ooda-to-self-reflection-92eb9dd204f6)
- [aiogram FSM docs](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html)
