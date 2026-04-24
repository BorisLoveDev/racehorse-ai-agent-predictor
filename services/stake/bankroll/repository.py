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

    # ---------- Phase 1 additions ----------
    def current_balance(self) -> float:
        """Phase-1-aligned alias: returns 0.0 when not set (safer for downstream arithmetic)."""
        v = self.get_balance()
        return 0.0 if v is None else float(v)

    def peak_balance(self) -> float:
        v = self.get_peak_balance()
        return 0.0 if v is None else float(v)

    def staked_today(self) -> float:
        """Sum of confirmed bet_slips stakes for today (UTC).

        Used by Sizer to enforce daily-limit cap. Day boundary is UTC midnight
        to avoid timezone drift across server restarts.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(stake), 0.0) FROM stake_bet_slips "
                "WHERE status='confirmed' "
                "AND date(confirmed_at) = date('now')"
            ).fetchone()
            return float(row[0] or 0.0)
        finally:
            conn.close()

    def save_bet_slip(self, slip: dict) -> None:
        """Persist a Phase-1 BetSlip.model_dump() into stake_bet_slips.

        Raises sqlite3.IntegrityError on duplicate idempotency_key (invariant
        I7 defense — idempotency_key prevents double-submission).

        If the slip is inserted with status='confirmed' but no confirmed_at
        timestamp (e.g. reconstructed from a stored record or created confirmed
        in a single step), confirmed_at is backfilled to datetime('now') so
        that staked_today() can attribute it to the current UTC day.
        """
        import json
        proposed = slip["proposed"]
        sizing = proposed["sizing_params"]
        intent = proposed["intent"]
        status = slip.get("status", "draft")
        confirmed_at = slip.get("confirmed_at")
        conn = sqlite3.connect(self.db_path)
        try:
            if status == "confirmed" and not confirmed_at:
                conn.execute(
                    """
                    INSERT INTO stake_bet_slips
                        (id, race_id, user_id, market, selections, stake, confidence,
                         idempotency_key, status, mode,
                         max_loss, profit_if_win, portfolio_var_95,
                         caps_applied, sizing_params, user_edits, confirmed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        slip["id"], slip["race_id"], slip["user_id"],
                        intent["market"],
                        json.dumps(intent["selections"]),
                        float(proposed["stake"]),
                        float(intent.get("confidence", 0.0)),
                        slip.get("idempotency_key"),
                        status,
                        proposed.get("mode", "paper"),
                        float(proposed.get("max_loss", 0.0)),
                        float(proposed.get("profit_if_win", 0.0)),
                        float(proposed.get("portfolio_var_95", 0.0)),
                        json.dumps(proposed.get("caps_applied") or []),
                        json.dumps(sizing),
                        json.dumps(slip.get("user_edits")) if slip.get("user_edits") else None,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO stake_bet_slips
                        (id, race_id, user_id, market, selections, stake, confidence,
                         idempotency_key, status, mode,
                         max_loss, profit_if_win, portfolio_var_95,
                         caps_applied, sizing_params, user_edits, confirmed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slip["id"], slip["race_id"], slip["user_id"],
                        intent["market"],
                        json.dumps(intent["selections"]),
                        float(proposed["stake"]),
                        float(intent.get("confidence", 0.0)),
                        slip.get("idempotency_key"),
                        status,
                        proposed.get("mode", "paper"),
                        float(proposed.get("max_loss", 0.0)),
                        float(proposed.get("profit_if_win", 0.0)),
                        float(proposed.get("portfolio_var_95", 0.0)),
                        json.dumps(proposed.get("caps_applied") or []),
                        json.dumps(sizing),
                        json.dumps(slip.get("user_edits")) if slip.get("user_edits") else None,
                        confirmed_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_bet_slip_id_by_idempotency_key(self, idem: str) -> Optional[str]:
        """Return the slip id for a given idempotency_key, or None.

        Used by interrupt_approval on LangGraph resume: the node body re-runs
        from the top, and we need to reuse the previously persisted slip id
        rather than minting a new one (the UNIQUE constraint prevents a
        second insert, and a fresh id would point at a non-existent row).
        """
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM stake_bet_slips WHERE idempotency_key=?",
                (idem,),
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def update_bet_slip_status(
        self, slip_id: str, status: str, *, user_edits: Optional[dict] = None,
    ) -> None:
        import json
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE stake_bet_slips SET status=?, user_edits=?, "
                "confirmed_at=datetime('now') WHERE id=?",
                (status, json.dumps(user_edits) if user_edits is not None else None, slip_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_bet_slip(self, slip_id: str) -> Optional[dict]:
        """Return a BetSlip-shaped dict (with nested proposed) or None."""
        import json
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT id, race_id, user_id, market, selections, stake, confidence,
                       idempotency_key, status, mode,
                       max_loss, profit_if_win, portfolio_var_95,
                       caps_applied, sizing_params, user_edits, confirmed_at
                FROM stake_bet_slips WHERE id=?
                """,
                (slip_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        (sid, race_id, user_id, market, sel_json, stake, confidence,
         idem, status, mode, max_loss, profit_if_win, var95,
         caps_json, sizing_json, user_edits_json, confirmed_at) = row
        return {
            "id": sid, "race_id": race_id, "user_id": user_id,
            "idempotency_key": idem, "status": status,
            "stake": float(stake), "mode": mode,
            "proposed": {
                "intent": {
                    "market": market,
                    "selections": json.loads(sel_json) if sel_json else [],
                    "confidence": float(confidence or 0.0),
                    "rationale_id": "",
                    "edge_source": "paper_only",
                },
                "stake": float(stake),
                "max_loss": float(max_loss or 0.0),
                "profit_if_win": float(profit_if_win or 0.0),
                "portfolio_var_95": float(var95 or 0.0),
                "caps_applied": json.loads(caps_json) if caps_json else [],
                "sizing_params": json.loads(sizing_json) if sizing_json else {},
                "mode": mode,
            },
            "user_edits": json.loads(user_edits_json) if user_edits_json else None,
            "confirmed_at": confirmed_at,
        }

    def apply_paper_pnl(self, *, race_id: str, pnl: float) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE stake_bankroll "
                "SET balance_usdt = balance_usdt + ?, updated_at = datetime('now') "
                "WHERE id = 1",
                (float(pnl),),
            )
            conn.commit()
        finally:
            conn.close()
