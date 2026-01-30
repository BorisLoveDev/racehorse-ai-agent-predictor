"""
Database access layer for the betting agent system.
Provides clean interface for storing and retrieving predictions and outcomes.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from ..models.bets import StructuredBetOutput


class AgentRepository:
    """Repository for agent data."""

    def __init__(self, db_path: str = "races.db"):
        self.db_path = db_path

    def get_agent_id(self, agent_name: str) -> Optional[int]:
        """Get agent ID by name."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT agent_id FROM agents WHERE agent_name = ?",
                (agent_name,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    def get_agent_info(self, agent_id: int) -> Optional[dict]:
        """Get agent information by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT agent_id, agent_name, model_id, provider, config_json "
                "FROM agents WHERE agent_id = ?",
                (agent_id,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    "agent_id": result[0],
                    "agent_name": result[1],
                    "model_id": result[2],
                    "provider": result[3],
                    "config": json.loads(result[4]) if result[4] else {}
                }
            return None
        finally:
            conn.close()


class PredictionRepository:
    """Repository for predictions data."""

    def __init__(self, db_path: str = "races.db"):
        self.db_path = db_path

    def save_prediction(
        self,
        agent_name: str,
        race_id: int,
        structured_bet: StructuredBetOutput,
        race_start_time: Optional[str] = None,
        odds_snapshot_json: Optional[str] = None
    ) -> int:
        """
        Save a prediction to the database.
        Returns the prediction_id.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get agent_id
            cursor.execute(
                "SELECT agent_id FROM agents WHERE agent_name = ?",
                (agent_name,)
            )
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Agent '{agent_name}' not found in database")
            agent_id = result[0]

            # Insert prediction
            cursor.execute("""
                INSERT INTO predictions (
                    race_id, agent_id, race_url, race_location, race_number,
                    race_start_time, analysis_summary, confidence_score,
                    risk_level, key_factors, structured_bet_json, odds_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                agent_id,
                structured_bet.race_url,
                structured_bet.race_location,
                structured_bet.race_number,
                race_start_time,
                structured_bet.analysis_summary,
                structured_bet.confidence_score,
                structured_bet.risk_level,
                json.dumps(structured_bet.key_factors),
                structured_bet.model_dump_json(),
                odds_snapshot_json
            ))

            prediction_id = cursor.lastrowid
            conn.commit()
            return prediction_id

        finally:
            conn.close()

    def get_prediction(self, prediction_id: int) -> Optional[dict]:
        """Get a prediction by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT prediction_id, race_id, agent_id, race_url,
                       race_location, race_number, race_start_time,
                       analysis_summary, confidence_score, risk_level,
                       key_factors, structured_bet_json, odds_snapshot_json, created_at
                FROM predictions WHERE prediction_id = ?
            """, (prediction_id,))
            result = cursor.fetchone()

            if result:
                return {
                    "prediction_id": result[0],
                    "race_id": result[1],
                    "agent_id": result[2],
                    "race_url": result[3],
                    "race_location": result[4],
                    "race_number": result[5],
                    "race_start_time": result[6],
                    "analysis_summary": result[7],
                    "confidence_score": result[8],
                    "risk_level": result[9],
                    "key_factors": json.loads(result[10]) if result[10] else [],
                    "structured_bet": json.loads(result[11]),
                    "odds_snapshot": json.loads(result[12]) if result[12] else {},
                    "created_at": result[13]
                }
            return None
        finally:
            conn.close()

    def update_telegram_message_id(self, prediction_id: int, message_id: int) -> None:
        """Update the Telegram message ID for a prediction (for reply-to)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE predictions SET telegram_message_id = ? WHERE prediction_id = ?",
                (message_id, prediction_id)
            )
            conn.commit()
        finally:
            conn.close()

    def get_telegram_message_id(self, prediction_id: int) -> Optional[int]:
        """Get the Telegram message ID for a prediction."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT telegram_message_id FROM predictions WHERE prediction_id = ?",
                (prediction_id,)
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
        finally:
            conn.close()

    def get_predictions_for_race(self, race_url: str) -> list[dict]:
        """Get all predictions for a specific race."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT p.prediction_id, p.race_id, p.agent_id, a.agent_name,
                       p.race_url, p.race_location, p.race_number,
                       p.analysis_summary, p.confidence_score, p.risk_level,
                       p.structured_bet_json, p.odds_snapshot_json, p.created_at
                FROM predictions p
                JOIN agents a ON p.agent_id = a.agent_id
                WHERE p.race_url = ?
                ORDER BY p.created_at DESC
            """, (race_url,))
            results = cursor.fetchall()

            predictions = []
            for row in results:
                predictions.append({
                    "prediction_id": row[0],
                    "race_id": row[1],
                    "agent_id": row[2],
                    "agent_name": row[3],
                    "race_url": row[4],
                    "race_location": row[5],
                    "race_number": row[6],
                    "analysis_summary": row[7],
                    "confidence_score": row[8],
                    "risk_level": row[9],
                    "structured_bet": json.loads(row[10]),
                    "odds_snapshot": json.loads(row[11]) if row[11] else {},
                    "created_at": row[12]
                })
            return predictions
        finally:
            conn.close()


class OutcomeRepository:
    """Repository for prediction outcomes."""

    def __init__(self, db_path: str = "races.db"):
        self.db_path = db_path

    def save_outcome(
        self,
        prediction_id: int,
        finishing_order: list[dict],
        dividends: dict,
        bet_results: dict[str, bool],
        payouts: dict[str, float],
        total_bet_amount: float,
        actual_dividends_json: Optional[str] = None
    ) -> int:
        """
        Save prediction outcome after race finishes.
        Returns the outcome_id.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            total_payout = sum(payouts.values())
            net_profit_loss = total_payout - total_bet_amount

            cursor.execute("""
                INSERT INTO prediction_outcomes (
                    prediction_id, race_finished_at, finishing_order,
                    dividends_json, win_result, place_result, exacta_result,
                    quinella_result, trifecta_result, first4_result, qps_result,
                    win_payout, place_payout, exacta_payout, quinella_payout,
                    trifecta_payout, first4_payout, qps_payout,
                    total_bet_amount, total_payout, net_profit_loss, actual_dividends_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prediction_id,
                datetime.utcnow().isoformat(),
                json.dumps(finishing_order),
                json.dumps(dividends),
                1 if bet_results.get("win") else 0 if "win" in bet_results else None,
                1 if bet_results.get("place") else 0 if "place" in bet_results else None,
                1 if bet_results.get("exacta") else 0 if "exacta" in bet_results else None,
                1 if bet_results.get("quinella") else 0 if "quinella" in bet_results else None,
                1 if bet_results.get("trifecta") else 0 if "trifecta" in bet_results else None,
                1 if bet_results.get("first4") else 0 if "first4" in bet_results else None,
                1 if bet_results.get("qps") else 0 if "qps" in bet_results else None,
                payouts.get("win", 0.0),
                payouts.get("place", 0.0),
                payouts.get("exacta", 0.0),
                payouts.get("quinella", 0.0),
                payouts.get("trifecta", 0.0),
                payouts.get("first4", 0.0),
                payouts.get("qps", 0.0),
                total_bet_amount,
                total_payout,
                net_profit_loss,
                actual_dividends_json
            ))

            outcome_id = cursor.lastrowid
            conn.commit()

            # Update agent statistics
            self._update_agent_statistics(cursor, prediction_id, bet_results, payouts, total_bet_amount, total_payout, net_profit_loss)
            conn.commit()

            return outcome_id

        finally:
            conn.close()

    def _update_agent_statistics(
        self,
        cursor: sqlite3.Cursor,
        prediction_id: int,
        bet_results: dict[str, bool],
        payouts: dict[str, float],
        total_bet_amount: float,
        total_payout: float,
        net_profit_loss: float
    ) -> None:
        """Update agent statistics after recording an outcome."""
        # Get agent_id from prediction
        cursor.execute(
            "SELECT agent_id FROM predictions WHERE prediction_id = ?",
            (prediction_id,)
        )
        result = cursor.fetchone()
        if not result:
            return
        agent_id = result[0]

        # Count total wins and losses
        total_bets = len(bet_results)
        total_wins = sum(1 for won in bet_results.values() if won)
        total_losses = total_bets - total_wins

        # Update statistics
        cursor.execute("""
            UPDATE agent_statistics
            SET total_predictions = total_predictions + 1,
                total_bets = total_bets + ?,
                total_wins = total_wins + ?,
                total_losses = total_losses + ?,
                total_bet_amount = total_bet_amount + ?,
                total_payout = total_payout + ?,
                net_profit_loss = net_profit_loss + ?,
                roi_percentage = CASE
                    WHEN (total_bet_amount + ?) > 0
                    THEN ((total_payout + ? - total_bet_amount - ?) / (total_bet_amount + ?)) * 100
                    ELSE 0
                END,
                win_bets_placed = win_bets_placed + ?,
                win_bets_won = win_bets_won + ?,
                place_bets_placed = place_bets_placed + ?,
                place_bets_won = place_bets_won + ?,
                exacta_bets_placed = exacta_bets_placed + ?,
                exacta_bets_won = exacta_bets_won + ?,
                quinella_bets_placed = quinella_bets_placed + ?,
                quinella_bets_won = quinella_bets_won + ?,
                trifecta_bets_placed = trifecta_bets_placed + ?,
                trifecta_bets_won = trifecta_bets_won + ?,
                first4_bets_placed = first4_bets_placed + ?,
                first4_bets_won = first4_bets_won + ?,
                qps_bets_placed = qps_bets_placed + ?,
                qps_bets_won = qps_bets_won + ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE agent_id = ?
        """, (
            total_bets, total_wins, total_losses,
            total_bet_amount, total_payout, net_profit_loss,
            total_bet_amount, total_payout, total_bet_amount, total_bet_amount,
            1 if "win" in bet_results else 0,
            1 if bet_results.get("win") else 0,
            1 if "place" in bet_results else 0,
            1 if bet_results.get("place") else 0,
            1 if "exacta" in bet_results else 0,
            1 if bet_results.get("exacta") else 0,
            1 if "quinella" in bet_results else 0,
            1 if bet_results.get("quinella") else 0,
            1 if "trifecta" in bet_results else 0,
            1 if bet_results.get("trifecta") else 0,
            1 if "first4" in bet_results else 0,
            1 if bet_results.get("first4") else 0,
            1 if "qps" in bet_results else 0,
            1 if bet_results.get("qps") else 0,
            agent_id
        ))

    def get_outcome(self, prediction_id: int) -> Optional[dict]:
        """Get outcome for a specific prediction."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT outcome_id, prediction_id, race_finished_at,
                       finishing_order, dividends_json, win_result,
                       place_result, exacta_result, quinella_result,
                       trifecta_result, first4_result, qps_result,
                       win_payout, place_payout, exacta_payout,
                       quinella_payout, trifecta_payout, first4_payout,
                       qps_payout, total_bet_amount, total_payout,
                       net_profit_loss, evaluated_at, actual_dividends_json
                FROM prediction_outcomes
                WHERE prediction_id = ?
            """, (prediction_id,))
            result = cursor.fetchone()

            if result:
                return {
                    "outcome_id": result[0],
                    "prediction_id": result[1],
                    "race_finished_at": result[2],
                    "finishing_order": json.loads(result[3]) if result[3] else [],
                    "dividends": json.loads(result[4]) if result[4] else {},
                    "bet_results": {
                        "win": result[5] == 1 if result[5] is not None else None,
                        "place": result[6] == 1 if result[6] is not None else None,
                        "exacta": result[7] == 1 if result[7] is not None else None,
                        "quinella": result[8] == 1 if result[8] is not None else None,
                        "trifecta": result[9] == 1 if result[9] is not None else None,
                        "first4": result[10] == 1 if result[10] is not None else None,
                        "qps": result[11] == 1 if result[11] is not None else None,
                    },
                    "payouts": {
                        "win": result[12],
                        "place": result[13],
                        "exacta": result[14],
                        "quinella": result[15],
                        "trifecta": result[16],
                        "first4": result[17],
                        "qps": result[18],
                    },
                    "total_bet_amount": result[19],
                    "total_payout": result[20],
                    "net_profit_loss": result[21],
                    "evaluated_at": result[22],
                    "actual_dividends": json.loads(result[23]) if result[23] else {}
                }
            return None
        finally:
            conn.close()


class StatisticsRepository:
    """Repository for agent statistics."""

    def __init__(self, db_path: str = "races.db"):
        self.db_path = db_path

    def get_agent_statistics(self, agent_name: str) -> Optional[dict]:
        """Get statistics for a specific agent."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT s.* FROM agent_statistics s
                JOIN agents a ON s.agent_id = a.agent_id
                WHERE a.agent_name = ?
            """, (agent_name,))
            result = cursor.fetchone()

            if result:
                return {
                    "agent_id": result[1],
                    "total_predictions": result[2],
                    "total_bets": result[3],
                    "total_wins": result[4],
                    "total_losses": result[5],
                    "total_bet_amount": result[6],
                    "total_payout": result[7],
                    "net_profit_loss": result[8],
                    "roi_percentage": result[9],
                    "win_bets": {"placed": result[10], "won": result[11]},
                    "place_bets": {"placed": result[12], "won": result[13]},
                    "exacta_bets": {"placed": result[14], "won": result[15]},
                    "quinella_bets": {"placed": result[16], "won": result[17]},
                    "trifecta_bets": {"placed": result[18], "won": result[19]},
                    "first4_bets": {"placed": result[20], "won": result[21]},
                    "qps_bets": {"placed": result[22], "won": result[23]},
                    "last_updated": result[24]
                }
            return None
        finally:
            conn.close()

    def get_all_statistics(self) -> list[dict]:
        """Get statistics for all agents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT a.agent_name, s.* FROM agent_statistics s
                JOIN agents a ON s.agent_id = a.agent_id
                ORDER BY s.roi_percentage DESC
            """)
            results = cursor.fetchall()

            statistics = []
            for row in results:
                statistics.append({
                    "agent_name": row[0],
                    "agent_id": row[2],
                    "total_predictions": row[3],
                    "total_bets": row[4],
                    "total_wins": row[5],
                    "total_losses": row[6],
                    "total_bet_amount": row[7],
                    "total_payout": row[8],
                    "net_profit_loss": row[9],
                    "roi_percentage": row[10],
                    "last_updated": row[25]
                })
            return statistics
        finally:
            conn.close()

    def _get_date_filter(self, period: str) -> tuple[str, list]:
        """Return SQL WHERE clause and params for period."""
        now = datetime.utcnow()
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "3d":
            start = now - timedelta(days=3)
        elif period == "week":
            start = now - timedelta(days=7)
        else:  # "all"
            return "", []

        return "AND po.evaluated_at >= ?", [start.isoformat()]

    def get_statistics_for_period(self, period: str = "all") -> list[dict]:
        """Get agent statistics for specified period."""
        where_clause, params = self._get_date_filter(period)

        query = f"""
            SELECT
                a.agent_name,
                COUNT(DISTINCT p.prediction_id) as total_predictions,
                COUNT(po.outcome_id) as total_bets,
                SUM(CASE WHEN po.net_profit_loss > 0 THEN 1 ELSE 0 END) as total_wins,
                SUM(CASE WHEN po.net_profit_loss <= 0 THEN 1 ELSE 0 END) as total_losses,
                SUM(po.total_bet_amount) as total_bet_amount,
                SUM(po.total_payout) as total_payout,
                SUM(po.net_profit_loss) as net_profit_loss
            FROM agents a
            LEFT JOIN predictions p ON a.agent_id = p.agent_id
            LEFT JOIN prediction_outcomes po ON p.prediction_id = po.prediction_id
            WHERE 1=1 {where_clause}
            GROUP BY a.agent_id
        """

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()

            statistics = []
            for row in results:
                statistics.append({
                    "agent_name": row[0],
                    "total_predictions": row[1] or 0,
                    "total_bets": row[2] or 0,
                    "total_wins": row[3] or 0,
                    "total_losses": row[4] or 0,
                    "total_bet_amount": row[5] or 0.0,
                    "total_payout": row[6] or 0.0,
                    "net_profit_loss": row[7] or 0.0
                })
            return statistics
        finally:
            conn.close()

    def get_pl_chart_data(self, period: str = "all") -> list[dict]:
        """Get P/L data points for chart generation."""
        where_clause, params = self._get_date_filter(period)

        query = f"""
            SELECT
                a.agent_name,
                p.race_start_time,
                po.net_profit_loss,
                SUM(po.net_profit_loss) OVER (
                    PARTITION BY a.agent_id
                    ORDER BY p.race_start_time
                ) as cumulative_pl
            FROM agents a
            JOIN predictions p ON a.agent_id = p.agent_id
            JOIN prediction_outcomes po ON p.prediction_id = po.prediction_id
            WHERE po.evaluated_at IS NOT NULL {where_clause}
            ORDER BY p.race_start_time
        """

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()

            chart_data = []
            for row in results:
                chart_data.append({
                    "agent": row[0],
                    "race_time": datetime.fromisoformat(row[1]) if row[1] else datetime.utcnow(),
                    "net_profit_loss": row[2],
                    "cumulative_pl": row[3]
                })
            return chart_data
        finally:
            conn.close()

    def get_pending_predictions(self) -> list[dict]:
        """Get predictions without outcomes (active bets)."""
        query = """
            SELECT p.*, a.agent_name
            FROM predictions p
            JOIN agents a ON p.agent_id = a.agent_id
            LEFT JOIN prediction_outcomes po ON p.prediction_id = po.prediction_id
            WHERE po.outcome_id IS NULL
            ORDER BY p.race_start_time
        """

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            results = cursor.fetchall()

            predictions = []
            for row in results:
                predictions.append({
                    "prediction_id": row[0],
                    "race_id": row[1],
                    "agent_id": row[2],
                    "race_url": row[3],
                    "race_location": row[4],
                    "race_number": row[5],
                    "race_start_time": row[6],
                    "agent_name": row[-1],
                    "structured_bet": json.loads(row[10])
                })
            return predictions
        finally:
            conn.close()

    def get_recent_outcomes(self, limit: int = 5) -> list[dict]:
        """Get most recent outcomes with prediction details."""
        query = """
            SELECT po.*, p.race_location, p.race_number, a.agent_name, p.structured_bet_json
            FROM prediction_outcomes po
            JOIN predictions p ON po.prediction_id = p.prediction_id
            JOIN agents a ON p.agent_id = a.agent_id
            ORDER BY po.evaluated_at DESC
            LIMIT ?
        """

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            outcomes = []
            for row in results:
                outcomes.append({
                    "outcome_id": row[0],
                    "prediction_id": row[1],
                    "race_location": row[-4],
                    "race_number": row[-3],
                    "agent_name": row[-2],
                    "total_bet_amount": row[19],
                    "total_payout": row[20],
                    "net_profit_loss": row[21],
                    "evaluated_at": row[22],
                    "structured_bet": json.loads(row[-1])
                })
            return outcomes
        finally:
            conn.close()
