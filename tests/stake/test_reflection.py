"""
Tests for Phase 3 reflection: LessonsRepository CRUD.
"""

import pytest

from services.stake.reflection.repository import LessonsRepository


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
