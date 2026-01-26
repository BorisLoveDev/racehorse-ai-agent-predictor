# Coding Standards

## Python Style

- Follow PEP 8 conventions
- Use type hints for function parameters and return values
- Use async/await for I/O operations (Playwright, Redis, database)
- Keep functions focused and single-purpose

## AI Agent Guidelines

### Model Selection

- **Gemini**: `google/gemini-3-flash-preview` (fast, cost-effective)
- **Grok**: `x-ai/grok-4.1-fast` (balanced performance)

IMPORTANT: These are the only models configured to work with OpenRouter. Do not suggest or use other models.

### Structured Output

All agents must return `StructuredBet` with:
- Confidence score (0.0-1.0)
- Bet types: win, place, exacta, trifecta, quinella, first4, qps
- Horse numbers and reasoning

## Service Development

### Redis Pub/Sub Patterns

```python
# Publishing
await redis_client.publish(
    "channel:name",
    json.dumps({"key": "value"})
)

# Subscribing
async with redis_client.pubsub() as pubsub:
    await pubsub.subscribe("channel:name")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
```

### Error Handling

- Wrap external API calls in try/except
- Log errors with context (race_url, agent_name, etc.)
- Use exponential backoff for retries
- Never let service crash - log and continue

### Database Access

- Use repositories from `src/database/repositories.py`
- Always commit transactions
- Use context managers for connections
- Handle database locks gracefully

## Testing

- Test AI agents with real race URLs using `test_agent.py`
- Test scrapers with current races using `show_next_races.py`
- Test end-to-end with Docker Compose
- Verify Redis pub/sub with `redis-cli MONITOR`

## Environment Variables

Never hardcode:
- API keys (use `OPENROUTER_API_KEY`)
- Telegram credentials (use `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- Timezones (use `SOURCE_TIMEZONE`, `CLIENT_TIMEZONE`)
- Service URLs (use environment variables)

## Docker Best Practices

- Keep base image lean (only common dependencies)
- Use multi-stage builds when possible
- Set proper healthchecks
- Use restart policies for production
- Mount volumes for persistent data (database, logs)
