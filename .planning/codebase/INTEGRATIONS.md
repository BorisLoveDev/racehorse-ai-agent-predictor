# External Integrations

**Analysis Date:** 2026-03-22

## APIs & External Services

**AI Models (via OpenRouter):**
- **Gemini 3 Flash** - Deep race analysis
  - SDK/Client: `langchain_openai.ChatOpenAI` via OpenRouter gateway
  - Auth: `RACEHORSE_API_KEYS__OPENROUTER_API_KEY` (SecretStr)
  - Configuration: `src/config/settings.py` → `GeminiAgentSettings`
  - Details: 1M context tokens, 10K max output, high reasoning (80%), temperature 0.7
  - Located in: `src/agents/gemini_agent.py`

- **Grok 4.1 Fast** - Creative betting insight
  - SDK/Client: `langchain_openai.ChatOpenAI` via OpenRouter gateway
  - Auth: Same API key as Gemini (`RACEHORSE_API_KEYS__OPENROUTER_API_KEY`)
  - Configuration: `src/config/settings.py` → `GrokAgentSettings`
  - Details: 2M context tokens, 12K max output, high reasoning (80%), temperature 0.7
  - Located in: `src/agents/grok_agent.py`

**Research Data Gathering:**
- **SearXNG** - Primary web search engine (self-hosted)
  - Docker service: `searxng` at `http://searxng:8080` (internal), exposed on port 8888 (external)
  - SDK/Client: `src/web_search/searxng.py` → `SearXNGSearch` class using `aiohttp`
  - Configuration: `RACEHORSE_WEB_SEARCH__SEARXNG_URL` (default `http://searxng:8080`)
  - Modes: raw (JSON API, no LLM), lite (visit sites + LLM extract), deep (full multi-agent research)
  - Health check: `GET http://searxng:8080/healthz`

- **DuckDuckGo** - Fallback search engine
  - Endpoint: `https://html.duckduckgo.com/html/` (no API key required)
  - SDK/Client: `src/web_search/duckduckgo.py` → `DuckDuckGoSearch` class using `aiohttp`
  - Method: HTML scraping with BeautifulSoup4
  - No auth required

**TabTouch Racing Data:**
- **TabTouch (tabtouch.mobi)** - Primary race data source
  - Website: Australian horse racing odds and results
  - SDK/Client: `tabtouch_parser.py` → `TabTouchParser` class using Playwright
  - Methods: `get_next_races()`, `get_race_details()`, `get_race_results()`
  - Timezone: Source timezone `Australia/Perth` (hardcoded)
  - Browser: Playwright Chromium (async automation)
  - Rate: 60-second polling interval for race monitoring

## Data Storage

**Databases:**
- **SQLite (races.db)**
  - Connection: File-based at `RACEHORSE_DATABASE__PATH` (default `races.db`)
  - Client: Built-in `sqlite3` module + custom repositories
  - Tables: `agents`, `predictions`, `prediction_outcomes`, `agent_statistics`
  - Columns: `odds_snapshot_json`, `actual_dividends_json`, `telegram_message_id`, etc.
  - Data access: `src/database/repositories.py` → `PredictionRepository`, `OutcomeRepository`, `StatisticsRepository`
  - Migrations: `src/database/migrations.py` → `run_migrations()` (called on service startup)

**Caching:**
- **Redis (in-memory)**
  - Provider: Redis 7-alpine (Docker service)
  - Connection: TCP `RACEHORSE_REDIS__HOST` (default `redis:6379`)
  - Client: `redis>=5.0.0` async (`redis.asyncio` / `aioredis`)
  - Usage: Pub/sub only (no data persistence needed)
  - Data: Volatile (lost on restart)

**File Storage:**
- **Local volumes (Docker):**
  - `db_data:/app/data` - SQLite database file (`races.db`)
  - `race_data:/app/race_data` - Intermediate race data/JSON (scraper cache)
  - `redis_data:/data` - Redis append-only file (AOF) backup
  - `searxng_data:/var/cache/searxng` - Search result caching
- **External access:** None (self-contained)

## Authentication & Identity

**API Key Management:**
- **OpenRouter Gateway** - Single API key for both Gemini and Grok
  - Env var: `RACEHORSE_API_KEYS__OPENROUTER_API_KEY`
  - Type: `SecretStr` (Pydantic field, value masked in logs)
  - Implementation: Passed to `langchain_openai.ChatOpenAI` as `api_key` parameter
  - LLM requests: Made through OpenRouter proxy to Google and xAI backends

**Telegram Bot Authentication:**
- **Telegram Bot Token**
  - Env var: `RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN` (SecretStr)
  - Service: `services/telegram/main.py`
  - Framework: `aiogram` (Bot class auto-retrieves user info from token)

- **Chat ID for Notifications**
  - Env var: `RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID` (plain string)
  - Purpose: Target chat for all bot messages (notifications + interactive keyboard replies)
  - Implementation: Passed to bot methods like `bot.send_message(chat_id, ...)`

