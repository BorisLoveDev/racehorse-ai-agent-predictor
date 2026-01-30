# Horse Racing Betting Agent System

Automated horse racing analysis system powered by dual AI agents (Gemini & Grok) that monitors races, generates predictions, and tracks performance statistics.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Monitor   │────▶│    Redis     │◀────│ Orchestrator│
│  (scraper)  │     │  (pub/sub)   │     │ (AI agents) │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌──────────┐  ┌──────────┐
        │ Results │  │ Telegram │  │ SearXNG  │
        │(checker)│  │  (notify)│  │ (search) │
        └─────────┘  └──────────┘  └──────────┘
              │            │
              └────────────┴──────▶ SQLite (races.db)
```

## Features

- **Dual AI Analysis**: Gemini (fast pattern recognition) + Grok (deep reasoning)
- **Automated Monitoring**: Continuous race monitoring with configurable timing
- **Structured Betting**: Win, Place, Exacta, Quinella, Trifecta, First4, QPS bets
- **Web Search Integration**: SearXNG-powered research on horses, jockeys, trainers
- **Performance Tracking**: Comprehensive statistics and ROI tracking
- **Telegram Notifications**: Real-time predictions and results with reply threading
- **Microservices Architecture**: Docker-based services with Redis pub/sub

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API Keys:
  - [OpenRouter](https://openrouter.ai/) for LLM access
  - [Telegram Bot](https://core.telegram.org/bots#how-do-i-create-a-bot) for notifications

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd racehorse-agent
```

2. Copy environment template:
```bash
cp .env.example .env
```

3. Edit `.env` with your API keys:
```bash
nano .env
```

Required variables:
```
RACEHORSE_API_KEYS__OPENROUTER_API_KEY=sk-or-...
RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN=123456:ABC-...
RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID=-100...
```

4. Build and run:
```bash
# Build base image
docker build -t racehorse-base:latest -f Dockerfile.base .

# Start all services
docker compose up -d

# View logs
docker compose logs -f
```

## Services

| Service | Description |
|---------|-------------|
| **monitor** | Polls TabTouch for upcoming races, triggers analysis 3-5 min before start |
| **orchestrator** | Runs Gemini & Grok agents in parallel, saves predictions |
| **results** | Waits for race completion, evaluates predictions, updates statistics |
| **telegram** | Sends notifications, handles bot commands (/stats, /history, etc.) |
| **redis** | Message broker for pub/sub communication |
| **searxng** | Self-hosted web search for horse/jockey research |

## Project Structure

```
racehorse-agent/
├── src/
│   ├── agents/              # AI agents (Gemini, Grok, Research)
│   ├── config/              # Pydantic settings
│   ├── database/            # Migrations & repositories
│   ├── models/              # Bet schemas
│   └── web_search/          # SearXNG integration
├── services/
│   ├── monitor/             # Race monitoring service
│   ├── orchestrator/        # Agent orchestration service
│   ├── results/             # Results evaluation service
│   └── telegram/            # Telegram bot service
├── config/
│   └── searxng/             # SearXNG configuration
├── tests/                   # Integration tests
├── tabtouch_parser.py       # TabTouch scraper
├── docker-compose.yml       # Service orchestration
├── Dockerfile.base          # Base image with dependencies
└── version.txt              # Current version
```

## AI Agents

### Gemini Agent
- **Model**: `google/gemini-3-flash-preview`
- **Strengths**: Fast pattern recognition, efficient data synthesis
- **Strategy**: Data-driven, diversified bets, balanced risk-reward

### Grok Agent
- **Model**: `x-ai/grok-4.1-fast`
- **Reasoning**: High effort mode
- **Strengths**: Deep causal analysis, non-obvious factors
- **Strategy**: Value identification, complex exotics, contrarian plays

## Configuration

All configuration via environment variables (see `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `RACEHORSE_TIMING__MINUTES_BEFORE_RACE` | 3 | Trigger analysis N min before race |
| `RACEHORSE_TIMING__RESULT_WAIT_MINUTES` | 15 | Wait N min after race for results |
| `RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET` | 0.5 | Min confidence threshold |
| `RACEHORSE_WEB_SEARCH__MODE` | lite | Search mode: off, raw, lite, deep |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/races` | Show upcoming races |
| `/status` | Show active bets awaiting results |
| `/history [N]` | Show last N results (default 5) |
| `/stats [period]` | Statistics with P/L chart (all/today/3d/week) |
| `/evaluate` | Manually check results for pending bets |

## Monitoring

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f orchestrator

# Check health
docker compose ps

# Restart service
docker compose restart telegram
```

## Database

SQLite database with tables:
- `agents` - AI agent configurations
- `predictions` - Structured bet predictions with odds snapshot
- `prediction_outcomes` - Results, payouts, P/L
- `agent_statistics` - Aggregated performance metrics

## Troubleshooting

### Services not starting
- Check `.env` has all required API keys
- Verify Redis is healthy: `docker compose logs redis`

### No predictions generated
- Check OpenRouter API key is valid
- Review orchestrator logs for errors
- Verify warmup messages on startup

### Results not evaluating
- Race results may not be posted yet
- Check results service logs
- Use `/evaluate` command to manually trigger

## License

MIT License

## Disclaimer

This system is for educational and research purposes only. It analyzes horse racing data but does not place real bets. Always gamble responsibly.
