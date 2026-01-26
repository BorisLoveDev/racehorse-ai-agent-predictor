"""
Gemini agent implementation using google/gemini-2.0-flash-exp:free via OpenRouter.
"""

from .base import BaseRaceAgent
from ..config.settings import get_settings


class GeminiAgent(BaseRaceAgent):
    """
    Gemini Flash agent for fast, efficient race analysis.
    Uses Google's Gemini 2.0 Flash model via OpenRouter.
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

    def _get_analysis_system_prompt(self) -> str:
        """Gemini-specific analysis prompt."""
        base_prompt = super()._get_analysis_system_prompt()

        gemini_specific = """

GEMINI AGENT APPROACH:
You are known for fast, accurate pattern recognition and data synthesis.
Focus on:
- Quick identification of key performance patterns
- Statistical trends and anomalies
- Efficient comparison of multiple runners
- Clear, concise insights

Leverage your speed to analyze more data points efficiently.
"""
        return base_prompt + gemini_specific

    def _get_structured_output_system_prompt(self) -> str:
        """Gemini-specific structured output prompt."""
        base_prompt = super()._get_structured_output_system_prompt()

        gemini_specific = """

As Gemini, your betting strategy emphasizes:
- Data-driven decisions with clear statistical backing
- Multiple bet types for diversification
- Balanced risk-reward ratios
- Quick adaptation to new information
"""
        return base_prompt + gemini_specific
