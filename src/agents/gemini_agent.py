"""
Gemini agent implementation using google/gemini-3-flash-preview via OpenRouter.
Configured with high reasoning effort (~80% tokens for thinking) for deep analysis.

Gemini 3 Flash specs:
- Context: 1,048,576 tokens (1M)
- Max output: 65,536 tokens
- Reasoning: high (~80%), medium (~50%), low (~20%)

Optimized config (per multi-model analysis):
- max_tokens: 10,000 (caps runtime/cost)
- reasoning_effort: high (~8K thinking tokens)
- web_search: disabled (research agent gathers data)
"""

from langchain_openai import ChatOpenAI

from .base import BaseRaceAgent
from ..config.settings import get_settings


class GeminiAgent(BaseRaceAgent):
    """
    Gemini agent with high reasoning effort for in-depth race analysis.
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
        # Using effort level instead of raw max_tokens for better budget allocation
        openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
        self.llm = ChatOpenAI(
            model=gemini_settings.model_id,
            temperature=gemini_settings.temperature,
            max_tokens=gemini_settings.max_tokens,
            openai_api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_kwargs={
                "reasoning": {
                    "effort": gemini_settings.reasoning_effort
                }
            }
        )

    def _get_analysis_system_prompt(self) -> str:
        """Gemini-specific analysis prompt."""
        base_prompt = super()._get_analysis_system_prompt()

        gemini_specific = """

GEMINI AGENT APPROACH (HIGH REASONING MODE - 80% tokens for thinking):
You are configured for deep reasoning with high analytical rigor.
Your analysis should:
- Thoroughly analyze all runners' form, not just favorites
- Identify non-obvious patterns and correlations
- Consider multiple race scenarios and pace dynamics
- Evaluate risk factors with statistical precision
- Think through cause-effect relationships step-by-step

You have ~8K tokens for reasoning - use them wisely for rigorous analysis.
Don't just state facts - explain the reasoning chain behind conclusions.
"""
        return base_prompt + gemini_specific

    def _get_structured_output_system_prompt(self) -> str:
        """Gemini-specific structured output prompt."""
        base_prompt = super()._get_structured_output_system_prompt()

        gemini_specific = """

As Gemini with high reasoning effort (80% thinking budget), your betting strategy emphasizes:
- Deep data-driven decisions with thorough statistical analysis
- Multiple bet types for diversification when analysis supports it
- Well-reasoned risk-reward assessments with clear probability estimates
- Comprehensive consideration of all factors before final recommendations
- Clear explanation of reasoning chain in key_factors

Your confidence_score should reflect genuine epistemic uncertainty after deep analysis.
"""
        return base_prompt + gemini_specific
