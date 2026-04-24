# Universal Betting Advisor — Design Spec

**Status:** Draft, awaiting user review
**Date:** 2026-04-24
**Scope:** Redesign the Stake horse racing bot (`services/stake/`) into a universal multi-sportsbook, multi-sport advisor with image input and a real learning loop.
**Author context:** Triggered by user asking for brainstorm — pipeline audit, logical gaps, and full implementation plan before the next betting session.

---

## 1. Executive Summary

Current bot: **Stake.com-only**, **horse-racing-only**, **text input only**, with a reflection loop that writes to disk but does not grade itself.

Target: a bot where the user can

- paste text, drop a photo/screenshot, or send a URL,
- from any sportsbook (Stake, TAB, Betfair, DraftKings, bet365, etc.),
- for any sport where probabilistic markets exist (horses, greyhounds, football, tennis, etc.),
- and get a bankroll-aware recommendation whose confidence is **calibrated by its own track record**.

The current architecture is already 70% of the way there. The LangGraph two-phase pipeline, Kelly/overround math, Redis FSM, bankroll singleton, audit log, and two-tier research agent are all sound and sport-agnostic at the *code* level. The Stake-specific parts are concentrated in four places: parser prompt, analysis prompt, research prompt, and the text-only input layer.

The real gap isn't sport-abstraction — it's **input modality** (no image/OCR) and **feedback quality** (lessons never scored, calibration never measured). Those two are the load-bearing improvements.

**Recommended approach: modular plugin architecture (Approach B)** with a phased rollout that lets the user take the bot to the track in ~2 days for quick wins, then layers in deeper changes over the following weeks.

---

## 2. Current Pipeline — Ground Truth

### 2.1 End-to-end flow (present state)

```
User (text paste / .txt file)
      │
      ▼
[aiogram Dispatcher] ── DebugMiddleware, @dp.errors()
      │
      ▼
[handlers/pipeline.py::_run_parse_pipeline]
      │
      ▼
┌─────────────── PHASE 1 (build_pipeline_graph) ───────────────┐
│ parse_node   ─► LLM extraction → ParsedRace (Gemini Flash)   │
│ calc_node    ─► Odds math, overround, enriched runners       │
└──────────────────────────────────────────────────────────────┘
      │
      ▼  (if ambiguous → awaiting_clarification)
      ▼  (if no bankroll → awaiting_bankroll_input)
      ▼  (user presses Confirm → awaiting_parse_confirm)
      ▼
┌─────────────── PHASE 2 (build_analysis_graph) ───────────────┐
│ drawdown_check  ─► circuit breaker (peak − cur)/peak ≥ 20%   │
│ pre_skip_check  ─► skip if overround_active > 15%            │
│ research        ─► orchestrator (Gemini Pro) plans;          │
│                   cheap sub-agents (Flash-Lite) execute      │
│                   via SearXNG or OpenRouter web plugin       │
│ analysis        ─► LLM assigns ai_win_prob / ai_place_prob,  │
│                   labels, skip signals (Gemini Pro)          │
│ sizing          ─► deterministic Kelly ½ → USDT,             │
│                   portfolio caps (5% total, 3 win bets)      │
│ format          ─► HTML for Telegram                         │
└──────────────────────────────────────────────────────────────┘
      │
      ▼
[awaiting_placed_tracked]  → user marks Placed / Tracked
      │
      ▼
[awaiting_result]          → user pastes result text
      │
      ▼
results/evaluator          → evaluate bets, P&L to stake_bet_outcomes
reflection/writer          → append to mindset.md
reflection/extractor       → one lesson → stake_lessons
(next race)                → top-5 rules + 3 recent failures
                             prepended to analysis prompt
```

### 2.2 Inventory (what's already there)

| Area | File | What it does |
|---|---|---|
| Entry / FSM | `services/stake/main.py`, `states.py` | aiogram Dispatcher, Redis FSM, 12 states |
| Parser (LLM) | `parser/llm_parser.py`, `prompt.py` (90 lines, Stake-specific), `models.py` | Text paste → `ParsedRace` via `.with_structured_output()` |
| Odds math | `parser/math.py` | 13 pure functions: to_decimal, implied_prob, overround, no_vig, EV, Kelly, portfolio caps |
| Pipeline | `pipeline/graph.py`, `nodes.py`, `state.py` | Two compiled LangGraphs (parse; analyze), conditional routers |
| Research | `pipeline/research/agent.py`, `tools.py`, `prompts.py` | Two-tier: orchestrator (Pro) plans + synthesizes; sub-agents (Flash-Lite) execute via SearXNG/web |
| Analysis | `analysis/models.py`, `prompts.py` | LLM assigns `ai_win_prob`, labels, skip flags → `AnalysisResult` |
| Bankroll | `bankroll/repository.py` | SQLite singleton (id=1), peak tracking, drawdown unlock |
| Results / evaluator | `results/evaluator.py`, `handlers/results.py` | Parses finish order, scores bets, writes `stake_bet_outcomes` |
| Reflection | `reflection/writer.py`, `extractor.py`, `repository.py` | LLM reflection → `mindset.md`; extracts ONE lesson → `stake_lessons` |
| Audit | `audit/logger.py` | Append-only JSONL, 10 event types, never rotates |
| Handlers | `handlers/pipeline.py` (428 LOC), `callbacks.py`, `commands.py`, `results.py` | Text-only; `.txt` document download; no `message.photo` anywhere |
| Tests | `tests/stake/` | 12 files, ~3,589 LOC, 210+ passing |

