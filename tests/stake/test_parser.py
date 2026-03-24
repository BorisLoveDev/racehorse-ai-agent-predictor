"""
Tests for StakeParser and parse_race_text.

All tests use mocked LLM calls — no real API calls are made.
Mocking strategy: patch ChatOpenAI at import time so with_structured_output
returns an AsyncMock chain that resolves to predefined ParsedRace objects.
"""

import asyncio
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.stake.parser.llm_parser import StakeParser, parse_race_text
from services.stake.parser.models import MarketContext, ParsedRace, RunnerInfo
from services.stake.settings import ParserSettings, StakeSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(model: str = "test/model-v1") -> StakeSettings:
    """Create a StakeSettings instance with a custom parser model for testing."""
    settings = StakeSettings(
        openrouter_api_key="test-key",
        parser=ParserSettings(model=model, temperature=0.0, max_tokens=4000),
    )
    return settings


def _make_simple_race(
    track: Optional[str] = "Flemington",
    race_number: Optional[str] = "Race 3",
    detected_bankroll: Optional[float] = None,
) -> ParsedRace:
    """Build a minimal ParsedRace for mock returns."""
    return ParsedRace(
        track=track,
        race_number=race_number,
        runners=[
            RunnerInfo(number=1, name="Thunderbolt", win_odds=3.5, win_odds_format="decimal"),
            RunnerInfo(number=2, name="Silver Arrow", win_odds=6.0, win_odds_format="decimal"),
        ],
        detected_bankroll=detected_bankroll,
    )


# ---------------------------------------------------------------------------
# StakeParser.__init__ tests
# ---------------------------------------------------------------------------


class TestStakeParserInit:
    """Verify StakeParser initialises with correct settings and model."""

    def test_uses_provided_settings(self) -> None:
        """StakeParser should use the settings passed to __init__."""
        settings = _make_settings(model="custom/model-xyz")
        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_instance.with_structured_output.return_value = MagicMock()

            parser = StakeParser(settings=settings)

        # Model param should come from settings.parser.model
        call_kwargs = mock_llm_cls.call_args.kwargs
        assert call_kwargs["model"] == "custom/model-xyz"

    def test_uses_settings_temperature_and_max_tokens(self) -> None:
        """StakeParser should pass temperature and max_tokens from settings."""
        settings = _make_settings()
        settings.parser.temperature = 0.1
        settings.parser.max_tokens = 2000

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_instance.with_structured_output.return_value = MagicMock()

            StakeParser(settings=settings)

        call_kwargs = mock_llm_cls.call_args.kwargs
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 2000

    def test_uses_openrouter_base_url(self) -> None:
        """StakeParser must use OpenRouter API base URL."""
        settings = _make_settings()
        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_instance.with_structured_output.return_value = MagicMock()

            StakeParser(settings=settings)

        call_kwargs = mock_llm_cls.call_args.kwargs
        assert call_kwargs["openai_api_base"] == "https://openrouter.ai/api/v1"

    def test_chain_uses_structured_output_with_parsed_race(self) -> None:
        """StakeParser.chain must be wired via with_structured_output(ParsedRace)."""
        settings = _make_settings()
        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = MagicMock()
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)

        # Verify with_structured_output was called with ParsedRace
        mock_instance.with_structured_output.assert_called_once_with(ParsedRace)
        assert parser.chain is mock_chain

    def test_uses_default_settings_when_none_provided(self) -> None:
        """StakeParser should fall back to get_stake_settings() singleton."""
        default_settings = _make_settings(model="default/model")
        with patch("services.stake.parser.llm_parser.get_stake_settings", return_value=default_settings):
            with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
                mock_instance = MagicMock()
                mock_llm_cls.return_value = mock_instance
                mock_instance.with_structured_output.return_value = MagicMock()

                parser = StakeParser()

        assert parser.settings is default_settings


# ---------------------------------------------------------------------------
# StakeParser.parse tests
# ---------------------------------------------------------------------------


