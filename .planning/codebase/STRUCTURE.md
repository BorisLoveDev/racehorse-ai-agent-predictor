# Codebase Structure

**Analysis Date:** 2026-03-22

## Directory Layout

```
racehorse-agent/
├── config/
│   └── searxng/
│       └── settings.yml           # SearXNG search engine config
├── services/
│   ├── monitor/
│   │   ├── Dockerfile
│   │   └── main.py                # Race monitoring service (300 lines)
│   ├── orchestrator/
│   │   ├── Dockerfile
│   │   └── main.py                # AI agent orchestration (317 lines)
│   ├── results/
│   │   ├── Dockerfile
│   │   └── main.py                # Results evaluation (527 lines)
│   └── telegram/
│       ├── Dockerfile
│       ├── main.py                # Telegram bot service (1307 lines)
│       ├── callbacks.py           # CallbackData classes (35 lines)
│       ├── keyboards.py           # Inline keyboard builders
│       └── charts.py              # P/L chart generation
├── src/
│   ├── __init__.py
│   ├── logging_config.py          # Centralized logging (105 lines)
│   ├── agents/
│   │   ├── __init__.py            # Empty
│   │   ├── base.py                # BaseRaceAgent with LangGraph workflow (517 lines)
│   │   ├── gemini_agent.py        # Gemini agent implementation (107 lines)
│   │   ├── grok_agent.py          # Grok agent implementation (116 lines)
│   │   └── research_agent.py      # Pre-fetch research agent (303 lines)
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py            # Pydantic settings with env vars (313 lines)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── migrations.py          # Schema creation and migrations (271 lines)
│   │   └── repositories.py        # Data access layer (703 lines)
│   ├── models/
│   │   ├── __init__.py
│   │   └── bets.py                # Pydantic bet models (279 lines)
│   └── web_search/
│       ├── __init__.py            # Module exports
│       ├── duckduckgo.py          # DuckDuckGo search (fallback)
│       ├── searxng.py             # SearXNG search (primary)
│       ├── site_visitor.py        # Web page content extraction
│       ├── search_cache.py        # In-memory TTL cache (137 lines)
│       └── research_modes.py      # WebResearcher with off/raw/lite/deep modes (525 lines)
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── mock_race_data.json    # Sample race data
│   │   └── mock_results.json      # Sample results
│   └── integration/
│       ├── __init__.py
│       └── test_full_pipeline.py  # Integration tests (407 lines)
├── tabtouch_parser.py             # Web scraper with Playwright (1355 lines)
├── test_agent.py                  # Manual AI agent test script (233 lines)
├── verify_fixes.sh                # Post-deploy verification (178 lines)
├── docker-compose.yml             # 6 services: redis, searxng, monitor, orchestrator, results, telegram
├── Dockerfile                     # Multi-target Docker build (70 lines)
├── Dockerfile.base                # Legacy base image build
├── entrypoint.sh                  # Runs migrations before service start
├── requirements.txt               # Python dependencies
├── version.txt                    # Semantic version string
├── races.db                       # SQLite database (runtime data)
├── .env                           # Environment variables (secrets)
├── .env.example                   # Example env template
└── CLAUDE.md                      # Project documentation for Claude Code
```

## Directory Purposes

**`services/`:**
- Purpose: Microservice entry points -- each subdirectory is a Docker container
- Contains: `main.py` files with service class + `async def main()` + `Dockerfile`
- Key pattern: Each service connects to Redis, subscribes to channels, runs event loops
- Exception: `telegram/` has extra modules (`callbacks.py`, `keyboards.py`, `charts.py`)

**`src/`:**
- Purpose: Shared library code imported by all services
- Contains: Agent logic, config, database, models, web search
- Key pattern: Services import from `src.*` using `sys.path.insert(0, parent_dir)`

**`src/agents/`:**
- Purpose: AI agent implementations using LangGraph workflows
- Contains: Base class with workflow graph, concrete Gemini/Grok agents, research agent
- Key pattern: Inheritance -- `GeminiAgent` and `GrokAgent` extend `BaseRaceAgent`

**`src/config/`:**
- Purpose: Centralized Pydantic settings with env var support
- Contains: Nested settings classes (timing, betting, agents, API keys, Redis, database, web search)
- Key pattern: Singleton via `get_settings()`, env prefix `RACEHORSE_`, nested delimiter `__`

**`src/database/`:**
- Purpose: SQLite schema and data access
- Contains: Migration scripts and repository pattern classes
- Key pattern: Repositories open/close connections per operation (no connection pooling)

**`src/models/`:**
- Purpose: Pydantic data models for AI agent outputs
- Contains: Bet type models (Win, Place, Exacta, etc.) and `StructuredBetOutput`
- Key pattern: `Optional` fields with validators, used with `llm.with_structured_output()`

**`src/web_search/`:**
- Purpose: Web research pipeline for AI agents
- Contains: Search engines (SearXNG, DuckDuckGo), site visitor, cache, research modes
- Key pattern: Four modes (off, raw, lite, deep) with increasing cost/quality

**`tests/`:**
- Purpose: Automated test suite
- Contains: Integration tests and JSON fixture files
- Key pattern: Tests skip gracefully when Redis is unavailable

**`config/searxng/`:**
- Purpose: SearXNG search engine configuration
- Contains: `settings.yml` for the SearXNG Docker container

