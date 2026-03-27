"""
Repository for bet outcome persistence in SQLite.

Provides CRUD operations on the stake_bet_outcomes table created by
run_stake_migrations().
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from services.stake.bankroll.migrations import run_stake_migrations


class BetOutcomesRepository:
    """Repository for bet outcome records in SQLite.

    Stores and queries BetOutcome data for P&L tracking and statistics.

    Args:
        db_path: Path to SQLite database file.

    On instantiation, runs stake migrations to ensure tables exist.
    """

    def __init__(self, db_path: str = "races.db") -> None:
        self.db_path = db_path
        run_stake_migrations(db_path)

    def save_outcomes(self, run_id: int, is_placed: bool, outcomes: list[dict]) -> None:
        """Insert multiple BetOutcome dicts into stake_bet_outcomes.

        Args:
            run_id: The stake_pipeline_runs.run_id this result belongs to.
            is_placed: True if user confirmed they actually placed the bets.
            outcomes: List of BetOutcome dicts (or BetOutcome.model_dump() dicts).
        """
        if not outcomes:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            for outcome in outcomes:
                cursor.execute(
                    """
                    INSERT INTO stake_bet_outcomes
                        (run_id, is_placed, runner_name, runner_number,
                         bet_type, amount_usdt, decimal_odds, place_odds,
                         won, profit_usdt, evaluable)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        1 if is_placed else 0,
                        outcome.get("runner_name", ""),
                        outcome.get("runner_number"),
                        outcome.get("bet_type", "win"),
                        float(outcome.get("amount_usdt", 0.0)),
                        outcome.get("decimal_odds"),
                        outcome.get("place_odds"),
                        1 if outcome.get("won") else 0,
                        float(outcome.get("profit_usdt", 0.0)),
                        1 if outcome.get("evaluable", True) else 0,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_total_stats(self, placed_only: bool = True) -> dict:
        """Return aggregate P&L statistics across all evaluable bets.

        Args:
            placed_only: If True, only include bets where is_placed=1.
                         Tracked-only bets (is_placed=0) are excluded by default.

        Returns:
            Dict with keys: total_bets, wins, win_rate, total_profit_usdt, roi_pct.
            win_rate and roi_pct are 0.0 when no bets available.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            placed_filter = "AND is_placed = 1" if placed_only else ""
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_bets,
                    SUM(won) AS wins,
                    SUM(profit_usdt) AS total_profit_usdt,
                    SUM(amount_usdt) AS total_staked
                FROM stake_bet_outcomes
                WHERE evaluable = 1
                {placed_filter}
                """
            )
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "total_bets": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "total_profit_usdt": 0.0,
                    "roi_pct": 0.0,
                }

            total_bets = row[0] or 0
            wins = row[1] or 0
            total_profit = row[2] or 0.0
            total_staked = row[3] or 0.0

            win_rate = (wins / total_bets * 100.0) if total_bets > 0 else 0.0
            roi_pct = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0

            return {
                "total_bets": total_bets,
                "wins": wins,
                "win_rate": round(win_rate, 2),
                "total_profit_usdt": round(total_profit, 4),
                "roi_pct": round(roi_pct, 2),
            }
        finally:
            conn.close()

    def get_period_stats(self, days: int, placed_only: bool = True) -> dict:
        """Return aggregate P&L statistics for the last N days.

        Args:
            days: Number of days back to include (e.g. 7 for last week).
            placed_only: If True, only include is_placed=1 bets.

        Returns:
            Same dict structure as get_total_stats().
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            placed_filter = "AND is_placed = 1" if placed_only else ""
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_bets,
                    SUM(won) AS wins,
                    SUM(profit_usdt) AS total_profit_usdt,
                    SUM(amount_usdt) AS total_staked
                FROM stake_bet_outcomes
                WHERE evaluable = 1
                  AND DATE(created_at) >= ?
                {placed_filter}
                """,
                (since_date,),
            )
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "total_bets": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "total_profit_usdt": 0.0,
                    "roi_pct": 0.0,
                }

            total_bets = row[0] or 0
            wins = row[1] or 0
            total_profit = row[2] or 0.0
            total_staked = row[3] or 0.0

            win_rate = (wins / total_bets * 100.0) if total_bets > 0 else 0.0
            roi_pct = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0

            return {
                "total_bets": total_bets,
                "wins": wins,
                "win_rate": round(win_rate, 2),
                "total_profit_usdt": round(total_profit, 4),
                "roi_pct": round(roi_pct, 2),
            }
        finally:
            conn.close()
