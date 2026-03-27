"""
Tests for Phase 3 reflection: LessonsRepository CRUD, ReflectionWriter, LessonExtractor.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.stake.reflection.repository import LessonsRepository
from services.stake.reflection.writer import ReflectionWriter, REFLECTION_SYSTEM_PROMPT
from services.stake.reflection.extractor import LessonExtractor, LESSON_EXTRACTION_PROMPT
from services.stake.results.models import LessonEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite db path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def lessons_repo(tmp_db):
    return LessonsRepository(db_path=tmp_db)


# ---------------------------------------------------------------------------
# LessonsRepository tests
# ---------------------------------------------------------------------------


def test_save_lesson_returns_id(lessons_repo):
    """save_lesson inserts a row and returns id > 0."""
    lesson_id = lessons_repo.save_lesson(
        error_tag="overconfidence",
        rule_sentence="Do not overconfidently bet on short odds.",
        is_failure=True,
    )
    assert isinstance(lesson_id, int)
    assert lesson_id > 0


def test_save_multiple_lessons(lessons_repo):
    """Multiple saves return incrementing ids."""
    id1 = lessons_repo.save_lesson("tag_a", "Rule A", is_failure=True)
    id2 = lessons_repo.save_lesson("tag_b", "Rule B", is_failure=False)
    assert id2 > id1


def test_get_top_rules_ordered_by_application_count(lessons_repo):
    """get_top_rules returns lessons ordered by application_count DESC."""
    id1 = lessons_repo.save_lesson("low_tag", "Low usage rule", is_failure=False)
    id2 = lessons_repo.save_lesson("high_tag", "High usage rule", is_failure=False)
    id3 = lessons_repo.save_lesson("mid_tag", "Mid usage rule", is_failure=False)

    # Increment counts — each call represents one application event
    lessons_repo.increment_application_count([id2])  # count: id2=1
    lessons_repo.increment_application_count([id2])  # count: id2=2
    lessons_repo.increment_application_count([id2])  # count: id2=3
    lessons_repo.increment_application_count([id3])  # count: id3=1
    lessons_repo.increment_application_count([id3])  # count: id3=2
    lessons_repo.increment_application_count([id1])  # count: id1=1

    top_rules = lessons_repo.get_top_rules(limit=3)
    assert len(top_rules) == 3
    # Most applied first
    assert top_rules[0]["error_tag"] == "high_tag"
    assert top_rules[0]["application_count"] == 3
    assert top_rules[1]["error_tag"] == "mid_tag"
    assert top_rules[2]["error_tag"] == "low_tag"


def test_get_recent_failures_only_failure_mode(lessons_repo):
    """get_recent_failures returns only is_failure=1 rows."""
    lessons_repo.save_lesson("positive_rule", "Good strategy", is_failure=False)
    id_fail1 = lessons_repo.save_lesson("fail_tag_1", "Failure rule 1", is_failure=True)
    id_fail2 = lessons_repo.save_lesson("fail_tag_2", "Failure rule 2", is_failure=True)

    failures = lessons_repo.get_recent_failures(limit=5)
    assert all(f["error_tag"].startswith("fail_tag") for f in failures)
    assert len(failures) == 2


def test_get_recent_failures_ordered_by_created_at(lessons_repo):
    """get_recent_failures returns most recent failure first."""
    id1 = lessons_repo.save_lesson("older_failure", "Old rule", is_failure=True)
    id2 = lessons_repo.save_lesson("newer_failure", "New rule", is_failure=True)

    failures = lessons_repo.get_recent_failures(limit=2)
    # Most recent is "newer_failure" (higher id = later creation)
    assert failures[0]["error_tag"] == "newer_failure"


def test_increment_application_count(lessons_repo):
    """increment_application_count increases the count correctly."""
    lesson_id = lessons_repo.save_lesson("tag", "Rule", is_failure=False)
    # Apply three times
    lessons_repo.increment_application_count([lesson_id])
    lessons_repo.increment_application_count([lesson_id])
    lessons_repo.increment_application_count([lesson_id])

    top = lessons_repo.get_top_rules(limit=1)
    assert top[0]["application_count"] == 3


def test_increment_application_count_multiple_ids(lessons_repo):
    """increment_application_count works with a list of multiple ids."""
    id1 = lessons_repo.save_lesson("tag1", "Rule 1", is_failure=False)
    id2 = lessons_repo.save_lesson("tag2", "Rule 2", is_failure=False)

    lessons_repo.increment_application_count([id1, id2])

    top = lessons_repo.get_top_rules(limit=2)
    counts = {r["error_tag"]: r["application_count"] for r in top}
    assert counts["tag1"] == 1
    assert counts["tag2"] == 1


def test_get_top_rules_empty(lessons_repo):
    """get_top_rules returns empty list when no lessons saved."""
    assert lessons_repo.get_top_rules() == []


def test_get_recent_failures_empty(lessons_repo):
    """get_recent_failures returns empty list when no failures."""
    assert lessons_repo.get_recent_failures() == []


def test_increment_empty_list_noop(lessons_repo):
    """increment_application_count with empty list is a no-op."""
    # Should not raise
    lessons_repo.increment_application_count([])


# ---------------------------------------------------------------------------
# ReflectionWriter fixtures and tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_reflection_writer(tmp_path):
    """ReflectionWriter with mocked LLM and temp mindset path."""
    settings = MagicMock()
    settings.reflection.model = "test-model"
    settings.reflection.temperature = 0.7
    settings.reflection.max_tokens = 4000
    settings.reflection.mindset_path = str(tmp_path / "mindset.md")
    settings.openrouter_api_key = "test-key"
    with patch("services.stake.reflection.writer.ChatOpenAI"):
        writer = ReflectionWriter(settings=settings)
        writer.llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Test reflection: probability was overestimated."
        writer.llm.ainvoke = AsyncMock(return_value=mock_response)
        yield writer


def test_reflection_system_prompt_contains_what_went_wrong():
    """REFLECT-02: REFLECTION_SYSTEM_PROMPT explicitly addresses 'what went wrong'."""
    assert "what went wrong" in REFLECTION_SYSTEM_PROMPT.lower()


def test_build_reflection_input_contains_outcome_data(mock_reflection_writer):
    """_build_reflection_input includes runner names and WON/LOST status."""
    outcomes = [
        {
            "runner_number": 3,
            "runner_name": "Speedy Horse",
            "bet_type": "win",
            "won": True,
            "profit_usdt": 12.5,
            "decimal_odds": 4.5,
            "evaluable": True,
        }
    ]
    final_bets = [
        {
            "runner_number": 3,
            "runner_name": "Speedy Horse",
            "bet_type": "win",
            "usdt_amount": 5.0,
            "ev": 0.125,
            "kelly_pct": 8.3,
        }
    ]
    parsed_result = {"finishing_order": [3, 1, 7], "is_partial": False}

    result = mock_reflection_writer._build_reflection_input(outcomes, final_bets, parsed_result)

    assert "Speedy Horse" in result
    assert "WON" in result
    assert "+12.50" in result
    assert "=== BET OUTCOMES ===" in result
    assert "=== ORIGINAL RECOMMENDATIONS ===" in result
    assert "=== ACTUAL RESULT ===" in result
    assert "[3, 1, 7]" in result


def test_build_reflection_input_marks_non_evaluable(mock_reflection_writer):
    """_build_reflection_input adds 'not evaluable' note for partial results."""
    outcomes = [
        {
            "runner_number": 2,
            "runner_name": "Dark Horse",
            "bet_type": "place",
            "won": False,
            "profit_usdt": -3.0,
            "decimal_odds": 2.0,
            "evaluable": False,
        }
    ]
    result = mock_reflection_writer._build_reflection_input(outcomes, [], {"finishing_order": [], "is_partial": True})
    assert "not evaluable" in result


@pytest.mark.asyncio
async def test_write_reflection_appends_to_file(mock_reflection_writer):
    """write_reflection appends entry to mindset.md and returns reflection text."""
    outcomes = [
        {
            "runner_number": 1,
            "runner_name": "Rocket",
            "bet_type": "win",
            "won": False,
            "profit_usdt": -5.0,
            "decimal_odds": 3.0,
            "evaluable": True,
        }
    ]
    final_bets = []
    parsed_result = {"finishing_order": [5, 2, 1], "is_partial": False}

    text = await mock_reflection_writer.write_reflection(outcomes, final_bets, parsed_result)

    assert text == "Test reflection: probability was overestimated."

    # Verify file was created and contains expected header
    with open(mock_reflection_writer.mindset_path, "r") as f:
        content = f.read()

    assert "## Reflection —" in content
    assert "Test reflection: probability was overestimated." in content


@pytest.mark.asyncio
async def test_write_reflection_appends_multiple_entries(mock_reflection_writer):
    """Multiple write_reflection calls append multiple entries to mindset.md."""
    outcomes = [
        {
            "runner_number": 1,
            "runner_name": "Horse A",
            "bet_type": "win",
            "won": True,
            "profit_usdt": 10.0,
            "decimal_odds": 3.0,
            "evaluable": True,
        }
    ]

    await mock_reflection_writer.write_reflection(outcomes, [], {"finishing_order": [1], "is_partial": False})
    await mock_reflection_writer.write_reflection(outcomes, [], {"finishing_order": [1], "is_partial": False})

    with open(mock_reflection_writer.mindset_path, "r") as f:
        content = f.read()

    assert content.count("## Reflection —") == 2


def test_writer_mindset_path_from_settings(mock_reflection_writer, tmp_path):
    """ReflectionWriter.mindset_path is derived from settings, not hardcoded."""
    assert mock_reflection_writer.mindset_path == str(tmp_path / "mindset.md")


# ---------------------------------------------------------------------------
# LessonExtractor fixtures and tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_lesson_extractor(tmp_path):
    """LessonExtractor with mocked LLM and temp database."""
    settings = MagicMock()
    settings.reflection.model = "test-model"
    settings.openrouter_api_key = "test-key"
    settings.database_path = str(tmp_path / "test.db")
    with patch("services.stake.reflection.extractor.ChatOpenAI") as mock_cls:
        mock_llm = MagicMock()
        mock_cls.return_value.with_structured_output.return_value = mock_llm
        extractor = LessonExtractor(settings=settings)
        mock_lesson = LessonEntry(
            error_tag="overconfidence_on_favourite",
            rule_sentence="Reduce sizing when favourite has < 3 recent wins",
            is_failure_mode=True,
        )
        extractor.llm = AsyncMock(return_value=mock_lesson)
        extractor.llm.ainvoke = AsyncMock(return_value=mock_lesson)
        yield extractor, settings


def test_lesson_extraction_prompt_contains_required_fields():
    """LESSON_EXTRACTION_PROMPT contains error_tag and rule_sentence."""
    assert "error_tag" in LESSON_EXTRACTION_PROMPT
    assert "rule_sentence" in LESSON_EXTRACTION_PROMPT


@pytest.mark.asyncio
async def test_extract_and_save_returns_lesson_entry(mock_lesson_extractor):
    """extract_and_save returns a LessonEntry with correct fields."""
    extractor, settings = mock_lesson_extractor
    reflection_text = "The model overestimated the favourite's probability."

    lesson = await extractor.extract_and_save(reflection_text, db_path=settings.database_path)

    assert isinstance(lesson, LessonEntry)
    assert lesson.error_tag == "overconfidence_on_favourite"
    assert lesson.rule_sentence == "Reduce sizing when favourite has < 3 recent wins"
    assert lesson.is_failure_mode is True


@pytest.mark.asyncio
async def test_extract_and_save_persists_to_database(mock_lesson_extractor):
    """extract_and_save saves the lesson to stake_lessons table."""
    extractor, settings = mock_lesson_extractor
    db_path = settings.database_path

    await extractor.extract_and_save("Some reflection text.", db_path=db_path)

    # Verify by reading directly from repository
    repo = LessonsRepository(db_path=db_path)
    top_rules = repo.get_top_rules(limit=10)
    assert len(top_rules) == 1
    assert top_rules[0]["error_tag"] == "overconfidence_on_favourite"
    assert top_rules[0]["rule_sentence"] == "Reduce sizing when favourite has < 3 recent wins"


@pytest.mark.asyncio
async def test_extract_and_save_uses_db_path_argument(tmp_path, mock_lesson_extractor):
    """extract_and_save uses the provided db_path, not the settings default."""
    extractor, settings = mock_lesson_extractor
    custom_db = str(tmp_path / "custom.db")

    await extractor.extract_and_save("Reflection text.", db_path=custom_db)

    repo = LessonsRepository(db_path=custom_db)
    rules = repo.get_top_rules(limit=10)
    assert len(rules) == 1
