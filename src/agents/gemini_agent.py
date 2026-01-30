"""
Gemini agent implementation using google/gemini-3-flash-preview via OpenRouter.
Configured with 32K reasoning tokens (thinking budget) for deep analysis.

Gemini 3 Flash specs:
- Context: 1,048,576 tokens (1M)
- Max output: 65,536 tokens
- Reasoning: up to 32K tokens for thinking budget
"""

from langchain_openai import ChatOpenAI

from .base import BaseRaceAgent
from ..config.settings import get_settings


class GeminiAgent(BaseRaceAgent):
    """
    Gemini agent with 32K reasoning budget for in-depth race analysis.
    Uses Google's Gemini 3 Flash via OpenRouter with extended thinking capabilities.
    """

    def __init__(self):
        settings = get_settings()
        gemini_settings = settings.agents.gemini

        super().__init__(
            agent_name="gemini",
            model_id=gemini_settings.model_id,
            temperature=gemini_settings.temperature,
            max_tokens=gemini_settings.max_tokens,
            enable_web_search=gemini_settings.enable_web_search
        )

        # Override LLM with reasoning configuration
        # Gemini uses reasoning.max_tokens (token budget) instead of reasoning_effort
        openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
        self.llm = ChatOpenAI(
            model=gemini_settings.model_id,
            temperature=gemini_settings.temperature,
            max_tokens=gemini_settings.max_tokens,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_kwargs={
                "reasoning": {
                    "max_tokens": gemini_settings.reasoning_max_tokens
                }
            }
        )

    def _get_analysis_system_prompt(self) -> str:
        """Gemini-specific analysis prompt."""
        base_prompt = super()._get_analysis_system_prompt()

        gemini_specific = """

GEMINI AGENT APPROACH (32K THINKING BUDGET):
You are configured with extended reasoning capacity for deep analysis.
Use your thinking tokens to:
- Thoroughly analyze all runners' form, not just favorites
- Identify non-obvious patterns and correlations
- Consider multiple race scenarios and pace dynamics
- Evaluate risk factors comprehensively
- Think through cause-effect relationships

Your analysis should reflect the depth afforded by your large reasoning budget.
"""
        return base_prompt + gemini_specific

    def _get_structured_output_system_prompt(self) -> str:
        """Gemini-specific structured output prompt."""
        base_prompt = super()._get_structured_output_system_prompt()

        gemini_specific = """

As Gemini with 32K thinking budget, your betting strategy emphasizes:
- Deep data-driven decisions with thorough statistical analysis
- Multiple bet types for diversification when analysis supports it
- Well-reasoned risk-reward assessments
- Comprehensive consideration of all factors before final recommendations
- Clear explanation of reasoning chain in key_factors
"""
        return base_prompt + gemini_specific
