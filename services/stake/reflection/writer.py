"""
Reflection writer for the Stake Advisor Bot.
Per REFLECT-01: Writes structured reflection to mindset.md after each result.
Per REFLECT-02: Explicitly asks 'what went wrong even in winning bets'.
"""
import logging
import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from services.stake.settings import get_stake_settings

logger = logging.getLogger("stake")

REFLECTION_SYSTEM_PROMPT = """You are a professional betting analyst reviewing a resolved horse racing bet.

Your job is to write a calibration-focused reflection. The goal is NOT to celebrate wins
or explain losses — it's to identify where the model's PROBABILITIES were wrong.

Even in a winning bet, ask:
- Was the assigned probability accurate, or did we just get lucky?
- Did research data justify the confidence level?
- Was the Kelly sizing appropriate given what we knew?

Required sections:
1. What happened (1-2 sentences — just the facts)
2. Probability calibration (was ai_win_prob realistic?)
3. What went wrong (even if we won — overconfidence, missing signals, bad data)
4. What the market knew that we missed

Be blunt. Self-serving explanations erode the model's ability to improve.

Output ONLY the reflection text. No headers, no markdown formatting, no preamble."""


class ReflectionWriter:
    """Writes LLM-generated calibration-aware reflections to mindset.md.

    Per D-06: Uses configurable model from ReflectionSettings.
    Per D-07: Appends to mindset.md file (human-readable reflection log).
    """

    def __init__(self, settings=None):
        self.settings = settings or get_stake_settings()
        self.llm = ChatOpenAI(
            model=self.settings.reflection.model,
            temperature=self.settings.reflection.temperature,
            max_tokens=self.settings.reflection.max_tokens,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        # Derive mindset.md path from settings; create parent dir if needed
        self.mindset_path = self.settings.reflection.mindset_path
        parent = os.path.dirname(self.mindset_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _build_reflection_input(
        self,
        outcomes: list[dict],
        final_bets: list[dict],
        parsed_result: dict,
    ) -> str:
        """Build the human message for the reflection LLM call."""
        lines = ["=== BET OUTCOMES ==="]
        for o in outcomes:
            status = "WON" if o.get("won") else "LOST"
            eval_note = "" if o.get("evaluable", True) else " (not evaluable — partial result)"
            lines.append(
                f"#{o.get('runner_number')} {o.get('runner_name')} "
                f"({o.get('bet_type')}): {status} | "
                f"Profit: {o.get('profit_usdt', 0):+.2f} USDT | "
                f"Odds: {o.get('decimal_odds', '?')}{eval_note}"
            )

        lines.append("\n=== ORIGINAL RECOMMENDATIONS ===")
        for b in final_bets:
            lines.append(
                f"#{b.get('runner_number')} {b.get('runner_name')} "
                f"({b.get('bet_type')}): {b.get('usdt_amount', 0):.2f} USDT | "
                f"EV: {b.get('ev', 0):+.3f} | Kelly: {b.get('kelly_pct', 0):.1f}%"
            )

        lines.append(f"\n=== ACTUAL RESULT ===")
        lines.append(f"Finishing order: {parsed_result.get('finishing_order', [])}")
        lines.append(f"Partial: {parsed_result.get('is_partial', False)}")

        return "\n".join(lines)

    async def write_reflection(
        self,
        outcomes: list[dict],
        final_bets: list[dict],
        parsed_result: dict,
    ) -> str:
        """Generate reflection via LLM and append to mindset.md.

        Returns the reflection text (for subsequent lesson extraction).
        """
        human_input = self._build_reflection_input(outcomes, final_bets, parsed_result)

        response = await self.llm.ainvoke([
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(content=human_input),
        ])

        reflection_text = response.content if hasattr(response, "content") else str(response)

        # Append to mindset.md
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        entry = (
            f"\n---\n\n"
            f"## Reflection — {timestamp}\n\n"
            f"{reflection_text}\n"
        )

        with open(self.mindset_path, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.info("[REFLECTION] Written to %s (%d chars)", self.mindset_path, len(reflection_text))
        return reflection_text
