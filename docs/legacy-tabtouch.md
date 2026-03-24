# Legacy: TabTouch System

Inactive in production. Code remains in repo for reference. Old deployment removed from Coolify.

## Services (not deployed)

- **Monitor** (`services/monitor/main.py`) — polls TabTouch every 60s, triggers analysis
- **Orchestrator** (`services/orchestrator/main.py`) — runs Gemini + Grok agents
- **Results** (`services/results/main.py`) — evaluates predictions
- **Telegram** (`services/telegram/main.py`) — notifications + interactive keyboards

## Key Components

- `tabtouch_parser.py` — Playwright scraper (SOURCE_TIMEZONE: Australia/Perth)
- `src/agents/` — GeminiAgent, GrokAgent, ResearchAgent
- `src/database/` — predictions, outcomes, agent_statistics tables
- `src/web_search/` — SearXNG/DuckDuckGo, modes: raw/lite/deep
- `src/config/settings.py` — `RACEHORSE_` env prefix, `__` nested delimiter

## Running Locally

```bash
docker build -f Dockerfile.base -t racehorse-base:latest .
docker compose --profile tabtouch up -d
```

## Redis Channels

| Channel | Publisher | Subscriber |
|---------|-----------|------------|
| `race:ready_for_analysis` | Monitor | Orchestrator |
| `race:schedule_result_check` | Monitor | Results |
| `predictions:new` | Orchestrator | Telegram |
| `results:evaluated` | Results | Telegram |
