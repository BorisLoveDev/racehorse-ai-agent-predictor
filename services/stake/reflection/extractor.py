"""
Lesson extractor for the Stake Advisor Bot.
Per REFLECT-03: Extracts one structured lesson (error_tag + rule_sentence)
from a reflection text. Saves to stake_lessons table.
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from services.stake.results.models import LessonEntry
from services.stake.reflection.repository import LessonsRepository
from services.stake.settings import get_stake_settings

logger = logging.getLogger("stake")

LESSON_EXTRACTION_PROMPT = """You are a betting lesson extractor.
Given a reflection on a resolved horse racing bet, extract exactly ONE structured lesson.

The lesson has two parts:
1. error_tag: A short 1-line category label (snake_case, e.g. "overconfidence_on_short_odds",
   "ignored_track_condition", "insufficient_research_data", "correct_value_identification")
2. rule_sentence: One actionable rule sentence (e.g. "Never exceed 15% of Kelly on runners
   with fewer than 5 races at this distance")
3. is_failure_mode: True if this is a mistake to avoid (most common), False if a positive
   pattern to reinforce

Focus on the MOST IMPORTANT lesson. Be specific — avoid generic platitudes like
"do more research" or "be careful with odds". Reference the specific signal that was
missed or correctly identified."""


class LessonExtractor:
    """Extracts structured lessons from reflection text via LLM.

    Per D-06: Uses configurable model from ReflectionSettings.
    Per REFLECT-03: Saves to stake_lessons table.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_stake_settings()
        self.llm = ChatOpenAI(
            model=self.settings.reflection.model,
            temperature=0.3,  # Lower temp for more consistent extraction
            max_tokens=500,
            openai_api_key=self.settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
        ).with_structured_output(LessonEntry)

    async def extract_and_save(
        self,
        reflection_text: str,
        db_path: str | None = None,
    ) -> LessonEntry:
        """Extract a structured lesson from reflection text and save to DB.

        Args:
            reflection_text: The full reflection text from ReflectionWriter.
            db_path: SQLite database path. Defaults to settings.database_path.

        Returns:
            LessonEntry with error_tag, rule_sentence, is_failure_mode.
        """
        lesson = await self.llm.ainvoke([
            SystemMessage(content=LESSON_EXTRACTION_PROMPT),
            HumanMessage(content=reflection_text),
        ])

        # Save to database
        path = db_path or self.settings.database_path
        repo = LessonsRepository(path)
        lesson_id = repo.save_lesson(
            error_tag=lesson.error_tag,
            rule_sentence=lesson.rule_sentence,
            is_failure=lesson.is_failure_mode,
        )

        logger.info(
            "[LESSON] Extracted: [%s] %s (id=%d, failure=%s)",
            lesson.error_tag, lesson.rule_sentence, lesson_id, lesson.is_failure_mode,
        )
        return lesson
