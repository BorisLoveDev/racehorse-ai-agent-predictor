# Codebase Concerns

**Analysis Date:** 2026-03-22

## Tech Debt

**Hardcoded race_id = 0:**
- Issue: `services/orchestrator/main.py` line 253 sets `race_id = 0` for all predictions with comment "we'll improve this later"
- Files: `services/orchestrator/main.py`
- Impact: Cannot correlate multiple predictions to the same race via a proper race entity. Statistics and querying by race are unreliable.
- Fix approach: Create a `races` table, generate race_id from race_url hash or auto-increment, look up or insert before saving predictions.

**sys.path manipulation in every service:**
- Issue: Each service uses `sys.path.insert(0, str(Path(__file__).parent.parent.parent))` to import `src.*` modules
- Files: `services/monitor/main.py`, `services/orchestrator/main.py`, `services/results/main.py`, `services/telegram/main.py`
- Impact: Fragile import resolution, IDE confusion, potential import order bugs
- Fix approach: Use proper Python packaging with `pyproject.toml` and install as editable package (`pip install -e .`), or set `PYTHONPATH=/app` consistently (already done in Dockerfile but not locally).

**Inline schema in test fixtures vs migrations:**
- Issue: `tests/integration/test_full_pipeline.py` defines its own database schema inline (lines 151-194), separate from `src/database/migrations.py`
- Files: `tests/integration/test_full_pipeline.py`, `src/database/migrations.py`
- Impact: Test schema can drift from production schema. Test database uses different column names (e.g., `name` vs `agent_name`), meaning tests pass against wrong schema.
- Fix approach: Import and call `run_migrations()` in test fixtures instead of inline schema.

**No connection pooling for SQLite:**
- Issue: Every repository method opens a new `sqlite3.connect()` and closes it in `finally`. No connection reuse.
- Files: `src/database/repositories.py`
- Impact: Performance overhead from repeated connection setup. Risk of SQLite "database is locked" errors under concurrent writes from multiple services sharing the same db volume.
- Fix approach: Use a connection pool or WAL mode (`PRAGMA journal_mode=WAL`) for concurrent access. Consider switching to a proper database for multi-service writes.

**Duplicate LLM initialization in agent constructors:**
- Issue: `GeminiAgent.__init__()` and `GrokAgent.__init__()` call `super().__init__()` which creates an LLM, then immediately override `self.llm` with a new one (to add `model_kwargs` for reasoning)
- Files: `src/agents/gemini_agent.py` (lines 32-54), `src/agents/grok_agent.py` (lines 34-56)
- Impact: Wasteful -- creates and discards an LLM client on every initialization. Minor but indicates design flaw.
- Fix approach: Add `model_kwargs` parameter to `BaseRaceAgent.__init__()` and pass reasoning config through.

