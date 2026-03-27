# Milestones

## v1.0 MVP (Shipped: 2026-03-27)

**Phases completed:** 3 phases, 14 plans, 21 tasks

**Key accomplishments:**

- Pydantic data contracts (ParsedRace, RunnerInfo, MarketContext) and pure Python odds math (to_decimal, overround, Kelly-ready functions) with 37 passing pytest tests establishing the deterministic math layer.
- StakeSettings Pydantic config with STAKE_ env prefix + SQLite bankroll repository using singleton row pattern, with 22 passing tests
- ChatOpenAI.with_structured_output(ParsedRace) parser using OpenRouter, with comprehensive D-07 extraction prompt and 16 mocked tests covering bankroll detection and scratched runners
- aiogram bot shell with RedisStorage FSM, 7-state PipelineStates, /start /help /cancel /balance /stake commands, and inline keyboard infrastructure for parse confirmation and bankroll management
- LangGraph parse pipeline wired to Telegram FSM: text/doc input → LLM parse → ambiguity check → race summary confirm → bankroll detect/set → JSONL audit trail
- STATUS: PARTIAL — Task 1 complete, Task 2 (human-verify checkpoint) pending
- One-liner:
- Two-tier research orchestrator with searxng_search/@online_model_search tools, three-phase research_node (plan/execute/synthesize), and ARCH-01-enforcing analysis prompt
- analysis_node
- One-liner:
- One-liner:
- ReflectionWriter appends calibration-aware LLM reflections to mindset.md; LessonExtractor uses with_structured_output to extract typed LessonEntry and persist to stake_lessons via LessonsRepository
- Closed the feedback loop: reflection + lesson extraction run automatically after each result, lessons inject into the next race's analysis prompt, /stats shows all-time/30-day/7-day P&L for placed bets

---