## Key File Locations

**Entry Points:**
- `services/monitor/main.py`: Race monitoring loop (polls TabTouch every 60s)
- `services/orchestrator/main.py`: AI agent coordination (runs Gemini + Grok)
- `services/results/main.py`: Post-race evaluation (checks results, calculates P/L)
- `services/telegram/main.py`: Telegram bot with inline keyboards
- `entrypoint.sh`: Docker entrypoint (runs migrations, then starts service)

**Configuration:**
- `src/config/settings.py`: All app settings (env vars via Pydantic)
- `docker-compose.yml`: Service definitions, networking, volumes
- `Dockerfile`: Multi-target build (base -> monitor/orchestrator/results/telegram)
- `config/searxng/settings.yml`: SearXNG engine config

**Core Logic:**
- `src/agents/base.py`: LangGraph workflow (search queries -> web search -> analysis -> structured output)
- `tabtouch_parser.py`: Playwright-based scraper (get_next_races, get_race_details, get_race_results)
- `src/database/repositories.py`: All database operations (predictions, outcomes, statistics)
- `src/web_search/research_modes.py`: WebResearcher with off/raw/lite/deep modes

**Models:**
- `src/models/bets.py`: `StructuredBetOutput`, `WinBet`, `PlaceBet`, `ExactaBet`, etc.

**Telegram UI:**
- `services/telegram/callbacks.py`: `MenuCB`, `RaceCB`, `StatsCB`, `ControlCB`, `DigestCB`
- `services/telegram/keyboards.py`: Inline keyboard builders
- `services/telegram/charts.py`: Matplotlib P/L chart generation

**Testing:**
- `tests/integration/test_full_pipeline.py`: Automated integration tests
- `test_agent.py`: Manual CLI tool for testing agents on live races
- `verify_fixes.sh`: Post-deploy Docker verification

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `tabtouch_parser.py`, `research_modes.py`)
- Service entry points: always `main.py`
- Config files: descriptive names (e.g., `settings.py`, `migrations.py`)

**Directories:**
- Service directories: `snake_case` matching service name (e.g., `monitor/`, `telegram/`)
- Library packages: `snake_case` (e.g., `web_search/`, `database/`)

**Classes:**
- PascalCase (e.g., `BaseRaceAgent`, `StructuredBetOutput`, `TabTouchParser`)
- Service classes: `*Service` suffix (e.g., `RaceMonitorService`, `ResultsEvaluationService`)
- Repository classes: `*Repository` suffix (e.g., `PredictionRepository`)

**Functions:**
- snake_case (e.g., `get_settings()`, `save_prediction()`, `analyze_race()`)
- Private methods: `_prefix` (e.g., `_build_workflow()`, `_format_race_data()`)

## Where to Add New Code

**New Microservice:**
1. Create directory: `services/<name>/`
2. Add `main.py` with service class and `async def main()`
3. Add `Dockerfile` (or add target to multi-target `Dockerfile`)
4. Add service block to `docker-compose.yml`
5. Subscribe to Redis channels as needed

**New AI Agent:**
1. Create `src/agents/<name>_agent.py`
2. Extend `BaseRaceAgent` from `src/agents/base.py`
3. Override `_get_analysis_system_prompt()` and `_get_structured_output_system_prompt()`
4. Add settings class in `src/config/settings.py` (e.g., `NewAgentSettings`)
5. Register in `src/database/migrations.py` via `initialize_default_agents()`
6. Wire into `services/orchestrator/main.py`

**New Bet Type:**
1. Add Pydantic model in `src/models/bets.py`
2. Add optional field to `StructuredBetOutput`
3. Update `total_bet_amount()`, `has_any_bets()`, `get_all_bets()`
4. Add evaluation logic in `services/results/main.py` (`evaluate_prediction()`)
5. Add outcome columns in `src/database/migrations.py`
6. Update repository save/get methods in `src/database/repositories.py`

**New Database Table:**
1. Add `CREATE TABLE` to `src/database/migrations.py` in `run_migrations()`
2. Add repository class in `src/database/repositories.py`
3. Migrations run automatically via `entrypoint.sh` on container start

**New Web Search Engine:**
1. Create `src/web_search/<engine>.py` implementing search interface
2. Register in `src/web_search/__init__.py`
3. Add engine option to `WebSearchSettings` in `src/config/settings.py`
4. Wire into `src/web_search/research_modes.py`

**Shared Utilities:**
- Logging: `src/logging_config.py`
- Timezone helpers: `tabtouch_parser.py` (top-level functions)
- Configuration: `src/config/settings.py`

**Tests:**
- Unit tests: `tests/test_<module>.py`
- Integration tests: `tests/integration/test_<feature>.py`
- Fixtures: `tests/fixtures/<data>.json`

## Special Directories

**`venv/`:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No (in `.gitignore`)

**`.claude/`:**
- Purpose: Claude Code configuration (agents, commands, hooks, rules)
- Generated: Partially
- Committed: Yes

**`.auto-claude/`:**
- Purpose: Auto-generated Claude analysis docs (ideation, insights, roadmap, specs)
- Generated: Yes
- Committed: Unclear (may be in `.gitignore`)

**`.planning/`:**
- Purpose: GSD planning and codebase analysis documents
- Generated: Yes (by map-codebase)
- Committed: Pending

---

*Structure analysis: 2026-03-22*
