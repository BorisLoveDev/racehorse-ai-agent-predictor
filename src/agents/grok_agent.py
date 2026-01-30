"""
Grok agent implementation using x-ai/grok-4.1-fast via OpenRouter.
Configured with high reasoning effort (~80% tokens for reasoning) for deep analysis.

Grok 4.1 Fast specs:
- Context: 2,000,000 tokens (2M)
- Max output: 30,000 tokens
- Reasoning: xhigh (~95%), high (~80%), medium (~50%), low (~20%)

Optimized config (per multi-model analysis):
- max_tokens: 12,000 (caps runtime)
- reasoning_effort: high (~9.6K thinking tokens)
- web_search: disabled (research agent gathers data)
- Cost: ~$0.50/M tokens - very cheap, so high effort is ok
"""

from langchain_openai import ChatOpenAI

from .base import BaseRaceAgent
from ..config.settings import get_settings


class GrokAgent(BaseRaceAgent):
    """
    Grok agent with high reasoning effort for deep analytical depth.
    Uses xAI's Grok 4.1 Fast via OpenRouter with extended reasoning capabilities.
    """

    def __init__(self):
        settings = get_settings()
        grok_settings = settings.agents.grok

        # Call parent constructor first
        super().__init__(
            agent_name="grok",
            model_id=grok_settings.model_id,
            temperature=grok_settings.temperature,
            max_tokens=grok_settings.max_tokens,
            enable_web_search=grok_settings.enable_web_search
        )

        # Override LLM with Grok-specific configuration
        # OpenRouter uses {"reasoning": {"effort": "xhigh"}} format
        openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
        self.llm = ChatOpenAI(
            model=grok_settings.model_id,
            temperature=grok_settings.temperature,
            max_tokens=grok_settings.max_tokens,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_kwargs={
                "reasoning": {
                    "effort": grok_settings.reasoning_effort
                }
            }
        )

    def _get_analysis_system_prompt(self) -> str:
        """Grok-specific analysis prompt with emphasis on deep reasoning."""
        base_prompt = super()._get_analysis_system_prompt()

        grok_specific = """

GROK AGENT APPROACH (HIGH REASONING MODE - 80% tokens for thinking):
You are configured for deep reasoning with strong conversational insight.
You have ~9.6K tokens for reasoning - use them for thorough analysis.

Your strengths:
- Exploring multiple hypotheses and scenarios
- Creative insight and intuitive pattern recognition
- Engaging explanations that capture nuance
- Challenge conventional wisdom when data supports it

Analyze systematically:
- Horse form trends (improving vs declining)
- Jockey/trainer combinations and track records
- Barrier draw advantages for different running styles
- Weather/track condition impacts
- Class levels and weight adjustments
- Pace scenarios and tactical positioning

Provide reasoning chains, not just conclusions.
"""
        return base_prompt + grok_specific

    def _get_structured_output_system_prompt(self) -> str:
        """Grok-specific structured output prompt."""
        base_prompt = super()._get_structured_output_system_prompt()

        grok_specific = """

As Grok with high reasoning effort (~9.6K thinking tokens), your betting strategy emphasizes:
- Deep value identification through multi-factor analysis
- Contrarian plays when reasoning supports them
- Complex exotic bets (Trifecta, First4) when confidence is high
- Risk-adjusted bet sizing based on edge calculation
- Willingness to skip bets when edge is unclear

Your key_factors should reflect depth of reasoning, not just surface observations.
Your confidence_score should reflect genuine uncertainty after analysis.
Complement Gemini's rigorous logic with your creative/intuitive insights.
"""
        return base_prompt + grok_specific
