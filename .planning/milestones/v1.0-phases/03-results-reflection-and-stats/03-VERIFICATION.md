---
phase: 03-results-reflection-and-stats
verified: 2026-03-27T00:00:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
---

# Phase 03: Results Reflection and Stats Verification Report

**Phase Goal:** Results Reflection and Stats — result submission, P&L evaluation, AI reflection to mindset.md, lesson extraction and injection, /stats command, drawdown protection
**Verified:** 2026-03-27
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | User's win bet P&L is correctly computed as (amount * odds - amount) on win and (-amount) on loss | VERIFIED | evaluate_bets() confirmed via spot-check: 5 USDT @ 3.5 odds = +12.5 USDT profit; loser = -5.0 USDT |
| 2  | User's place bet P&L uses place_odds when full finishing order is known | VERIFIED | evaluator.py line 81: `profit = round(amount * place_odds - amount, 4)` when won=True |
| 3  | User sees 'not evaluable' for place bets when only the winner is known (partial result) | VERIFIED | evaluator.py lines 72–73: `if result.is_partial: evaluable = False`; spot-check confirmed |
| 4  | User can query bet outcomes filtered by placed vs tracked status | VERIFIED | BetOutcomesRepository.get_total_stats(placed_only=True) and get_period_stats(); test_stats_placed_only passes |
| 5  | User's peak balance is tracked and persists across bot restarts | VERIFIED | BankrollRepository.update_peak_if_higher() called from set_balance(); peak stored in stake_bankroll SQLite table |
| 6  | Drawdown unlock state persists across bot restarts | VERIFIED | drawdown_unlocked column on stake_bankroll; set_drawdown_unlocked() / is_drawdown_unlocked() confirmed; spot-check passed |
| 7  | Recommendation message includes odds data needed for later P&L evaluation | VERIFIED | sizing_node appends `decimal_odds` (line 687) and `place_odds` (line 719) to raw_bets dicts |
| 8  | User can submit result text in various formats and bot parses it into structured finishing order | VERIFIED | ResultParser with LLM + structured_output(ParsedResult); handles numbers, names, partial, mixed |
| 9  | Low-confidence results trigger clarification flow via FSM | VERIFIED | handle_result_text() line 96: if parsed.confidence == "low" -> set_state(awaiting_result_clarification) |
| 10 | Drawdown check fires before analysis pipeline and short-circuits to skip message | VERIFIED | graph.set_entry_point("drawdown_check"); conditional edge routes to format_recommendation on skip |
| 11 | ReflectionWriter appends a structured markdown entry to mindset.md after each result | VERIFIED | write_reflection() opens self.mindset_path with mode "a"; entry format "## Reflection — {timestamp}" |
| 12 | Reflection prose explicitly addresses 'what went wrong even in winning bets' (REFLECT-02) | VERIFIED | REFLECTION_SYSTEM_PROMPT section 3: "What went wrong (even if we won — overconfidence, missing signals, bad data)"; test_reflection_system_prompt_contains_what_went_wrong passes |
| 13 | LessonExtractor returns a LessonEntry with error_tag and rule_sentence from reflection text | VERIFIED | extractor.py: .with_structured_output(LessonEntry); test_extract_and_save_returns_lesson_entry passes |
| 14 | Lessons are saved to stake_lessons table via LessonsRepository | VERIFIED | extractor.py line 72: `repo.save_lesson(...)`; test_extract_and_save_persists_to_database passes |
| 15 | mindset.md path is derived from settings, not hardcoded | VERIFIED | writer.py line 55: `self.mindset_path = self.settings.reflection.mindset_path`; no literal "data/mindset.md" in write_reflection() |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/stake/results/models.py` | ParsedResult, BetOutcome, LessonEntry Pydantic models | VERIFIED | All 3 classes present and substantive |
| `services/stake/results/evaluator.py` | evaluate_bets() pure Python P&L math (ARCH-01) | VERIFIED | No ChatOpenAI or ainvoke; pure Python; 99 lines |
| `services/stake/results/repository.py` | BetOutcomesRepository CRUD for stake_bet_outcomes | VERIFIED | save_outcomes, get_total_stats, get_period_stats all present |
| `services/stake/results/parser.py` | ResultParser with LLM-based flexible text parsing | VERIFIED | class ResultParser with async parse() method |
| `services/stake/reflection/repository.py` | LessonsRepository CRUD for stake_lessons | VERIFIED | save_lesson, get_top_rules, get_recent_failures, increment_application_count |
| `services/stake/reflection/writer.py` | ReflectionWriter — LLM reflection to mindset.md | VERIFIED | class ReflectionWriter with write_reflection() async method |
| `services/stake/reflection/extractor.py` | LessonExtractor — LLM structured lesson extraction | VERIFIED | class LessonExtractor with extract_and_save() async method |
| `services/stake/bankroll/migrations.py` | stake_bet_outcomes, stake_lessons, peak_balance_usdt, drawdown_unlocked | VERIFIED | All 4 additions present; PRAGMA table_info guards ALTER TABLE |
| `services/stake/bankroll/repository.py` | get_peak_balance, update_peak_if_higher, is_drawdown_unlocked, set_drawdown_unlocked, check_and_auto_reset_drawdown | VERIFIED | All 5 methods present |
| `services/stake/settings.py` | ReflectionSettings, RiskSettings in StakeSettings | VERIFIED | Both classes present; reflection + risk fields on StakeSettings |
| `services/stake/states.py` | awaiting_placed_tracked, awaiting_result, awaiting_result_clarification, confirming_result | VERIFIED | All 4 new states in PipelineStates |
| `services/stake/callbacks.py` | TrackingCB, ResultCB, DrawdownCB | VERIFIED | All 3 callback classes with correct prefixes (st, sr, sd) |
| `services/stake/keyboards/stake_kb.py` | tracking_kb(), result_confirm_kb(), drawdown_unlock_kb() | VERIFIED | All 3 functions present |
| `services/stake/handlers/results.py` | Result submission handlers router | VERIFIED | router = Router(name="results"); all 5 handlers present |
| `services/stake/handlers/commands.py` | cmd_stats, cmd_unlock_drawdown | VERIFIED | Both commands present with correct Command() filters |
| `services/stake/pipeline/nodes.py` | drawdown_check_node, _build_lessons_block | VERIFIED | Both functions present; lessons injected into analysis_node |
| `services/stake/pipeline/graph.py` | drawdown_check_node as entry point | VERIFIED | set_entry_point("drawdown_check"); conditional edge to format_recommendation on skip |
| `services/stake/main.py` | results_router registered before pipeline router | VERIFIED | dp.include_router(results_router) with comment confirming order |
| `tests/stake/test_results.py` | Unit tests for evaluator, repository, drawdown | VERIFIED | 11 tests; all pass |
| `tests/stake/test_reflection.py` | Unit tests for lessons repository, writer, extractor, lessons block | VERIFIED | 22 tests; all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| services/stake/results/evaluator.py | services/stake/results/models.py | `from services.stake.results.models import BetOutcome` | VERIFIED | Line 10 |
| services/stake/results/repository.py | services/stake/bankroll/migrations.py | run_stake_migrations creates stake_bet_outcomes | VERIFIED | Line 11 import; line 27 call |
| services/stake/handlers/results.py | services/stake/results/parser.py | ResultParser.parse() in awaiting_result handler | VERIFIED | handler line 84: `parsed = await parser.parse(raw_text)` |
| services/stake/handlers/callbacks.py | services/stake/handlers/results.py | TrackingCB handled directly in results router | VERIFIED | TrackingCB.filter() in results.py; no change to callbacks.py needed (documented in plan) |
| services/stake/pipeline/nodes.py | services/stake/bankroll/repository.py | drawdown_check_node reads peak + current balance | VERIFIED | nodes.py lines 219-222: repo.get_peak_balance(), repo.get_balance() |
| services/stake/reflection/extractor.py | services/stake/results/models.py | LessonEntry structured output model | VERIFIED | .with_structured_output(LessonEntry); line 12 import |
| services/stake/reflection/extractor.py | services/stake/reflection/repository.py | LessonsRepository.save_lesson() after extraction | VERIFIED | line 72: `repo.save_lesson(...)` |
| services/stake/reflection/writer.py | services/stake/settings.py | settings.reflection.mindset_path for file path | VERIFIED | line 55: `self.mindset_path = self.settings.reflection.mindset_path` |
| services/stake/handlers/results.py | services/stake/reflection/writer.py | write_reflection() called after evaluate_bets() | VERIFIED | line 238: `reflection_text = await writer.write_reflection(...)` |
| services/stake/handlers/results.py | services/stake/reflection/extractor.py | extract_and_save() called after write_reflection() | VERIFIED | line 245: `lesson = await extractor.extract_and_save(...)` |
| services/stake/pipeline/nodes.py | services/stake/reflection/repository.py | _build_lessons_block queries top rules and failures | VERIFIED | inline import at line 301; repo.get_top_rules + get_recent_failures |
| services/stake/pipeline/nodes.py analysis_node | _build_lessons_block | lessons_block prepended to analysis prompt | VERIFIED | lines 523-525: `lessons_block = _build_lessons_block(...); prompt = lessons_block + prompt` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| results/evaluator.py | final_bets, result | Pipeline FSM state (final_bets) + user result text | Yes — compute from real bet dicts and ParsedResult | FLOWING |
| results/repository.py | stake_bet_outcomes | SQLite INSERT from save_outcomes() | Yes — real DB writes and aggregation queries | FLOWING |
| reflection/writer.py | reflection_text | LLM (ainvoke) + mindset.md file append | Yes — LLM response, file write | FLOWING |
| reflection/extractor.py | LessonEntry | LLM structured output + LessonsRepository.save_lesson() | Yes — real DB write | FLOWING |
| pipeline/nodes.py _build_lessons_block | top_rules, failure_modes | LessonsRepository DB queries | Yes — real SELECT queries from stake_lessons | FLOWING |
| handlers/commands.py cmd_stats | all_time, last_30, last_7 | BetOutcomesRepository SQL aggregation | Yes — real SQL COUNT/SUM queries | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Win bet P&L math | `evaluate_bets` with 5 USDT @ 3.5 odds on winner | profit=12.5 USDT | PASS |
| Loss bet P&L math | `evaluate_bets` with loser | profit=-5.0 USDT | PASS |
| Partial place unevaluable | `evaluate_bets` with is_partial=True, place bet | evaluable=False | PASS |
| Lessons block injection | `_build_lessons_block` with seeded lesson | "LEARNED LESSONS" block with tag + rule | PASS |
| Peak balance persistence | set_balance(100) -> set_balance(75) -> get_peak_balance() | peak=100.0, drawdown=25.0% | PASS |
| Drawdown auto-reset | unlock -> balance recovers -> check_and_auto_reset_drawdown() | is_drawdown_unlocked()=False | PASS |
| Settings values | get_stake_settings() | reflection.model, risk.drawdown_threshold_pct=20.0, mindset_path=data/mindset.md | PASS |
| Full test suite (excl. e2e) | pytest tests/stake/ --ignore test_e2e_pipeline.py | 210 passed | PASS |
| Phase 3 tests | pytest tests/stake/test_results.py test_reflection.py | 47 passed | PASS |

Note: test_e2e_pipeline.py fails with 401 authentication error (no OpenRouter API key in local env). This is expected — it is a live API integration test, not a unit test, and not a Phase 3 test.

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RESULT-01 | 03-02, 03-04 | User can submit race result as flexible text | SATISFIED | ResultParser handles numbers, names, partial, mixed; handlers/results.py handle_result_text |
| RESULT-02 | 03-02 | LLM parses result into structured finishing order; asks clarification if ambiguous | SATISFIED | ResultParser with structured_output(ParsedResult); low-confidence -> awaiting_result_clarification state |
| RESULT-03 | 03-01, 03-04 | Evaluates each bet against actual result; calculates P&L | SATISFIED | evaluate_bets() pure Python; handle_result_confirm wires to P&L display and bankroll update |
| TRACK-01 | 03-01 | placed/tracked marking; P&L stats use placed only | SATISFIED | TrackingCB with is_placed flag; BetOutcomesRepository.get_total_stats(placed_only=True) |
| REFLECT-01 | 03-03 | After evaluated result, AI writes reflection to mindset.md | SATISFIED | ReflectionWriter.write_reflection() appends "## Reflection — {timestamp}" entries |
| REFLECT-02 | 03-03 | Reflection asks "what went wrong even in winning bets" | SATISFIED | REFLECTION_SYSTEM_PROMPT section 3 explicitly states this; test_reflection_system_prompt_contains_what_went_wrong passes |
| REFLECT-03 | 03-03, 03-04 | Extracts structured lesson; top-5 rules + last-3 failures injected into next analysis | SATISFIED | LessonExtractor.extract_and_save(); _build_lessons_block() injected via `prompt = lessons_block + prompt` in analysis_node |
| STATS-01 | 03-04 | /stats command shows P&L stats — placed bets only | SATISFIED | cmd_stats in commands.py; all-time + last-30 + last-7 day views with win rate and ROI |
| RISK-01 | 03-01, 03-02 | Drawdown circuit breaker: >=20% drop from peak -> skip-only mode | SATISFIED | drawdown_check_node as pipeline entry point; /unlock_drawdown command + DrawdownCB; check_and_auto_reset_drawdown for auto re-lock |

All 9 phase requirements are SATISFIED. No orphaned requirements found — all IDs from REQUIREMENTS.md Phase 3 mapping are covered by the 4 plans.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| services/stake/reflection/repository.py | 139 | `{placeholders}` in f-string | Info | Intentional SQL IN clause construction — not a stub. Confirmed functional. |

No blockers or warnings found. All anti-pattern grep hits were false positives or intentional patterns.

---

### Human Verification Required

#### 1. Tracking Keyboard Display

**Test:** Complete a race analysis pipeline end-to-end in Telegram. After the recommendation message appears, verify the "Placed (I bet this)" and "Tracked (not bet)" buttons are shown.
**Expected:** Two inline keyboard buttons appear below recommendation text.
**Why human:** Cannot test Telegram UI rendering programmatically.

#### 2. Drawdown Skip Message User Experience

**Test:** Set balance to 100 USDT, then to 75 USDT (25% drawdown from peak). Paste new race data.
**Expected:** Bot responds with a skip message mentioning "DRAWDOWN PROTECTION", the drawdown percentage, and current vs peak balance. Message should include "Unlock Protection" button (drawdown_unlock_kb).
**Why human:** Requires live Telegram interaction to verify the button appears with the skip message. Code shows skip_reason is set but the pipeline handler's drawdown path needs UI verification.

#### 3. Reflection Quality (REFLECT-02 Compliance)

**Test:** Submit a winning bet result and observe the "Lesson learned" message in Telegram.
**Expected:** The lesson error_tag and rule_sentence are specific and calibration-focused, not generic platitudes like "do more research".
**Why human:** LLM output quality cannot be verified programmatically.

#### 4. mindset.md Creation

**Test:** After a result is submitted and evaluated with the live bot, check `data/mindset.md` on the server.
**Expected:** File exists and contains timestamped reflection entries in the `## Reflection — YYYY-MM-DD HH:MM UTC` format.
**Why human:** Requires SSH access to server and live result submission.

---

### Gaps Summary

No gaps. All 15 observable truths are verified, all 9 requirement IDs are satisfied, all key links are wired, data flows through all artifacts, and all 47 Phase 3 unit tests pass. The full non-e2e test suite (210 tests) passes. The single failing test (test_e2e_pipeline.py) requires a live OpenRouter API key and is not a Phase 3 test.

---

_Verified: 2026-03-27_
_Verifier: Claude (gsd-verifier)_
