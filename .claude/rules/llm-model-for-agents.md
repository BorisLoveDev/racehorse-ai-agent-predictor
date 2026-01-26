# LLM Models Configuration

## Supported Models (via OpenRouter)

The project uses the following models for AI agents:

- **google/gemini-3-flash-preview** - Used by GeminiAgent (fast, cost-effective)
- **x-ai/grok-4.1-fast** - Used by GrokAgent (balanced performance)

IMPORTANT: These are the only models configured and tested. Do not suggest or implement other models without explicit approval.

## Adding New Models

If you need to add a new model:

1. Verify model exists on OpenRouter: https://openrouter.ai/models
2. Create new agent class in `src/agents/`
3. Add model to database: `INSERT INTO agents (name, model_name) VALUES ('agent_name', 'model/id')`
4. Test thoroughly with `test_agent.py`
5. Update docker-compose.yml if needed
6. Document performance and cost characteristics

## Model Selection Criteria

- **Speed**: Must return predictions within 30 seconds
- **Cost**: Keep per-prediction cost under acceptable threshold
- **Reliability**: Must handle race data format consistently
- **Structured output**: Must support JSON output format