class TestStakeParserParse:
    """Verify StakeParser.parse invokes chain correctly and returns ParsedRace."""

    @pytest.mark.asyncio
    async def test_parse_returns_parsed_race(self) -> None:
        """parse() should return the ParsedRace returned by the chain."""
        expected = _make_simple_race(track="Flemington")
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("raw race text here")

        assert result is expected
        assert isinstance(result, ParsedRace)

    @pytest.mark.asyncio
    async def test_parse_calls_ainvoke_with_system_and_human_messages(self) -> None:
        """parse() must call chain.ainvoke with [SystemMessage, HumanMessage]."""
        from langchain_core.messages import HumanMessage, SystemMessage

        expected = _make_simple_race()
        settings = _make_settings()
        raw_text = "Race 3 Flemington 1200m Horse 1 Thunderbolt 3.50"

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            await parser.parse(raw_text)

        call_args = mock_chain.ainvoke.call_args
        messages = call_args[0][0]
        assert len(messages) == 2
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)
        assert messages[1].content == raw_text

    @pytest.mark.asyncio
    async def test_parse_includes_system_prompt(self) -> None:
        """SystemMessage content must be PARSE_SYSTEM_PROMPT."""
        from langchain_core.messages import SystemMessage
        from services.stake.parser.prompt import PARSE_SYSTEM_PROMPT

        expected = _make_simple_race()
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            await parser.parse("some text")

        messages = mock_chain.ainvoke.call_args[0][0]
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert system_msg.content == PARSE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_parse_returns_race_with_detected_bankroll(self) -> None:
        """When LLM returns detected_bankroll, parse() must preserve it."""
        expected = _make_simple_race(detected_bankroll=150.0)
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("Balance: $150.00 — Race 3 Flemington")

        assert result.detected_bankroll == 150.0

    @pytest.mark.asyncio
    async def test_parse_returns_none_bankroll_when_not_in_paste(self) -> None:
        """When LLM returns detected_bankroll=None, parse() must return None."""
        expected = _make_simple_race(detected_bankroll=None)
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("Race 3 Flemington — no balance mentioned")

        assert result.detected_bankroll is None

    @pytest.mark.asyncio
    async def test_parse_preserves_scratched_runners(self) -> None:
        """When LLM returns scratched runners, parse() must preserve them."""
        scratched_runner = RunnerInfo(number=3, name="Lame Duck", status="scratched")
        active_runner = RunnerInfo(number=1, name="Thunderbolt", status="active", win_odds=3.5)
        expected = ParsedRace(
            track="Flemington",
            runners=[active_runner, scratched_runner],
        )
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("Race 3 — Horse 3 Lame Duck SCR")

        scratched = [r for r in result.runners if r.status == "scratched"]
        assert len(scratched) == 1
        assert scratched[0].name == "Lame Duck"

    @pytest.mark.asyncio
    async def test_parse_handles_empty_runners_list(self) -> None:
        """parse() should handle a ParsedRace with no runners without error."""
        expected = ParsedRace(track="Randwick", runners=[])
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("Some unparseable text")

        assert result.runners == []
        assert result.track == "Randwick"


# ---------------------------------------------------------------------------
# parse_race_text convenience function tests
# ---------------------------------------------------------------------------


class TestParseRaceTextFunction:
    """Verify the module-level parse_race_text convenience function."""

    @pytest.mark.asyncio
    async def test_convenience_function_returns_parsed_race(self) -> None:
        """parse_race_text() should return a ParsedRace."""
        expected = _make_simple_race(track="Eagle Farm")
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            result = await parse_race_text("Race text goes here", settings=settings)

        assert isinstance(result, ParsedRace)
        assert result.track == "Eagle Farm"

    @pytest.mark.asyncio
    async def test_convenience_function_uses_provided_settings(self) -> None:
        """parse_race_text() must forward settings to StakeParser."""
        settings = _make_settings(model="special/model-test")
        expected = _make_simple_race()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            await parse_race_text("text", settings=settings)

        call_kwargs = mock_llm_cls.call_args.kwargs
        assert call_kwargs["model"] == "special/model-test"

    @pytest.mark.asyncio
    async def test_convenience_function_with_bankroll_in_text(self) -> None:
        """parse_race_text() should surface detected_bankroll from LLM result."""
        expected = _make_simple_race(detected_bankroll=500.0)
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            result = await parse_race_text(
                "Your balance: $500.00\nRace 1 Flemington", settings=settings
            )

        assert result.detected_bankroll == 500.0


# ---------------------------------------------------------------------------
# Market context test
# ---------------------------------------------------------------------------


class TestMarketContextExtraction:
    """Verify market_context field is preserved when LLM extracts it."""

    @pytest.mark.asyncio
    async def test_parse_preserves_market_context(self) -> None:
        """When LLM returns market_context, parse() must preserve all sub-fields."""
        market_ctx = MarketContext(
            big_bet_activity=["$500 on Horse #3", "$1000 on Horse #1"],
            user_activity="High activity",
            bet_slip_info="Current bet: Horse #1 Win $50",
        )
        expected = ParsedRace(
            track="Flemington",
            market_context=market_ctx,
            runners=[RunnerInfo(number=1, name="Thunderbolt")],
        )
        settings = _make_settings()

        with patch("services.stake.parser.llm_parser.ChatOpenAI") as mock_llm_cls:
            mock_instance = MagicMock()
            mock_llm_cls.return_value = mock_instance
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = expected
            mock_instance.with_structured_output.return_value = mock_chain

            parser = StakeParser(settings=settings)
            result = await parser.parse("Race with market context")

        assert result.market_context is not None
        assert result.market_context.big_bet_activity == ["$500 on Horse #3", "$1000 on Horse #1"]
        assert result.market_context.user_activity == "High activity"
