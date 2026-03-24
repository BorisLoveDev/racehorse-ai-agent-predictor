"""
Bankroll repository for the Stake Advisor Bot.
Provides SQLite-backed CRUD for bankroll state (balance and stake percentage).

The stake_bankroll table uses a singleton row pattern (id = 1) enforced by
a CHECK constraint. All writes use INSERT ... ON CONFLICT DO UPDATE (upsert).
"""

import sqlite3
from typing import Optional

from services.stake.bankroll.migrations import run_stake_migrations


class BankrollRepository:
    """Repository for bankroll state in SQLite.

    Args:
        db_path: Path to SQLite database file.

    On instantiation, runs stake migrations to ensure the table exists.
    """

    def __init__(self, db_path: str = "races.db") -> None:
        self.db_path = db_path
        run_stake_migrations(db_path)

    def get_balance(self) -> Optional[float]:
        """Return current bankroll balance in USDT, or None if not set.

        Returns:
            float balance, or None when no bankroll record exists.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance_usdt FROM stake_bankroll WHERE id = 1")
            row = cursor.fetchone()
            return float(row[0]) if row else None
        finally:
            conn.close()

    def set_balance(self, balance: float) -> None:
        """Create or update the bankroll balance.

        Uses upsert to avoid duplicate rows. Preserves existing stake_pct
        when updating balance (only updates balance_usdt and updated_at).

        Args:
            balance: New balance in USDT.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # First check if a row exists so we can preserve stake_pct
            cursor.execute("SELECT stake_pct FROM stake_bankroll WHERE id = 1")
            existing = cursor.fetchone()

            if existing is not None:
                # Update only balance, preserve stake_pct
                cursor.execute("""
                    UPDATE stake_bankroll
                    SET balance_usdt = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (float(balance),))
            else:
                # Insert with default stake_pct
                cursor.execute("""
                    INSERT INTO stake_bankroll (id, balance_usdt, stake_pct)
                    VALUES (1, ?, 0.02)
                """, (float(balance),))

            conn.commit()
        finally:
            conn.close()

    def get_stake_pct(self) -> float:
        """Return current stake percentage, defaulting to 0.02 if not set.

        Returns:
            float stake_pct (e.g. 0.02 = 2% of bankroll).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT stake_pct FROM stake_bankroll WHERE id = 1")
            row = cursor.fetchone()
            return float(row[0]) if row else 0.02
        finally:
            conn.close()

    def set_stake_pct(self, pct: float) -> None:
        """Create or update the stake percentage.

        Uses upsert to avoid duplicate rows. When no row exists, inserts
        with balance_usdt=0.0 as placeholder.

        Args:
            pct: Stake fraction (e.g. 0.05 = 5% of bankroll).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO stake_bankroll (id, balance_usdt, stake_pct)
                VALUES (1, 0.0, ?)
                ON CONFLICT(id) DO UPDATE SET
                    stake_pct = excluded.stake_pct,
                    updated_at = CURRENT_TIMESTAMP
            """, (float(pct),))
            conn.commit()
        finally:
            conn.close()
