"""
LLM-based parser for race result text provided by the user after a race.

Converts free-form result text (numbers, names, partial) into a structured
ParsedResult using ChatOpenAI.with_structured_output.

The parser reuses the cheap parser model (flash-lite) for cost efficiency.
Confidence is set to "low" when the input is ambiguous or contradictory.
"""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from services.stake.results.models import ParsedResult
from services.stake.settings import StakeSettings, get_stake_settings


RESULT_PARSE_SYSTEM_PROMPT = """You are a horse racing result parser.
Given a user's description of a race result, extract the finishing order.

The user may provide:
- Numbers: "3,5,11,12" (runner numbers in finishing order)
- Names: "Thunder won, Lightning 2nd, Storm 3rd"
- Partial: "3 won" or "Thunder won" (only winner known)
- Mixed: "Runner 3 won, 5 second"

Rules:
- finishing_order: list of runner NUMBERS in order (1st, 2nd, 3rd...)
- finishing_names: list of runner NAMES in order (only if numbers not given)
- is_partial: True if the user only provided the winner (not full top 3+)
- confidence: "low" if the input is ambiguous or contradictory, "high" otherwise
- raw_text: preserve the original input exactly as given

If the user provides names but not numbers, set finishing_names.
If the user provides numbers, always set finishing_order.
If only 1 position given, set is_partial=True.
"""


class ResultParser:
    """LLM-based parser for race result text.

    Converts user-supplied result text into a structured ParsedResult.
    Uses the cheap parser model (flash-lite) for cost efficiency.

    Args:
        settings: Optional StakeSettings instance. Uses get_stake_settings()
                  singleton if not provided.
    """

    def __init__(self, settings: Optional[StakeSettings] = None) -> None:
        self.settings = settings or get_stake_settings()
        # Use cheap model (parser model) for result parsing — not expensive analysis model
        llm = ChatOpenAI(
            model=self.settings.parser.model,
            temperature=0.0,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        self.chain = llm.with_structured_output(ParsedResult)

    async def parse(self, raw_result_text: str) -> ParsedResult:
        """Parse free-form result text into a structured ParsedResult.

        Args:
            raw_result_text: User-supplied result string (numbers, names, partial).

        Returns:
            ParsedResult with finishing_order or finishing_names populated.
            confidence="low" when input is ambiguous.
        """
        result: ParsedResult = await self.chain.ainvoke([
            SystemMessage(content=RESULT_PARSE_SYSTEM_PROMPT),
            HumanMessage(content=raw_result_text),
        ])
        # Ensure raw_text is preserved (LLM may leave it blank)
        result.raw_text = raw_result_text
        return result