**`datetime.utcnow()` usage (deprecated):**
- Issue: Several files use `datetime.utcnow()` which returns naive UTC datetime (deprecated in Python 3.12+)
- Files: `services/orchestrator/main.py` (line 289), `services/monitor/main.py` (line 112, 253), `src/database/repositories.py` (line 259, 501, 628)
- Impact: Mixing naive and aware datetimes can cause comparison bugs. Results service already has `ensure_utc_aware()` workaround.
- Fix approach: Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`. Results service already does this correctly.

## Known Bugs

**Test schema mismatch:**
- Symptoms: Integration test database schema uses `name` column, production uses `agent_name`
- Files: `tests/integration/test_full_pipeline.py` (line 159), `src/database/migrations.py` (line 58)
- Trigger: Running tests against production migration code would fail
- Workaround: Tests use inline schema, not production migrations

## Security Considerations

**SQLite shared volume across containers:**
- Risk: All 4 Python services write to the same `db_data` Docker volume containing `races.db`. SQLite is not designed for concurrent multi-process writes.
- Files: `docker-compose.yml` (volumes section), `src/database/repositories.py`
- Current mitigation: None. SQLite default journal mode (DELETE) does not handle concurrent writers well.
- Recommendations: Enable WAL mode (`PRAGMA journal_mode=WAL`), or migrate to PostgreSQL for multi-service access. Add retry logic with exponential backoff on "database is locked" errors.

**No authentication on Telegram bot commands:**
- Risk: Any user who discovers the bot can send commands to it
- Files: `services/telegram/main.py`
- Current mitigation: Bot only responds in configured `TELEGRAM_CHAT_ID`
- Recommendations: Add explicit user/chat ID validation middleware to reject messages from unauthorized sources.

**API key in settings singleton:**
- Risk: `get_settings()` singleton holds `SecretStr` API keys in memory for process lifetime
- Files: `src/config/settings.py`
- Current mitigation: Uses `SecretStr` (Pydantic) which prevents accidental logging
- Recommendations: Acceptable for current architecture. Do not log `settings` object directly.

## Performance Bottlenecks

**TabTouchParser (Playwright browser):**
- Problem: Each scraping operation launches Playwright browser automation. Three services (monitor, results, telegram) each maintain their own browser instance.
- Files: `tabtouch_parser.py`, `services/monitor/main.py`, `services/results/main.py`
- Cause: Playwright Chromium is memory-hungry (~200-400MB per instance). Three instances on a 4GB RAM server.
- Improvement path: Share a single scraping service that other services call via Redis RPC, or use lightweight HTTP requests instead of full browser automation where possible.

**Synchronous database operations in async services:**
- Problem: All `repositories.py` methods are synchronous (`sqlite3.connect()`), called from async service code
- Files: `src/database/repositories.py`, `services/orchestrator/main.py`, `services/results/main.py`
- Cause: SQLite's Python driver is synchronous. Blocking calls in async event loop.
- Improvement path: Use `aiosqlite` for async SQLite access, or wrap sync calls in `asyncio.to_thread()`.

**Large Telegram service file:**
- Problem: `services/telegram/main.py` is 1307 lines -- the largest Python file in the project
- Files: `services/telegram/main.py`
- Cause: All bot handlers, message formatting, Redis listener, and service logic in one file
- Improvement path: Extract message formatters, handler registration, and Redis listener into separate modules.

## Fragile Areas

**TabTouch scraper:**
- Files: `tabtouch_parser.py` (1355 lines)
- Why fragile: Web scraping depends on TabTouch HTML structure. Any site redesign breaks parsing. Parser uses CSS selectors and regex patterns that are tightly coupled to page structure.
- Safe modification: Test against live site before/after changes. Use `show_next_races.py` and `show_race_details.py` for quick validation.
- Test coverage: No automated tests. Only manual verification scripts.

**Dividend parsing:**
- Files: `tabtouch_parser.py` (`_parse_dividends()`), `services/results/main.py` (`evaluate_prediction()`, `_build_actual_dividends()`)
- Why fragile: Dividends have different types per bet (float for win, list for place, dict with "amount" for exotics). Multiple `isinstance()` checks throughout.
- Safe modification: Always test with real race results. Check CLAUDE.md "Dividend Data Structures" section.
- Test coverage: No automated tests for dividend parsing logic.

**Timezone handling:**
- Files: `tabtouch_parser.py` (timezone helpers), `services/results/main.py` (`ensure_utc_aware()`), `services/monitor/main.py`
- Why fragile: Mix of naive and aware datetimes across services. `tabtouch_parser.py` uses `ZoneInfo`, results service uses `timezone.utc`, monitor uses `datetime.utcnow()`.
- Safe modification: Always use timezone-aware datetimes. Convert to UTC for storage, Perth timezone for scraping.
- Test coverage: One test (`TestTimezoneHandling`) covering only `to_utc_naive()`.

**Redis pub/sub message contracts:**
- Files: All service `main.py` files
- Why fragile: No schema validation on Redis messages. Services publish/subscribe using `json.dumps()`/`json.loads()` with implicit field contracts. A typo in a field name causes silent failure.
- Safe modification: Verify both publisher and subscriber agree on field names. Check CLAUDE.md "Redis Pub/Sub Channels" table.
- Test coverage: One integration test (`test_pubsub_roundtrip`) verifies basic connectivity only.

## Scaling Limits

**4GB RAM production server:**
- Current capacity: 6 Docker containers (redis, searxng, 4 Python services with Playwright)
- Limit: OOM kills during Docker builds with `--no-cache`. Runtime memory ~2.5-3GB typical.
- Scaling path: Upgrade to 8GB RAM, or move Playwright-dependent services to separate host.

**SQLite for multi-service writes:**
- Current capacity: Works for low-volume writes (a few predictions per hour)
- Limit: SQLite write locks will cause "database is locked" errors under high throughput
- Scaling path: Migrate to PostgreSQL. Already use Docker volumes, so swap is straightforward.

**Single-server deployment:**
- Current capacity: One Coolify instance on Meridian (46.30.43.46)
- Limit: Cannot horizontally scale individual services
- Scaling path: Split into separate containers deployable on multiple hosts, use PostgreSQL + Redis as shared state.

## Dependencies at Risk

**Playwright (browser automation):**
- Risk: Heavy dependency (~400MB) for web scraping. Chromium updates can break selectors.
- Impact: Monitor, results, and telegram services all depend on it for TabTouch access.
- Migration plan: For read-only pages, consider switching to `httpx` + `BeautifulSoup`. Playwright only needed if TabTouch uses heavy JavaScript rendering.

**OpenRouter API:**
- Risk: Single provider for all LLM access. Rate limits, downtime, or pricing changes affect both agents.
- Impact: Orchestrator cannot generate predictions if OpenRouter is down.
- Migration plan: Add direct API support for Gemini (Google) and Grok (xAI) as fallbacks.

**nest_asyncio:**
- Risk: Used in `src/agents/base.py` (line 199) to patch event loop for sync-in-async. Known to cause subtle bugs with some libraries.
- Impact: Could cause deadlocks or unexpected behavior in edge cases.
- Migration plan: Refactor LangGraph workflow to be fully async, eliminating need for `nest_asyncio`.

## Missing Critical Features

**No CI/CD pipeline:**
- Problem: No GitHub Actions, no automated testing on push
- Blocks: Cannot catch regressions automatically. Manual verification only.

**No automated test for AI agent output:**
- Problem: No tests validate that agents return valid `StructuredBetOutput` given sample data
- Blocks: Cannot detect prompt regression or structured output schema breaks without manual testing.

**No race deduplication at database level:**
- Problem: `race_id = 0` for all predictions. No `races` table.
- Blocks: Cannot query "show me all predictions for this race" reliably. Statistics aggregation may double-count.

**No graceful shutdown handling:**
- Problem: Services catch `KeyboardInterrupt` but Docker sends `SIGTERM`. No signal handler registered.
- Blocks: Ungraceful container restarts may leave Playwright browsers orphaned or SQLite in dirty state.

## Test Coverage Gaps

**TabTouch parser (0% automated coverage):**
- What's not tested: `get_next_races()`, `get_race_details()`, `get_race_results()`, `_parse_dividends()`, timezone helpers
- Files: `tabtouch_parser.py` (1355 lines)
- Risk: Site structure changes silently break scraping with no automated detection
- Priority: High -- this is the data source for the entire system

**AI agent workflow (0% automated coverage):**
- What's not tested: `BaseRaceAgent._build_workflow()`, `_deep_analysis()`, `_structured_output()`, `analyze_race()`
- Files: `src/agents/base.py`, `src/agents/gemini_agent.py`, `src/agents/grok_agent.py`
- Risk: Prompt changes or model updates can silently break structured output generation
- Priority: High -- core business logic

**Results evaluation (0% automated coverage):**
- What's not tested: `evaluate_prediction()` with all 7 bet types, dividend parsing edge cases, payout calculation
- Files: `services/results/main.py`
- Risk: Incorrect P/L calculations, missed winning bets, wrong payout amounts
- Priority: High -- directly affects financial tracking accuracy

**Telegram message formatting (0% automated coverage):**
- What's not tested: Message rendering, keyboard interactions, callback handling
- Files: `services/telegram/main.py` (1307 lines), `services/telegram/callbacks.py`, `services/telegram/keyboards.py`
- Risk: UI bugs, malformed messages, keyboard data exceeding 64-byte limit
- Priority: Medium -- user-facing but not data-critical

**Repository methods (partial coverage):**
- What's not tested: `save_prediction()`, `save_outcome()`, `_update_agent_statistics()`, `get_statistics_for_period()`, `get_pl_chart_data()`
- Files: `src/database/repositories.py`
- Risk: SQL errors, incorrect aggregations, data corruption
- Priority: Medium -- some basic insert/select tests exist but complex queries untested

---

*Concerns audit: 2026-03-22*