### 2.3 What's Stake-specific (the hardcoded bits)

| Location | Stake-specific detail |
|---|---|
| `parser/prompt.py:10` | *"raw Stake.com race page text"* |
| `parser/prompt.py:18` | platform default *"Stake.com"* |
| `parser/prompt.py:35` | runner number extraction rule (parenthetical) matches **only** Stake layout |
| `parser/prompt.py:62` | bankroll keywords list scoped for Stake wallet phrasing |
| `analysis/prompts.py:9` | *"senior horse racing analyst"* |
| `pipeline/research/prompts.py:12,36` | *"horse racing research strategist"*, *"Stake.com odds"* |
| `handlers/pipeline.py:390–406` | document handler accepts only `text/plain` / `.txt` |
| `handlers/pipeline.py` | no `F.photo` filter, no vision route |

Everything else — math, routing, FSM, sizing, bankroll, audit, reflection — is generic.

---

## 3. Logical Gaps & Failure Modes

### 3.1 Input layer
- **No photo / screenshot support.** The single biggest user gap. Cannot read the sportsbook layout on your phone.
- **No URL ingest.** User can't send a deep link to a race page.
- **No multi-message merge.** Pasting a long race in two messages creates two separate pipelines.
- **Documents restricted to `.txt`.** No PDF, no markdown, no image-document.

### 3.2 Platform / sport coupling
- Parser prompt is Stake-formatted; different book = silent extraction errors (wrong runner numbers, missing odds).
- Analysis & research prompts hardcode "horse racing", "jockey", "trainer" — unusable for football/tennis.
- No platform auto-detection; system trusts whatever the parser guesses.
- No per-platform quirks registry (e.g. DraftKings American odds default, Betfair exchange commission).

### 3.3 Pipeline robustness
- `PipelineState` lives in Redis with 24h TTL — a long race pause past 24h silently wipes the in-progress run.
- Active pipeline flag **blocks** new inputs instead of queueing; user must cancel and re-paste.
- Research provider is binary (`online` XOR `searxng`); no fallback on failure.
- Single LLM call per node, no retries — a transient 503 from OpenRouter skips the race.
- No timeout guard on LLM calls — a hung request stalls the FSM.
- `.with_structured_output()` failure modes return malformed objects; no schema sanity assert.

### 3.4 Decision quality
- Single model (Gemini Pro) for analysis — no ensemble / no second opinion.
- Kelly multiplier fixed at 0.5; never adapts to recent Sharpe / variance.
- No odds-staleness check between paste and actual placement.
- No cross-race day context: "jockey X 3/3 today at this track" isn't used.
- Tier-2 AI skip is binary; no "size down 50%" intermediate signal.

### 3.5 Feedback loop (the big one)
- **Lessons never graded against outcomes.** `application_count` tracks usage, not effectiveness. A lesson that actively hurts ROI is indistinguishable from one that helps.
- **No calibration tracking.** We assign `ai_win_prob = 0.30`; we never measure whether predicted-30% runners actually win ~30% of the time.
- **No Brier / log-loss score.** Classic calibration metrics are absent.
- **Reflection only on executed bets.** If we said `no_bet` and the horse won 8.0 → that miss is invisible.
- **mindset.md grows forever.** No compression; eventually poisons the prompt with stale notes.
- **No A/B lesson evaluation.** Lessons can't be retired.
- **/stats shows P&L only** — no model skill, no edge, no calibration.

### 3.6 Infra / ops
- Audit JSONL never rotates; file grows unbounded.
- No health endpoint; only Telegram `getMe` indirectly proves liveness.
- No request/trace ID correlating audit ↔ pipeline run ↔ bankroll update.
- No dead-letter for failed pipeline runs.

### 3.7 UX
- Text-heavy interface; mobile paste is clumsy at a live meeting.
- One paste = one race; at an 8-race meeting, state is rebuilt each time.
- No race countdown timer until placement cutoff.

---

## 4. Approaches Considered

### Approach A — Adapter-only (minimal)
Add a vision input adapter; abstract the three prompts into templates parametrized by platform + sport; leave the rest.

- Pros: 2–3 days to ship. Minimal refactor. Low regression risk.
- Cons: Still horse-racing-centric in the prompt library; learning loop unchanged; weak for football/tennis; no clean extensibility.

### Approach B — Modular plugin architecture *(RECOMMENDED)*
Introduce two plugin axes:

