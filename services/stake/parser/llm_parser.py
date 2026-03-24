"""
LLM-based parser for Stake.com race data.

Converts raw paste text from Stake.com into a structured ParsedRace model
using ChatOpenAI.with_structured_output for reliable JSON extraction.

The parser model is configurable via StakeSettings.parser.model (D-06).
Extraction follows D-07 (full field extraction), D-08 (null for absent fields),
D-10 (scratched runner detection), and PARSE-03 (bankroll detection).
"""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from services.stake.parser.models import ParsedRace
from services.stake.parser.prompt import PARSE_SYSTEM_PROMPT
from services.stake.settings import StakeSettings, get_stake_settings


class StakeParser:
    """
    LLM-based parser that converts raw Stake.com race text to ParsedRace.

    Uses ChatOpenAI.with_structured_output to reliably extract the full
    ParsedRace schema from arbitrary paste format.

    Args:
        settings: Optional StakeSettings instance. Uses get_stake_settings()
                  singleton if not provided.
    """

    def __init__(self, settings: Optional[StakeSettings] = None) -> None:
        self.settings = settings or get_stake_settings()
        self.llm = ChatOpenAI(
            model=self.settings.parser.model,
            temperature=self.settings.parser.temperature,
            max_tokens=self.settings.parser.max_tokens,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        # Bind structured output to ParsedRace Pydantic model
        self.chain = self.llm.with_structured_output(ParsedRace)

    async def parse(self, raw_text: str) -> ParsedRace:
        """
        Parse raw Stake.com paste text into a structured ParsedRace.

        Args:
            raw_text: Raw text pasted from a Stake.com race page.

        Returns:
            ParsedRace Pydantic model with all extractable fields populated.
            Absent fields are set to None per D-08.
        """
        result = await self.chain.ainvoke([
            SystemMessage(content=PARSE_SYSTEM_PROMPT),
            HumanMessage(content=raw_text),
        ])
        return result


async def parse_race_text(
    raw_text: str,
    settings: Optional[StakeSettings] = None,
) -> ParsedRace:
    """
    Convenience function for one-shot parsing of Stake.com race text.

    Args:
        raw_text: Raw text pasted from a Stake.com race page.
        settings: Optional StakeSettings. Uses singleton if not provided.

    Returns:
        ParsedRace Pydantic model.
    """
    parser = StakeParser(settings=settings)
    return await parser.parse(raw_text)
