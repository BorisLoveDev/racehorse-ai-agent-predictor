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
        Also updates peak_balance_usdt if the new balance is a new high.

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

        # After updating balance, track peak
        self.update_peak_if_higher(balance)

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

    def get_peak_balance(self) -> Optional[float]:
        """Return peak_balance_usdt or None if not tracked yet.

        Returns:
            float peak balance in USDT, or None when no record exists.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT peak_balance_usdt FROM stake_bankroll WHERE id = 1")
            row = cursor.fetchone()
            if row and row[0] is not None:
                return float(row[0])
            return None
        finally:
            conn.close()

    def update_peak_if_higher(self, new_balance: float) -> None:
        """Set peak_balance_usdt to MAX(current_peak, new_balance).

        Uses MAX(COALESCE(peak_balance_usdt, 0), new_balance) so that the
        first call with any balance initialises peak from zero.

        Args:
            new_balance: Candidate new peak balance in USDT.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE stake_bankroll
                SET peak_balance_usdt = MAX(COALESCE(peak_balance_usdt, 0), ?)
                WHERE id = 1
                """,
                (float(new_balance),),
            )
            conn.commit()
        finally:
            conn.close()

    def is_drawdown_unlocked(self) -> bool:
        """Return True if drawdown_unlocked = 1 for the singleton row.

        Returns:
            True when drawdown circuit breaker has been unlocked by user.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT drawdown_unlocked FROM stake_bankroll WHERE id = 1")
            row = cursor.fetchone()
            return bool(row[0]) if row and row[0] is not None else False
        finally:
            conn.close()

    def set_drawdown_unlocked(self, unlocked: bool) -> None:
        """Set the drawdown_unlocked flag on the singleton row.

        Args:
            unlocked: True to unlock (allow bets during drawdown), False to lock.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE stake_bankroll SET drawdown_unlocked = ? WHERE id = 1",
                (1 if unlocked else 0,),
            )
            conn.commit()
        finally:
            conn.close()

    def check_and_auto_reset_drawdown(self, threshold_pct: float = 20.0) -> None:
        """Auto-reset drawdown_unlocked when balance recovers above threshold.

        If current balance >= peak * (1 - threshold_pct / 100), the drawdown
        condition no longer applies and the flag is reset to 0 (locked).

        Args:
            threshold_pct: Drawdown threshold in percent (default 20.0).
        """
        balance = self.get_balance()
        peak = self.get_peak_balance()
        if balance is None or peak is None or peak <= 0:
            return
        recovery_threshold = peak * (1 - threshold_pct / 100.0)
        if balance >= recovery_threshold:
            self.set_drawdown_unlocked(False)