1. `providers/` — Platform plugins (Stake, DraftKings, Betfair, TAB, bet365, Generic) owning parsing prompt, field-mapping quirks, bankroll keyword list, URL patterns.
2. `sports/` — Sport plugins (horse_racing, greyhound, football, tennis, basketball, Generic) owning domain vocabulary for analysis & research prompts, participant role names, market structure.

Add input adapters (`text`, `image_vision`, `url_fetch`, `document`) that all reduce to a common `RawInput`. Add a platform/sport auto-detector (cheap LLM call on unknown input). Add proper calibration loop.

- Pros: Clean extension story ("to add bet365, write one plugin"). Testable per-plugin. Keeps the working math/FSM. Accommodates multi-sport from day one. Calibration loop is a self-contained addition.
- Cons: 2–3 weeks to fully execute. Slightly more moving parts.

### Approach C — Fully LLM-driven
Single mega-prompt that self-detects platform + sport + format. Feed text and images to the same vision LLM.

- Pros: Minimal code. No plugin boilerplate.
- Cons: Higher hallucination rate. Hard to test. Hard to debug. Cost scales with every input. No clean place to encode per-book quirks (e.g. Betfair commission).

**Decision: B.** Plugin architecture gets the generality without giving up testability, and the phased rollout (§7) lets us ship quick wins under Approach A's cost envelope while laying the bones for B.

---

## 5. Target Architecture

### 5.1 Component map

```
User input (text | photo | URL | document)
           │
           ▼
┌────────────────────────────────────────────────┐
│          Input Adapter Layer                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │  Text    │ │  Vision  │ │  URL     │        │
│  │ Adapter  │ │ Adapter  │ │ Adapter  │        │
│  │ (paste)  │ │ (Gemini  │ │ (fetch + │        │
│  │          │ │  vision) │ │  clean)  │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘        │
│       └────────────┼────────────┘              │
│                    ▼                           │
│           RawInput { content, kind,            │
│                      hints, meta }             │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────┐
│       Platform / Sport Detector                │
│   cheap LLM → (platform, sport, confidence)    │
│   falls back to "generic" plugin if low conf   │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────┐
│         Plugin Registry                        │
│   providers/<platform>.py   sports/<sport>.py  │
│   compose → (parse_prompt, analysis_prompt,    │
│             research_prompt, field_map)        │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
        EXISTING Phase 1 / Phase 2 LangGraph
        (math, research, analysis, sizing
         all unchanged under the hood)
                     │
                     ▼
┌────────────────────────────────────────────────┐
│     Calibration & Reflection Loop (new)        │
│  • predictions table (prob, size, label, ts)   │
│  • outcomes table (actual finish, ts)          │
│  • calibration_scorer (Brier, log-loss,        │
│    bucketed calibration per sport/platform)    │
│  • lesson_grader (effectiveness per lesson)    │
│  • mindset_compressor (weekly digest)          │
│  • /calibration command                        │
└────────────────────────────────────────────────┘
```

### 5.2 New directory layout

```
services/advisor/                     # renamed from stake/
├── adapters/
│   ├── text.py
│   ├── vision.py           ← NEW — Gemini vision → RawInput
│   ├── url.py              ← NEW — fetch + readability clean
│   └── document.py         ← existing .txt, plus image-as-document
├── detector/
│   └── platform_sport.py   ← NEW — cheap LLM classifier
├── providers/              ← NEW plugin axis
│   ├── base.py             ← PlatformPlugin ABC
│   ├── stake.py
│   ├── draftkings.py
│   ├── betfair.py
│   ├── tab.py
│   └── generic.py
├── sports/                 ← NEW plugin axis
│   ├── base.py             ← SportPlugin ABC
│   ├── horse_racing.py
│   ├── greyhound.py
│   ├── football.py
│   ├── tennis.py
│   └── generic.py
├── parser/                 ← existing, now thin — templates moved into plugins
│   ├── llm_parser.py
│   ├── math.py
│   └── models.py           ← RunnerInfo/ParsedRace become ParticipantInfo/ParsedEvent
├── pipeline/               ← existing (graph, nodes, research) — prompts parametrized
├── analysis/               ← existing — prompts parametrized
├── bankroll/               ← existing, unchanged
├── results/                ← existing, unchanged
├── reflection/             ← existing
├── calibration/            ← NEW
│   ├── scorer.py           ← Brier, log-loss, bucketed calibration
│   ├── lesson_grader.py    ← scores lessons vs. outcomes
│   └── mindset_compressor.py ← weekly LLM summarization
├── audit/                  ← existing + rotation
├── handlers/               ← existing + photo/URL handlers
├── settings.py             ← ADVISOR_ prefix; STAKE_ kept as alias for backwards compat
└── main.py
```

### 5.3 Plugin interfaces

```python
# providers/base.py
class PlatformPlugin(Protocol):
    name: str                           # e.g. "Stake", "DraftKings"
    url_patterns: list[re.Pattern]      # autodetect from URL
    odds_default_format: Literal["decimal","fractional","american"]
    bankroll_keywords: list[str]
    parse_quirks: str                   # markdown block injected into parse prompt
    commission_pct: float               # Betfair-type exchange commission, default 0.0

    def normalise(self, parsed: ParsedEvent) -> ParsedEvent: ...
```