**No Custom Auth:**
- TabTouch: No login required (public data)
- SearXNG: Self-hosted, no auth
- Redis: No password by default (private Docker network only)
- SQLite: File-based, no auth

## Monitoring & Observability

**Error Tracking:**
- None detected - Uses standard Python logging

**Logs:**
- **Approach:** Centralized Python logging via `src/logging_config.py`
- **Output:** Console (Docker logs aggregation)
- **Format:** Structured JSON or key=value pairs
- **Level:** `RACEHORSE_LOG_LEVEL` (default `INFO`)
- **Loggers:** Per-service (monitor, orchestrator, results, telegram) + per-module

**Health Checks:**
- Redis: `redis-cli ping` (Docker health check, 10s interval)
- SearXNG: `wget http://localhost:8080/healthz` (30s interval)

## CI/CD & Deployment

**Hosting:**
- **Production:** Coolify self-hosted PaaS on Meridian (46.30.43.46, Ubuntu 24.04)
- **Deployment:** Git-based (Coolify polls `BorisLoveDev/racehorse-ai-agent-predictor` main branch)

**CI Pipeline:**
- None detected - Direct git push triggers Coolify rebuild

**Deployment Methods:**
- **Preferred:** Coolify API → `mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")`
- **Fallback:** SSH to Meridian → `docker compose up -d`

**Build Pipeline:**
- Dockerfile.base (shared): Python 3.11-slim + system deps + Playwright Chromium
- Dockerfile (multi-target): Copies base, adds service CMD per target
- Build time: 8-10 minutes (Playwright binary install)
- OOM risk: 4GB RAM server + `--no-cache` can crash

## Environment Configuration

**Required env vars:**
- `RACEHORSE_API_KEYS__OPENROUTER_API_KEY` - LLM access (required for agents)
- `RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN` - Bot notifications (required)
- `RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID` - Target chat (required)
- `SOURCE_TIMEZONE` - TabTouch timezone (default: Australia/Perth)
- `CLIENT_TIMEZONE` - Display timezone (default: Asia/Kuala_Lumpur)

**Optional env vars:**
- `RACEHORSE_REDIS__HOST` - Redis host (default: `redis` for Docker, `localhost` for dev)
- `RACEHORSE_REDIS__PORT` - Redis port (default: 6379)
- `RACEHORSE_DATABASE__PATH` - SQLite path (default: `races.db`)
- `RACEHORSE_WEB_SEARCH__MODE` - Search mode: `off`, `raw`, `lite`, `deep` (default: `lite`)
- `RACEHORSE_WEB_SEARCH__ENABLED` - Enable web search (default: true)
- `RACEHORSE_AGENTS__GEMINI__MAX_TOKENS` - Gemini output limit (default: 10000)
- `RACEHORSE_AGENTS__GROK__MAX_TOKENS` - Grok output limit (default: 12000)
- `RACEHORSE_TIMING__MINUTES_BEFORE_RACE` - Trigger analysis window (default: 3)
- `RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET` - Confidence threshold (default: 0.5)

**Secrets location:**
- Development: `.env` file (ignored in `.gitignore`)
- Production: Coolify UI environment variable management (49 vars configured)
- Never committed to git

## Webhooks & Callbacks

**Incoming:**
- **Telegram Callbacks** - User interaction with inline keyboards
  - Endpoint: Handled by aiogram Bot dispatcher (polling mode)
  - Types: MenuCB, RaceCB, StatsCB, ControlCB, DigestCB (callback data classes)
  - Max size: 64 bytes per Telegram API limit (enforced in `services/telegram/callbacks.py`)
  - Examples: `menu_action`, `race_select`, `stats_period`, `bot_control`

**Outgoing:**
- **Redis Pub/Sub Channels:**
  - `race:ready_for_analysis` - Monitor → Orchestrator (race URL + data)
  - `race:schedule_result_check` - Monitor → Results (race URL + check time)
  - `predictions:new` - Orchestrator → Telegram (predictions for display)
  - `results:evaluated` - Results → Telegram (outcomes + statistics)
  - `races:digest` - Monitor → Telegram (manual mode, 10-min throttle via Redis TTL)

- **No External Webhooks** - System is pull-based (polling TabTouch every 60s) + async message passing

## External API Rate Limits

**OpenRouter (Gemini + Grok):**
- No hardcoded rate limiting detected
- Relies on API key rate limits (provider-side)
- Both agents run in parallel via `asyncio.gather()` for speed

**DuckDuckGo Search:**
- No API key required
- HTML scraping fallback (less reliable than SearXNG)
- aiohttp requests: 30-second timeout

**TabTouch Scraping:**
- Poll interval: 60 seconds (monitor_poll_interval)
- Single concurrent browser instance (Playwright)
- No explicit rate limiting beyond poll interval

---

*Integration audit: 2026-03-22*
