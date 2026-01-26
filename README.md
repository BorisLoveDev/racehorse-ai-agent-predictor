# Horse Racing Betting Agent System

Automated horse racing analysis system powered by dual AI agents (Gemini & Grok) that monitors races, generates predictions, and tracks performance statistics.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Race Monitor   │────▶│ Agent Orchestrator│────▶│ Results Tracker │
│  (Playwright)   │     │ (LangChain/Graph) │     │  (Evaluator)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │                        │
        └───────────────────────┼────────────────────────┘
                                ▼
                        ┌──────────────┐
                        │    Redis     │
                        │  (Pub/Sub)   │
                        └──────────────┘
                                │
                        ┌───────┴───────┐
                        ▼               ▼
                 ┌──────────┐    ┌──────────┐
                 │ SQLite   │    │ Telegram │
                 │ (races.db)│    │   Bot    │
                 └──────────┘    └──────────┘
```

## Features

- **Dual AI Analysis**: Gemini (fast pattern recognition) + Grok (deep reasoning)
- **Automated Monitoring**: Continuous race monitoring with configurable timing
- **Structured Betting**: Win, Place, Exacta, Quinella, Trifecta, First4, QPS bets
- **Web Search Integration**: Tavily-powered research on horses, jockeys, trainers
- **Performance Tracking**: Comprehensive statistics and ROI tracking
- **Telegram Notifications**: Real-time predictions and results
- **Microservices Architecture**: Docker-based services with Redis pub/sub

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API Keys:
  - [OpenRouter](https://openrouter.ai/) for LLM access
  - [Tavily](https://tavily.com/) for web search
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
nano .env  # or use your preferred editor
```

Required variables:
- `RACEHORSE_API_KEYS__OPENROUTER_API_KEY`
- `RACEHORSE_API_KEYS__TAVILY_API_KEY`
- `RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN`
- `RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID`

4. Build and run:
```bash
# Build base image
docker build -t racehorse-base:latest -f Dockerfile.base .

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

## Services

### 1. Monitor Service
- Polls TabTouch for upcoming races
- Triggers analysis N minutes before race start
- Schedules result checks

### 2. Orchestrator Service
- Runs both AI agents in parallel
- Saves predictions to database
- Publishes to Telegram

### 3. Results Service
- Waits for race completion
- Fetches results and evaluates predictions
- Updates agent statistics

### 4. Telegram Service
- Sends prediction notifications
- Sends result notifications with P/L
- Periodic statistics updates

## Configuration

All configuration via environment variables (see `.env.example`).

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `RACEHORSE_TIMING__MINUTES_BEFORE_RACE` | 3 | Trigger analysis N min before race |
| `RACEHORSE_TIMING__RESULT_WAIT_MINUTES` | 15 | Wait N min for results |
| `RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET` | 0.5 | Min confidence threshold |
| `RACEHORSE_AGENTS__PARALLEL_EXECUTION` | true | Run agents in parallel |

## AI Agents

### Gemini Agent
- **Model**: `google/gemini-2.0-flash-exp:free`
- **Strengths**: Fast pattern recognition, efficient data synthesis
- **Strategy**: Data-driven, diversified bets, balanced risk-reward

### Grok Agent
- **Model**: `x-ai/grok-2-1212`
- **Reasoning**: High effort mode
- **Strengths**: Deep causal analysis, non-obvious factors
- **Strategy**: Value identification, complex exotics, contrarian plays

## Database Schema

### Core Tables
- `agents`: AI agent configurations
- `predictions`: Structured bet predictions
- `prediction_outcomes`: Results and payouts
- `agent_statistics`: Aggregated performance metrics

### Key Metrics
- Total predictions, bets, wins, losses
- Net profit/loss, ROI percentage
- Bet type breakdown (Win, Place, Exacta, etc.)

## Development

### Local Development (without Docker)

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

3. Run database migrations:
```bash
python3 src/database/migrations.py
```

4. Start Redis locally:
```bash
redis-server
```

5. Run services individually:
```bash
# Terminal 1: Monitor
python3 services/monitor/main.py

# Terminal 2: Orchestrator
python3 services/orchestrator/main.py

# Terminal 3: Results
python3 services/results/main.py

# Terminal 4: Telegram
python3 services/telegram/main.py
```

### Project Structure

```
racehorse-agent/
├── src/
│   ├── config/
│   │   └── settings.py         # Pydantic-Settings config
│   ├── models/
│   │   └── bets.py             # Structured bet schemas
│   ├── agents/
│   │   ├── base.py             # Base agent + LangGraph workflow
│   │   ├── gemini_agent.py     # Gemini implementation
│   │   └── grok_agent.py       # Grok implementation
│   └── database/
│       ├── migrations.py       # Schema setup
│       └── repositories.py     # Data access layer
└── services/
    ├── monitor/main.py         # Race monitoring
    ├── orchestrator/main.py    # Agent execution
    ├── results/main.py         # Results evaluation
    └── telegram/main.py        # Notifications
```

## Monitoring

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f monitor
docker-compose logs -f orchestrator
docker-compose logs -f results
docker-compose logs -f telegram
```

### Check Service Health
```bash
docker-compose ps
```

### View Statistics
Statistics are automatically sent to Telegram after each race evaluation.

Or query database directly:
```bash
sqlite3 races.db "SELECT * FROM agent_statistics"
```

## Troubleshooting

### Services not starting
- Check `.env` file has all required API keys
- Verify Redis is running: `docker-compose ps redis`
- Check logs: `docker-compose logs <service-name>`

### No predictions generated
- Verify OpenRouter API key is valid
- Check Tavily API key (optional but recommended)
- Ensure confidence threshold isn't too high
- Review orchestrator logs for errors

### Results not evaluating
- Races may not have results yet (check TabTouch manually)
- Verify `RESULT_WAIT_MINUTES` setting
- Check results service logs

### Telegram not working
- Verify bot token and chat ID
- Test bot with /start command
- Check telegram service logs

## Performance Tuning

### Agent Configuration
- Adjust `TEMPERATURE` for more/less randomness
- Modify `MAX_TOKENS` for longer/shorter analysis
- Toggle `ENABLE_WEB_SEARCH` to save API costs

### Timing
- `MINUTES_BEFORE_RACE`: Earlier = more time, but odds may change
- `MONITOR_POLL_INTERVAL`: Lower = more frequent checks, higher load
- `RESULT_WAIT_MINUTES`: Adjust based on typical result posting time

### Betting
- `MIN_CONFIDENCE_TO_BET`: Higher = fewer but more confident bets
- `DEFAULT_BET_AMOUNT`: Virtual stake size for tracking
- `ENABLE_EXOTIC_BETS`: Disable for simpler strategies

## License

MIT License

## Disclaimer

This system is for educational and research purposes only. It analyzes horse racing data but does not place real bets. Always gamble responsibly and follow local laws and regulations.