```python
# sports/base.py
class SportPlugin(Protocol):
    name: str                           # "horse_racing" etc.
    participant_noun: str               # "runner" / "player" / "team"
    coach_noun: str                     # "trainer" / "coach" / None
    rider_noun: str | None              # "jockey" / "driver" / None
    bet_types: list[str]                # ["win","place"] / ["1x2","btts","over_under"]
    market_knowledge: str               # template chunk injected into analysis + research prompts

    def build_analysis_extras(self, event: ParsedEvent) -> str: ...
```

The existing `parser/prompt.py`, `analysis/prompts.py`, `pipeline/research/prompts.py` become template skeletons with `{platform_quirks}`, `{sport_vocabulary}`, `{participant_noun}` slots. Plugins supply the fill.

### 5.4 Input adapters

```python
# adapters/base.py
class RawInput(BaseModel):
    kind: Literal["text","image","url","document"]
    content: str                        # normalised text form
    images: list[bytes] = []            # preserved for vision path
    platform_hint: str | None = None
    sport_hint: str | None = None
    source_meta: dict = {}              # e.g. URL, image dimensions
```

- **text adapter**: identity, `kind="text"`.
- **vision adapter**: `message.photo[-1]` → `bot.download()` → Gemini 2.0 Flash vision with structured-output prompt → `ParsedEvent` directly (skip the text→parse stage). For low-confidence outputs, fall back to Gemini 2.5/3 Pro vision. Output normalised into `RawInput(content=<rendered text representation>, images=[raw_bytes])` so downstream nodes can still do text-based reasoning.
- **URL adapter**: `httpx` fetch with timeout + simple readability/trafilatura clean → text. Rejects unknown domains unless `--force` command.
- **document adapter**: existing `.txt`, plus `.png/.jpg` treated as image via vision adapter, plus `.pdf` (first page → image → vision).

### 5.5 Platform/sport detector

One cheap LLM call (Flash-Lite) with prompt:

```
You classify sports-betting paste/screenshots.
Given this content, return JSON: {platform, sport, confidence_platform, confidence_sport}.
Platforms: Stake, DraftKings, FanDuel, bet365, Betfair, TAB, Sportsbet, Ladbrokes, unknown.
Sports: horse_racing, greyhound_racing, football, tennis, basketball, baseball, unknown.
If confidence < 0.6 for either, set it to "generic".
```

Output wires the plugin selection. Cached per `RawInput.content_hash` to avoid re-running on retries.

### 5.6 Calibration & reflection loop (the real learning)

**New tables** (migrations on existing SQLite):

```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY,
    run_id TEXT,                  -- joins pipeline runs
    sport TEXT, platform TEXT,
    event_id TEXT,                -- canonical race/match id
    participant_id TEXT,          -- runner number / team
    ai_win_prob REAL,
    ai_place_prob REAL,
    label TEXT,
    decimal_odds REAL,
    place_odds REAL,
    implied_prob_from_odds REAL,
    no_vig_prob REAL,
    kelly_fraction REAL,
    recommended_usdt REAL,
    was_placed INTEGER,           -- user confirmed placement
    lesson_ids_applied TEXT,      -- JSON array
    created_at TIMESTAMP
);

CREATE TABLE outcomes (
    id INTEGER PRIMARY KEY,
    event_id TEXT,
    participant_id TEXT,
    finished_position INTEGER,    -- 1 = winner; NULL = scratched
    won_win INTEGER,
    won_place INTEGER,
    created_at TIMESTAMP
);

CREATE TABLE calibration_buckets (
    id INTEGER PRIMARY KEY,
    sport TEXT, platform TEXT,
    bucket_lo REAL, bucket_hi REAL,  -- e.g. 0.20 – 0.30
    predicted_count INTEGER,
    won_count INTEGER,
    period_start TIMESTAMP,
    period_end TIMESTAMP
);

-- Extend existing stake_lessons with effectiveness:
ALTER TABLE stake_lessons ADD COLUMN applications_with_win INTEGER DEFAULT 0;
ALTER TABLE stake_lessons ADD COLUMN applications_with_loss INTEGER DEFAULT 0;
ALTER TABLE stake_lessons ADD COLUMN expected_value_delta REAL;   -- avg EV vs baseline
ALTER TABLE stake_lessons ADD COLUMN last_graded_at TIMESTAMP;
ALTER TABLE stake_lessons ADD COLUMN archived INTEGER DEFAULT 0;
```

**New modules**:

- `calibration/scorer.py` — after each resolved event, writes to `calibration_buckets`, computes Brier & log-loss, updates running mean.
- `calibration/lesson_grader.py` — for each `prediction.lesson_ids_applied`, attributes the prediction's delta-EV vs. a lesson-free baseline to each lesson, updates `expected_value_delta`. Lessons with `expected_value_delta < 0` and `applications >= N` get auto-archived (not injected in future prompts).
- `calibration/mindset_compressor.py` — weekly cron (or manual `/compress_mindset`): reads `mindset.md`, asks LLM to produce a distilled 200-line "Stable Lessons" file, archives raw history.
- `/calibration` command: shows bucketed calibration ("you say 30% → actual 22%"), Brier trend, top-helpful vs top-hurtful lessons.
- **Auto reflection on misses**: when an outcome comes in, also reflect on the winner if we labelled it `no_bet` with low `ai_win_prob`. Creates "missed value" lessons distinct from "executed bet" lessons.

### 5.7 Robustness additions

The table below is the **target state**; items are sequenced across phases in §7 (most land in Phase 4 unless called out).

| Gap | Fix |
|---|---|
| Research provider single-point failure | Fallback chain in `research/tools.py`: try primary → on exception try secondary |
| LLM transient error | Tenacity retry (3 attempts, exp backoff) wrapping every `ainvoke` |
| LLM hang | `asyncio.wait_for(call, timeout=settings.llm_timeout_sec)` |
| Redis FSM TTL | Persist pipeline runs to SQLite `stake_pipeline_runs` keyed by `run_id`; FSM holds only the `run_id` |
| Active-pipeline block → queue | Optional: keep block; add `/resume <run_id>` command for interrupted runs |
| Audit growth | Rotating JSONL: 50MB max per file, 10 files kept; compression optional |
| Tracing | Issue `run_id = uuid7()` at pipeline start; thread through audit, DB, logs |
| Odds staleness | Optional: at placement time, ask user to re-paste odds block; diff vs. stored decimal_odds |

### 5.8 UX additions

- `/quick <photo>` — skip confirm step for trusted inputs.
- `/race` — list recent pipeline runs (multi-race day).
- `/calibration` — show model skill.
- `/compress_mindset` — trigger weekly digest manually.
- Race countdown ticker in status message if `time_to_start` detected.
- Quick inline buttons after photo: "parse as Stake | DraftKings | Betfair | Generic".

---

## 6. Data Model Changes

### 6.1 Renames (breaking but benign — backwards-compatible alias)

| Old | New | Rationale |
|---|---|---|
| `RunnerInfo` | `ParticipantInfo` | Applies to teams/players |
| `ParsedRace` | `ParsedEvent` | Applies to matches |
| `parsed_race` in state | `parsed_event` | |
| `jockey`, `trainer` on RunnerInfo | keep as optional; add generic `participant_role`, `coach_role`, `side_a`, `side_b` for team sports | |
| `StakeParser` | `AdvisorParser` wrapping `PlatformPlugin` | |
| `stake_*` DB tables | keep names for continuity; add new prefixed tables | No forced migration |

All renames ship as aliases first (`RunnerInfo = ParticipantInfo`) so tests keep passing while code migrates.

### 6.2 ParsedEvent shape (additive)

```python
class ParsedEvent(ParsedRace):           # inherits all fields
    event_type: Literal["race","match","bout"] = "race"
    event_id: str | None = None          # canonical key: platform+sport+track+race_number+date
    sport_key: str = "horse_racing"
    platform_key: str = "stake"
    detection_confidence: float | None = None
```

---

## 7. Phased Rollout

Four phases. Each ends with a shippable bot. User can pause at any boundary.

### Phase 1 — Quick win: vision input + de-Stake'd prompts  *(target: 1–2 days)*

Delivers: photo in → bet recommendation out, still horse-racing but platform-agnostic.

1. Add `adapters/vision.py`: Gemini 3 Flash vision wrapper that accepts `bytes` + outputs `ParsedRace`. Uses current parser prompt with a small vision preamble.
2. Add `F.photo` handler in `handlers/pipeline.py`: downloads the largest photo size, pipes into vision adapter, then into the existing Phase 1 LangGraph starting at `calc_node` (skip `parse_node` — vision output IS the parse).
3. Rewrite `parser/prompt.py` to be platform-agnostic: drop "Stake.com" specificity, replace runner-number-in-parens rule with a generic "use the saddle-cloth number if present, otherwise display order" rule. Add a `{platform_hint}` injection point (empty for now).
4. Add `adapters/document.py` branch: PNG/JPG/PDF documents route through vision adapter.
5. Tests: add vision adapter fixtures (screenshot → expected ParsedEvent); one integration test end-to-end from photo bytes to `final_bets`.
6. Add structured output schema sanity: after parse, assert each `decimal_odds` > 1.0 and `implied_prob` sum is finite. Fall back to error + user clarification on violation.
7. Coolify redeploy; smoke test with a real screenshot at the track.

**Risk**: vision model mis-reads odds. Mitigation: cheap double-check — re-convert the odds string in the raw text back to decimal via `to_decimal()` and compare to what the vision model emitted; on mismatch, prefer the math-converted value.

### Phase 2 — Plugin architecture + multi-sport *(target: 3–5 days)*

