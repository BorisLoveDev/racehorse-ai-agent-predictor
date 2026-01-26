"""
Grok agent implementation using x-ai/grok-2-1212 via OpenRouter.
Configured with high reasoning effort for deep analysis.
"""

from langchain_openai import ChatOpenAI

from .base import BaseRaceAgent
from ..config.settings import get_settings


class GrokAgent(BaseRaceAgent):
    """
    Grok agent with high reasoning effort for in-depth race analysis.
    Uses xAI's Grok model via OpenRouter with extended reasoning capabilities.
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
        openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
        self.llm = ChatOpenAI(
            model=grok_settings.model_id,
            temperature=grok_settings.temperature,
            max_tokens=grok_settings.max_tokens,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_kwargs={
                "reasoning_effort": grok_settings.reasoning_effort
            }
        )

    def _get_analysis_system_prompt(self) -> str:
        """Grok-specific analysis prompt with emphasis on deep reasoning."""
        base_prompt = super()._get_analysis_system_prompt()

        grok_specific = """

GROK AGENT APPROACH (HIGH REASONING MODE):
You are configured for maximum reasoning depth and analytical rigor.
Your analysis should:
- Explore multiple hypotheses and scenarios
- Consider non-obvious factors and edge cases
- Perform deep causal reasoning about performance factors
- Identify subtle patterns others might miss
- Challenge conventional wisdom when data supports it
- Think through race dynamics step-by-step

Take your time to reason through complex interactions between:
- Horse form trends (improving vs declining)
- Jockey/trainer combinations and their track records
- Barrier draw advantages for different running styles
- Weather/track condition impacts
- Class levels and weight adjustments
- Pace scenarios and tactical positioning

Don't just state facts - explain the reasoning chain behind your conclusions.
"""
        return base_prompt + grok_specific

    def _get_structured_output_system_prompt(self) -> str:
        """Grok-specific structured output prompt."""
        base_prompt = super()._get_structured_output_system_prompt()

        grok_specific = """

As Grok with high reasoning effort, your betting strategy emphasizes:
- Deep value identification through multi-factor analysis
- Contrarian plays when reasoning supports them
- Complex exotic bets (Trifecta, First4) when confidence is high
- Risk-adjusted bet sizing based on edge calculation
- Willingness to skip bets when edge is unclear

Your key_factors should reflect the depth of your reasoning, not just surface observations.
Your confidence_score should reflect genuine epistemic uncertainty after deep analysis.
"""
        return base_prompt + grok_specific
