# CLAUDE.md

## Active Project: Stake Horse Racing Advisor Bot

Telegram bot for horse racing betting on Stake.com. User pastes raw race text -> LLM parses -> odds math -> bankroll-aware recommendations.

**Stack:** Python 3.11, aiogram 3, LangChain/LangGraph, OpenRouter, Redis (FSM), SQLite, Docker
**Entry point:** `services/stake/main.py`

## Architecture

```
User (Telegram) -> Stake Bot -> LLM Parser -> Odds Math -> Bankroll -> Recommendations
                       |              |
                   Redis FSM     OpenRouter API
                       |         (gemini-2.0-flash)
                   SQLite DB
```

3 Docker containers: `redis`, `searxng`, `stake`

## Stake Bot Structure

- `services/stake/main.py` — bot entry, Dispatcher + RedisStorage
- `services/stake/settings.py` — `StakeSettings`, env prefix `STAKE_`, delimiter `__`
- `services/stake/parser/` — LLM parser, models (ParsedRace, RunnerInfo), odds math
- `services/stake/handlers/` — commands, pipeline, callbacks
- `services/stake/pipeline/` — LangGraph state graph (parse -> calc -> format)
- `services/stake/bankroll/` — SQLite repo, singleton row pattern
- `services/stake/audit/` — JSONL append-only logger
- `tests/stake/` — 84 tests

## Deployment

See `docs/deployment.md` for full guide. Quick reference:

```bash
git push origin main
# Then: mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")
```

**Pre-deploy:** run `pytest tests/stake/ -x -q`, check no competing bot containers.

## Configuration

Stake bot: `STAKE_` prefix. Key env vars in Coolify UI:
- `STAKE_PARSER__MODEL` — LLM for parsing (default: google/gemini-2.0-flash-001)
- `STAKE_PARSER__TEMPERATURE` — 0.0
- `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY` — must be set (not empty)

Legacy TabTouch: `RACEHORSE_` prefix. See `docs/legacy-tabtouch.md`.

## AI Models (via OpenRouter)

| Component | Model | Cost | Env Var |
|-----------|-------|------|---------|
| Parser (extraction) | gemini-3.1-flash-lite-preview | Cheap | `STAKE_PARSER__MODEL` |
| Research (data gathering) | gemini-3.1-flash-lite-preview | Cheap | `STAKE_RESEARCH__MODEL` |
| Analysis (aggregation) | gemini-3.1-pro-preview | Expensive | `STAKE_ANALYSIS__MODEL` |

Config: `services/stake/settings.py` — ParserSettings, ResearchSettings, AnalysisSettings.
Flash-lite: high-volume, low cost. Pro: use sparingly for final aggregation.

## Development

```bash
source venv/bin/activate
PYTHONPATH=. pytest tests/stake/ -x -v    # run tests
python -c "import ast; ast.parse(open('file.py').read())"  # syntax check
```

## Common Pitfalls

- **Telegram 64-byte callback limit** — use short prefixes (`sc:`, `sb:`, `sm:`)
- **Competing bot instances** — two polling clients with same token = random message loss. Always check `docker ps | grep bot` before deploy
- **Coolify env vars** — `${TELEGRAM_BOT_TOKEN}` in docker-compose references Coolify UI vars, NOT .env. If empty in UI = empty in container
- **Pydantic nested settings** — nested classes MUST be `BaseModel`, not `BaseSettings`, for `env_nested_delimiter` to work
- **aiogram swallows handler errors** — configure `logging.basicConfig()` and `@dp.errors()` handler, otherwise exceptions are invisible
- **parse_mode=HTML** — bot uses HTML parse mode. Unescaped `<>` in messages will silently fail

## Docs

- `docs/deployment.md` — full deployment guide, Coolify setup, troubleshooting
- `docs/legacy-tabtouch.md` — old TabTouch system (inactive, code in repo)

## GSD Workflow

Use GSD commands for structured work:
- `/gsd:quick` — small fixes
- `/gsd:debug` — investigation
- `/gsd:execute-phase` — planned phase work