Delivers: DraftKings, Betfair, TAB paste support; football/tennis-ready.

1. Introduce `providers/base.py`, `sports/base.py` ABCs.
2. Move Stake-isms out of `parser/prompt.py` into `providers/stake.py::parse_quirks`.
3. Move horse-racing vocabulary out of `analysis/prompts.py`, `research/prompts.py` into `sports/horse_racing.py`.
4. Build `providers/generic.py` with permissive parse quirks — this is the fallback when detection is low-confidence.
5. Implement `detector/platform_sport.py` as described in §5.5.
6. Wire detector into `_run_parse_pipeline`: detect → pick plugins → inject prompts → call existing graph.
7. Add providers: DraftKings, Betfair, TAB (copy Stake, adjust odds defaults and bankroll keywords).
8. Add sports: greyhound_racing (trivial clone of horse_racing), football, tennis (new vocabulary, simpler participant model).
9. Extend `RunnerInfo` → `ParticipantInfo` with aliases.
10. Rename `services/stake/` → `services/advisor/` with symlink/alias for docker-compose compatibility; environment variable prefix `ADVISOR_*` with `STAKE_*` as fallback in `settings.py`.
11. Tests: one golden-set test per (platform × sport), fixtures from real pastes.

**Risk**: prompt drift breaks calibration baseline. Mitigation: tag every prediction with `platform_key`, `sport_key`; calibration scored per combination.

### Phase 3 — Real learning loop *(target: 5–7 days)*

Delivers: bot that knows its own skill.

1. Migrations for `predictions`, `outcomes`, `calibration_buckets`; extend `stake_lessons`.
2. Write to `predictions` on every `sizing_node` output.
3. Write to `outcomes` on every result confirmation.
4. `calibration/scorer.py` computes Brier + log-loss + bucket hit rates per `(sport, platform, 30-day window)`; populated as a post-outcome hook.
5. `calibration/lesson_grader.py`: attributes delta-EV per applied lesson; archives losers.
6. Reflection extension: if the winner was labelled `no_bet` by the analysis, fire a second reflection ("missed value"); extractor tags lessons as `missed_value` so prompts can weight them differently.
7. `/calibration` command: ASCII bucket chart + top lessons + Brier trend.
8. `/compress_mindset` command: LLM (Pro) summarises `mindset.md` into `mindset_stable.md`; raw file archived with timestamp.
9. Audit rotation: swap to `RotatingFileHandler`-equivalent for JSONL.
10. Tests: golden calibration snapshot on a synthetic bet history; lesson-grading end-to-end.

**Risk**: low-volume bet history makes calibration noisy. Mitigation: show Wilson confidence intervals alongside raw rates; hide bucket rates until N≥20.

### Phase 4 — Nice-to-haves *(target: optional, as you use the bot)*

- Request tracing (`run_id` threaded everywhere).
- LLM retry + timeout wrappers.
- Research provider fallback chain.
- Ensemble analysis (2 models vote; diverge → ask a third).
- Adaptive Kelly (scale multiplier up/down with realised Sharpe over last 30 bets).
- Odds-staleness re-paste flow.
- `/race` multi-race session list; quick inline book-choice buttons.

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Vision model mis-reads odds | Wrong bet size | Cross-check via `to_decimal()`; surface discrepancies as clarification |
| Plugin mis-routing (detector wrong) | Parser produces garbage | Always show detected (platform, sport) in confirm step; user can override |
| Legacy tests break on rename | CI red | Aliases (`StakeParser = AdvisorParser`); keep old import paths for one phase |
| Calibration noise on small N | Misleading `/calibration` output | Hide rates until N≥20 per bucket; show Wilson CI |
| Lesson grader penalises a good lesson due to variance | Retires useful rules | Require `applications >= 25` before archiving; soft-demote (lower prompt weight) before archiving |
| Image privacy | Screenshots may contain personal account balances | Redact balance before audit-logging if `detected_bankroll` present; never log raw image bytes |
| Vision call cost | Flash vision ~10× parser cost per invocation | Use Flash-Lite first; only escalate to Pro on low-confidence |
| Breaking Redis FSM format during migration | Users lose in-flight runs | Gate changes behind `ADVISOR_FSM_VERSION`; on mismatch, clear state and re-prompt |

---

## 9. Out of scope (explicit non-goals)

- Placing bets automatically. User still clicks Place on Stake.com. Advisor is advisory.
- Real-time odds scraping. We parse what the user sends us.
- Account linking / OAuth to sportsbooks.
- Mobile app. Telegram is the UI.
- Live-betting loop (in-play probability updates). Pre-race only.
- Multi-user billing / tenancy. Single-user bot.

---

## 10. Success criteria

