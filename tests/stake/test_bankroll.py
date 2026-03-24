"""
Unit tests for BankrollRepository and stake migrations.
Uses pytest tmp_path fixture for isolated SQLite databases.
"""

import sqlite3
import pytest

from services.stake.bankroll.repository import BankrollRepository
from services.stake.bankroll.migrations import run_stake_migrations


class TestRunStakeMigrations:
    """Tests for the run_stake_migrations function."""

    def test_creates_stake_bankroll_table(self, tmp_path):
        """run_stake_migrations creates stake_bankroll table."""
        db_path = str(tmp_path / "test.db")
        run_stake_migrations(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stake_bankroll'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_creates_stake_pipeline_runs_table(self, tmp_path):
        """run_stake_migrations creates stake_pipeline_runs table."""
        db_path = str(tmp_path / "test.db")
        run_stake_migrations(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stake_pipeline_runs'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_idempotent_migration(self, tmp_path):
        """run_stake_migrations is safe to call multiple times (CREATE TABLE IF NOT EXISTS)."""
        db_path = str(tmp_path / "test.db")
        # Should not raise on second call
        run_stake_migrations(db_path)
        run_stake_migrations(db_path)

    def test_bankroll_table_has_singleton_constraint(self, tmp_path):
        """stake_bankroll table uses CHECK (id = 1) to enforce singleton row."""
        db_path = str(tmp_path / "test.db")
        run_stake_migrations(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Insert with id=1 should succeed
        cursor.execute(
            "INSERT INTO stake_bankroll (id, balance_usdt, stake_pct) VALUES (1, 100.0, 0.02)"
        )
        conn.commit()
        # Insert with id=2 should fail (CHECK constraint)
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO stake_bankroll (id, balance_usdt, stake_pct) VALUES (2, 200.0, 0.02)"
            )
        conn.close()


class TestBankrollRepository:
    """Tests for BankrollRepository CRUD operations."""

    def test_get_balance_returns_none_when_empty(self, tmp_path):
        """get_balance returns None when no bankroll record exists."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        result = repo.get_balance()
        assert result is None

    def test_set_balance_stores_value(self, tmp_path):
        """set_balance stores balance; get_balance returns it."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        repo.set_balance(100.0)
        result = repo.get_balance()
        assert result == 100.0

    def test_set_balance_updates_existing_record(self, tmp_path):
        """set_balance updates existing record without creating duplicates."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        repo.set_balance(100.0)
        repo.set_balance(200.0)
        result = repo.get_balance()
        assert result == 200.0

        # Verify only one row in table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stake_bankroll")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    def test_get_balance_returns_float(self, tmp_path):
        """get_balance returns float, not int."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        repo.set_balance(100)  # pass int
        result = repo.get_balance()
        assert isinstance(result, float)
        assert result == 100.0

    def test_get_stake_pct_returns_default_when_no_row(self, tmp_path):
        """get_stake_pct returns default 0.02 when no bankroll record exists."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        result = repo.get_stake_pct()
        assert result == 0.02

    def test_set_stake_pct_updates_value(self, tmp_path):
        """set_stake_pct updates stake percentage."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        repo.set_stake_pct(0.05)
        result = repo.get_stake_pct()
        assert result == 0.05

    def test_balance_persists_across_repository_instances(self, tmp_path):
        """Bankroll balance persists across repository instantiations (SQLite)."""
        db_path = str(tmp_path / "test.db")
        repo1 = BankrollRepository(db_path=db_path)
        repo1.set_balance(500.0)

        # Create new instance pointing to same db
        repo2 = BankrollRepository(db_path=db_path)
        result = repo2.get_balance()
        assert result == 500.0

    def test_set_balance_preserves_stake_pct(self, tmp_path):
        """set_balance does not reset existing stake_pct."""
        db_path = str(tmp_path / "test.db")
        repo = BankrollRepository(db_path=db_path)
        repo.set_balance(100.0)
        repo.set_stake_pct(0.05)
        repo.set_balance(200.0)  # Update balance
        # stake_pct should remain 0.05
        assert repo.get_stake_pct() == 0.05

    def test_migrations_auto_run_on_init(self, tmp_path):
        """BankrollRepository runs migrations on init."""
        db_path = str(tmp_path / "test.db")
        # Just creating repo should create the table
        BankrollRepository(db_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stake_bankroll'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None
