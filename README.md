# LLM Prediction Capabilities Research

**Research project exploring Large Language Model capabilities in predicting probabilistic real-world events.**

## Research Goal

This project investigates whether modern LLMs (Gemini, Grok) can effectively analyze structured data and make accurate predictions for events with quantifiable outcomes. Horse racing was chosen as a test domain due to:

- **Rich structured data**: Form, odds, track conditions, jockey/trainer stats
- **Clear outcomes**: Verifiable results with exact finishing positions
- **Probabilistic nature**: Odds reflect market consensus, allowing comparison
- **High frequency**: Multiple events daily for rapid data collection

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
        │(eval)   │  │ (notify) │  │ (search) │
        └─────────┘  └──────────┘  └──────────┘
```

## Methodology

### Dual-Agent Approach

Two different LLMs analyze the same data independently:

| Agent | Model | Approach |
|-------|-------|----------|
| **Gemini** | `google/gemini-3-flash-preview` | Fast pattern recognition, statistical analysis |
| **Grok** | `x-ai/grok-4.1-fast` | Deep reasoning, causal analysis |

### Data Pipeline

1. **Monitor**: Scrapes upcoming race data from TabTouch
2. **Research**: Gathers web context on horses, jockeys, trainers via SearXNG
3. **Analysis**: Both LLMs analyze data and generate structured predictions
4. **Evaluation**: Compares predictions against actual results
5. **Statistics**: Tracks accuracy, ROI, and performance metrics

### Prediction Output

Each agent produces structured predictions with:
- Confidence score (0-1)
- Risk assessment
- Multiple bet types (Win, Place, Exacta, Trifecta, etc.)
- Reasoning explanation

## Quick Start

### Prerequisites

- Docker and Docker Compose
- [OpenRouter API Key](https://openrouter.ai/) for LLM access
- [Telegram Bot](https://core.telegram.org/bots) for notifications (optional)

### Setup

```bash
# Clone
git clone https://github.com/BorisLoveDev/racehorse-ai-agent-predictor.git
cd racehorse-ai-agent-predictor

# Configure
cp .env.example .env
nano .env  # Add your API keys

# Run
docker build -t racehorse-base:latest -f Dockerfile.base .
docker compose up -d

# Monitor
docker compose logs -f
```

## Project Structure

```
├── src/
│   ├── agents/          # LLM agents (Gemini, Grok, Research)
│   ├── config/          # Settings
│   ├── database/        # Data persistence
│   ├── models/          # Prediction schemas
│   └── web_search/      # SearXNG integration
├── services/
│   ├── monitor/         # Data collection
│   ├── orchestrator/    # Agent coordination
│   ├── results/         # Outcome evaluation
│   └── telegram/        # Notifications
└── docker-compose.yml
```

## Metrics Tracked

- **Prediction accuracy** by agent and bet type
- **ROI comparison** vs market odds
- **Confidence calibration** (does 80% confidence = 80% accuracy?)
- **Agent agreement** correlation with outcomes

## Configuration

Key settings in `.env`:

| Variable | Description |
|----------|-------------|
| `RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET` | Minimum confidence threshold |
| `RACEHORSE_WEB_SEARCH__MODE` | Research depth: off, raw, lite, deep |
| `RACEHORSE_AGENTS__PARALLEL_EXECUTION` | Run agents in parallel |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/stats [period]` | View performance metrics |
| `/history [N]` | Recent predictions and outcomes |
| `/status` | Pending predictions |

## Findings

*Research in progress. Statistics will be published as data accumulates.*

## License

MIT License

## Disclaimer

This is a research project for exploring LLM capabilities. It does not place real bets and should not be used for gambling decisions. The predictions are experimental and for educational purposes only.
