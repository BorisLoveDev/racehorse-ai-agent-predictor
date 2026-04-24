"""Repository for per-horse calibration samples (stake_calibration_samples).

One row is written per runner in every analysed race (regardless of whether a
bet is placed) so the Phase 3 calibration weekly job can retrain without
selection-sample bias. Outcome is NULL until settlement updates it.
"""
import sqlite3
from datetime import datetime
from typing import Optional


class CalibrationSamplesRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def insert(
        self,
        *,
        race_id: str,
        horse_no: int,
        market: str,
        track: Optional[str],
        jurisdiction: Optional[str],
        p_model_raw: float,
        p_model_calibrated: float,
        p_market: float,
        placed_bet: bool,
        ts: datetime,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO stake_calibration_samples
                (race_id, horse_no, market, track, jurisdiction,
                 p_model_raw, p_model_calibrated, p_market,
                 outcome, placed_bet, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (race_id, horse_no, market, track, jurisdiction,
             p_model_raw, p_model_calibrated, p_market,
             1 if placed_bet else 0, ts.isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def set_outcome(
        self, *, race_id: str, horse_no: int, market: str, outcome: int,
    ) -> None:
        self._conn.execute(
            "UPDATE stake_calibration_samples SET outcome=? "
            "WHERE race_id=? AND horse_no=? AND market=?",
            (outcome, race_id, horse_no, market),
        )
        self._conn.commit()

    def races_pending_settlement(self) -> list[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT race_id FROM stake_calibration_samples WHERE outcome IS NULL"
        )
        return [row[0] for row in cur.fetchall()]
