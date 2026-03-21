# Technology Stack

**Analysis Date:** 2026-03-22

## Languages

**Primary:**
- Python 3.11+ - All backend services, scrapers, and AI agents
- Python 3.13 - Tested on development host

**Secondary:**
- None - monolithic Python codebase

## Runtime

**Environment:**
- Docker 27+ with Docker Compose for containerized deployment
- Python 3.11-slim base image in production containers

**Package Manager:**
- pip (Python package manager)
- Lockfile: Not detected (requirements.txt used without hash lock)

## Frameworks

**Core:**
- Playwright 1.40.0+ - Async browser automation for web scraping TabTouch
- Pydantic 2.5.0+ - Data validation and settings management
- Pydantic Settings 2.1.0+ - Environment-based configuration with nested delimiter support

**AI & LLM:**
- LangChain 0.1.0+ - Framework for LLM applications and agent workflows
- LangChain OpenAI 0.0.5+ - OpenRouter integration through ChatOpenAI
- LangChain Community 0.0.20+ - Community integrations and utilities
- Langgraph 0.0.20+ - Graph-based workflow orchestration for agents (two-step analysis + bet generation)

**Web & Async:**
- aiohttp 3.9.0+ - Async HTTP client for API calls and web scraping
- asyncio-redis 0.16.0+ - Legacy async Redis support (overlaps with redis package)

**Bot & Messaging:**
- aiogram 3.4.0+ - Telegram bot framework with callback data and inline keyboards
- Telegram Bot API - HTTP-based communication with Telegram service

**Web Parsing:**
- BeautifulSoup4 4.12.0+ - HTML parsing for web scraping
- lxml 5.0.0+ - XML/HTML parser backend for BeautifulSoup

**Data Storage:**
- SQLite3 - Built-in Python, file-based SQL database at `races.db`
- Redis 7-alpine (Docker) - In-memory pub/sub message broker (redis:// protocol)

**Utilities:**
- nest-asyncio 1.6.0+ - Allows nested event loop execution (for REPL testing)
- matplotlib 3.8.0+ - Chart generation for performance statistics

## Key Dependencies

**Critical:**
- LangChain (0.1.0+) - LLM framework binding agents, web search, and structured output together
- Playwright (1.40.0+) - Browser automation for scraping TabTouch (Chromium required)
- Pydantic (2.5.0+) - Serialization/deserialization of race data and betting recommendations
- aiogram (3.4.0+) - Telegram bot API abstraction layer
- redis (5.0.0+) - async Redis for pub/sub messaging between services

**Infrastructure:**
- aiohttp (3.9.0+) - All HTTP requests (web search, API calls)
- BeautifulSoup4 (4.12.0+) - HTML content extraction from websites

## Configuration

**Environment:**
- Pydantic Settings with `env_prefix="RACEHORSE_"` and `env_nested_delimiter="__"`
- Load from `.env` file first, environment variables override
- Hierarchical structure: `RACEHORSE_AGENTS__GEMINI__MAX_TOKENS=10000`

**Key Configuration Groups:**
- `RACEHORSE_TIMING__*` - Race monitoring intervals and result check timing
- `RACEHORSE_BETTING__*` - Bet thresholds and exotic bet enablement
- `RACEHORSE_AGENTS__*` - Model IDs, reasoning effort, temperature, token limits
- `RACEHORSE_API_KEYS__*` - OpenRouter and Telegram credentials (SecretStr type)
- `RACEHORSE_REDIS__*` - Redis host/port/password
- `RACEHORSE_DATABASE__PATH` - SQLite database file path
- `RACEHORSE_WEB_SEARCH__*` - Search engine mode (searxng/duckduckgo), URLs, cache settings
- `SOURCE_TIMEZONE` - TabTouch timezone (Australia/Perth, hardcoded in logic)
- `CLIENT_TIMEZONE` - User display timezone (Asia/Kuala_Lumpur default)

**Build:**
- `Dockerfile` - Multi-target: base, monitor, orchestrator, results, telegram
- `Dockerfile.base` - Reusable base image with Playwright browsers pre-installed
- `docker-compose.yml` - 6 services: redis, searxng, monitor, orchestrator, results, telegram
- `.dockerignore` - Standard exclusions
- `entrypoint.sh` - Migration runner before service startup

## Platform Requirements

**Development:**
- macOS host with Miniforge/conda (per CLAUDE.md)
- Python 3.13.12 tested
- Virtual environment: `source venv/bin/activate`
- Playwright browsers auto-installed on first use or in Docker build

**Production:**
- Coolify self-hosted PaaS on Meridian server (2 vCPU, 4GB RAM, Ubuntu 24.04)
- Docker Compose orchestration via Coolify buildpack (`dockercompose`)
- Health checks on Redis and SearXNG (HTTP GET /healthz)
- Volumes: `redis_data`, `db_data`, `race_data`, `searxng_data`
- Network: bridge mode (`racehorse-network`)

**Deployment Process:**
- Coolify reads `docker-compose.yml` from git (`BorisLoveDev/racehorse-ai-agent-predictor` main branch)
- Build via Coolify API: `mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")`
- SSH fallback: `ssh meridian "cd /data/coolify && docker compose up -d"`

**Build Constraints:**
- Docker image build requires 8-10 minutes (Playwright Chromium binary inclusion)
- 4GB RAM server: `--no-cache` builds can trigger OOM-kill (use `docker build` with cache if possible)
- Base image reuse: Dockerfile.base cached once, each service target adds only CMD

---

*Stack analysis: 2026-03-22*
