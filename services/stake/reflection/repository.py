"""
Repository for lessons (extracted reflections) in SQLite.

Provides CRUD operations on the stake_lessons table created by
run_stake_migrations(). Lessons are actionable rules extracted by the
reflection LLM after each race result.
"""

import sqlite3

from services.stake.bankroll.migrations import run_stake_migrations


class LessonsRepository:
    """Repository for lesson records in SQLite.

    Stores and queries extracted lessons for the mindset prompt system.

    Args:
        db_path: Path to SQLite database file.

    On instantiation, runs stake migrations to ensure tables exist.
    """

    def __init__(self, db_path: str = "races.db") -> None:
        self.db_path = db_path
        run_stake_migrations(db_path)

    def save_lesson(self, error_tag: str, rule_sentence: str, is_failure: bool) -> int:
        """Insert a new lesson and return its assigned id.

        Args:
            error_tag: Short category label (e.g. 'overconfidence_on_short_odds').
            rule_sentence: One actionable rule sentence.
            is_failure: True if this is a failure mode, False for positive principle.

        Returns:
            The auto-assigned integer id of the new lesson row.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO stake_lessons (error_tag, rule_sentence, is_failure)
                VALUES (?, ?, ?)
                """,
                (error_tag, rule_sentence, 1 if is_failure else 0),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_top_rules(self, limit: int = 5) -> list[dict]:
        """Return the most frequently applied lessons ordered by application_count DESC.

        Args:
            limit: Maximum number of lessons to return.

        Returns:
            List of dicts with keys: id, error_tag, rule_sentence, application_count.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, error_tag, rule_sentence, application_count
                FROM stake_lessons
                ORDER BY application_count DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "error_tag": row[1],
                    "rule_sentence": row[2],
                    "application_count": row[3],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_recent_failures(self, limit: int = 3) -> list[dict]:
        """Return the most recent failure-mode lessons.

        Args:
            limit: Maximum number of failure lessons to return.

        Returns:
            List of dicts with keys: id, error_tag, rule_sentence.
            Ordered by created_at DESC.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, error_tag, rule_sentence
                FROM stake_lessons
                WHERE is_failure = 1
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "error_tag": row[1],
                    "rule_sentence": row[2],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def increment_application_count(self, lesson_ids: list[int]) -> None:
        """Increment application_count for each given lesson id.

        Called when lessons are applied in an analysis prompt to track
        which rules are frequently relevant.

        Args:
            lesson_ids: List of lesson ids to increment.
        """
        if not lesson_ids:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" * len(lesson_ids))
            cursor.execute(
                f"""
                UPDATE stake_lessons
                SET application_count = application_count + 1
                WHERE id IN ({placeholders})
                """,
                lesson_ids,
            )
            conn.commit()
        finally:
            conn.close()