- One-tap flow: photo → 10-second response → bet recommendation with ≥ one sensible label.
- Four platforms working end-to-end: Stake, DraftKings, Betfair, TAB.
- At least two sports: horse racing + one ball sport (football or tennis).
- `/calibration` shows bucket-by-bucket Brier for the last 30 days after ≥ 50 resolved bets.
- At least one lesson auto-archived in 30 days of use.
- Existing ~210 tests continue to pass under the rename (with compat aliases).
- No regression in the current Stake + horse-racing flow: same outputs for a golden-set of 3 historical pastes.

---

## 11. Open questions (to confirm on return)

1. **Platforms to prioritise in Phase 2?** Proposed: Stake (have), DraftKings, Betfair, TAB. Others (bet365, FanDuel, Ladbrokes) deferred. Confirm.
2. **Sports to prioritise in Phase 2?** Proposed: horse_racing (have), greyhound_racing, football (1x2, BTTS), tennis (2-way). Confirm.
3. **Rename `services/stake/` → `services/advisor/`?** Cleaner long-term but touches imports everywhere. Alternative: keep `stake/` name, it's just the directory.
4. **Vision model choice?** Gemini 3 Flash (cheap, fast, good for clear screenshots) vs. always-escalate to Pro (more reliable, 3–4× the cost). Proposal: Flash first with a confidence fallback.
5. **Calibration archiving threshold?** Proposed: archive after 25 applications with `expected_value_delta < 0`. Tune after seeing first month of data.
6. **Multi-race session UX?** Keep each paste as its own FSM run (simple), or introduce `/session` to batch multiple races at one meeting? Proposal: defer to Phase 4.
7. **Old TabTouch microservices resurrection?** `services/monitor/`, `services/results/`, `services/orchestrator/` exist in repo but are dormant. Revive as live scraping back-ends, or leave archived?
8. **Kelly multiplier adaptivity — OK to defer to Phase 4?**

---

## 12. Implementation plan gateway

Phase 1 is a natural first commit and ships visible value. Phases 2 and 3 can be sequenced independently — Phase 3 (calibration) does not require Phase 2 (plugins); we could do 3 first if the user prefers measurement over breadth. If the user approves this spec, the next step is to invoke the `writing-plans` skill to break Phase 1 into an executable plan, then iterate.

---

## 13. Framework API reference — concrete patterns

Pulled fresh from LangChain / LangGraph / OpenRouter docs (Context7, 2026-04). The spec above assumes these exact shapes; recording them here so the implementation plan can lean on them without re-researching.

### 13.1 Multimodal input to ChatOpenAI (Phase 1 vision adapter)

LangChain supports two forms for images; OpenRouter/Gemini route both through the OpenAI-compatible endpoint. We'll use the **base64 data-URL** form because it avoids hosting the image and works offline from an LLM's perspective.

```python
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
import base64

def build_vision_message(raw_image_bytes: bytes, mime: str = "image/jpeg") -> HumanMessage:
    b64 = base64.b64encode(raw_image_bytes).decode()
    return HumanMessage(content=[
        {"type": "text", "text": "Extract race data from this screenshot."},
        {"type": "image_url",
         "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
    ])

vision_llm = ChatOpenAI(
    model="google/gemini-3-flash-preview",           # cheap default
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=settings.openrouter_api_key,
    temperature=0.0,
    max_tokens=4000,
).with_structured_output(ParsedEvent)                # Pydantic schema enforced

parsed: ParsedEvent = await vision_llm.ainvoke(
    [SystemMessage(content=PARSE_SYSTEM_PROMPT), build_vision_message(img_bytes)]
)
```

Key constraints:
- **Image content only on `user` role** (OpenRouter rule).
- `detail: "high"` costs more tokens but improves odds extraction on dense screenshots.
- `.with_structured_output()` works fine with multimodal content — no separate code path needed.

Alternative modern form (LangChain's cross-provider standard):

```python
HumanMessage(content_blocks=[
    {"type": "text",  "text": "Extract race data."},
    {"type": "image", "base64": b64, "mime_type": "image/jpeg"},
])
```

### 13.2 Tool-using agent (existing pattern, confirmed)

The current research module uses `langgraph.prebuilt.create_react_agent` — this remains the right primitive for Phase 2 sub-agents.

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

@tool
def searxng_search(query: str) -> str:
    """Search self-hosted SearXNG; returns top 5 results."""
    ...

@tool
def online_model_search(query: str) -> str:
    """Query web via OpenRouter web plugin."""
    ...

sub_agent = create_react_agent(
    model=cheap_llm,
    tools=[searxng_search, online_model_search],
    prompt=SUB_AGENT_SYSTEM_PROMPT,
)
result = await sub_agent.ainvoke({"messages": [HumanMessage(content=query)]})
```

Tools decorated with `@tool` auto-expose docstring + typed signature to the LLM. No schema boilerplate.

### 13.3 Multi-agent supervisor (Phase 2/3 — platform router, analysis delegation)

For the **plugin-routing detector** and for **analysis → research delegation**, the `langgraph_supervisor` package gives us clean handoffs out of the box:

```python
from langgraph_supervisor import create_supervisor, create_handoff_tool
from langgraph.prebuilt import create_react_agent

stake_agent      = create_react_agent(model=cheap, tools=[stake_tools],      name="stake_expert",      prompt=STAKE_PROMPT)
draftkings_agent = create_react_agent(model=cheap, tools=[draftkings_tools], name="draftkings_expert", prompt=DK_PROMPT)
generic_agent    = create_react_agent(model=cheap, tools=[generic_tools],    name="generic_expert",    prompt=GENERIC_PROMPT)

router = create_supervisor(
    [stake_agent, draftkings_agent, generic_agent],
    model=cheap,
    prompt="Route to the sportsbook-specific expert. If unclear, hand off to generic_expert.",
).compile()
```

**Custom handoff tool** (when we want to pass `task_description` or `sport_hint` with the routing):

```python
from langgraph_supervisor.handoff import METADATA_KEY_HANDOFF_DESTINATION
from langgraph.types import Command

def make_handoff_tool(agent_name: str):
    @tool(f"route_to_{agent_name}", description=f"Delegate to {agent_name}.")
    def _handoff(task: Annotated[str, "what the next agent should do"],
                 state: Annotated[dict, InjectedState],
                 tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return Command(goto=agent_name, graph=Command.PARENT,
                       update={"messages": state["messages"], "task_description": task})
    _handoff.metadata = {METADATA_KEY_HANDOFF_DESTINATION: agent_name}
    return _handoff
```

Use this when we want the detector to pass typed context (e.g. *"this is an American-odds tennis match, focus on set handicaps"*) instead of raw message text.

### 13.4 Subagent-as-tool (alternative composition)

Simpler than `create_supervisor` when we don't need full handoff semantics — wrap an agent in a `@tool` and let the outer agent call it:

```python
@tool
def ask_research_agent(question: str) -> str:
    """Delegate a runner-research question to the research sub-agent."""
    resp = await research_agent.ainvoke({"messages": [HumanMessage(content=question)]})
    return resp["messages"][-1].content

outer = create_react_agent(model=pro, tools=[ask_research_agent, ...], prompt=ANALYSIS_PROMPT)
```

Good pattern for the **analysis node** in Phase 3: let it request additional research on the fly if its confidence is low on a specific runner, instead of fixed research-then-analyze sequence.

### 13.5 OpenRouter plugins we can leverage

| Plugin | Use |
|---|---|
| `web` | Current online research path; `{"id": "web", "max_results": 5}` in `extra_body.plugins` |
| `file-parser` | Parse PDFs/docs server-side; useful if user sends a form guide PDF |
| `context-compression` | Automatic context pruning — candidate for long reflection threads |
| `response-healing` | Retries malformed structured outputs — hedges against `.with_structured_output()` failures |

Wire example for current codebase:

```python
ChatOpenAI(
    model="google/gemini-3-flash-preview",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=settings.openrouter_api_key,
    extra_body={"plugins": [{"id": "web", "max_results": 5}]},  # web research
)
```

### 13.6 Structured output with vision — failure-hedging

OpenRouter + Gemini + `.with_structured_output(Pydantic)` generally works, but vision models hallucinate schemas under load. Two defences:

1. **`json_schema` strict mode** via `response_format` (natively supported):

   ```python
   extra_body={"response_format": {"type": "json_schema",
                                   "json_schema": {"name": "ParsedEvent",
                                                   "strict": True,
                                                   "schema": ParsedEvent.model_json_schema()}}}
   ```

2. **`response-healing` plugin**: auto-retry + fix malformed JSON server-side.

Use (1) as primary, (2) as belt-and-braces. Keep the existing `.with_structured_output()` as the LangChain-level wrapper (it sets `response_format` under the hood for models that support it).

### 13.7 Modern `create_agent` (to evaluate, Phase 4)

LangChain now exposes `langchain.agents.create_agent` with `ToolStrategy` for stricter structured output and richer tool composition:

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

agent = create_agent(
    model="google/gemini-3-pro-preview",
    tools=[search_tool, calc_tool],
    response_format=ToolStrategy(BetRecommendation),
)
```

This is a candidate replacement for `create_react_agent` in Phase 4 once the calibration data tells us which sub-agent behaviours need tighter output guarantees. Not adopted in Phases 1-3 to avoid churn on a still-validating codebase.

### 13.8 What this means for phases

- **Phase 1 vision adapter**: §13.1 + §13.6 (base64 data-URL + strict json_schema).
- **Phase 2 plugin routing**: can be done without a supervisor (simple if/elif on detector output calls the right prompt). Use `create_supervisor` only if routing LLM-driven logic becomes complex (e.g. ambiguous inputs where we want the LLM itself to decide which plugin to try first). Ship the dumb router first.
- **Phase 3 calibration**: mostly deterministic Python — the LLM parts (reflection writer, lesson extractor, mindset compressor) stay on simple `ChatOpenAI.ainvoke()`, no agent framework needed.
- **Phase 4**: evaluate `create_agent` / `ToolStrategy` migration once we have real calibration data showing where output reliability is the bottleneck.
