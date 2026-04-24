"""Repository for AuditTrace persistence (stake_audit_traces)."""
import json
import sqlite3

from services.stake.contracts.audit import AuditTrace


class AuditTracesRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save(self, trace: AuditTrace) -> None:
        """Upsert by race_id — later saves replace earlier."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO stake_audit_traces
                (race_id, schema_version, thread_id, started_at, finished_at,
                 reproducible, steps_json, total_cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.race_id,
                trace.schema_version,
                trace.thread_id,
                trace.started_at.isoformat(),
                trace.finished_at.isoformat() if trace.finished_at else None,
                None if trace.reproducible is None else int(trace.reproducible),
                json.dumps([s.model_dump(mode="json") for s in trace.steps]),
                trace.total_cost_usd,
            ),
        )
        self._conn.commit()

    def last_n_reproducibility(self, n: int = 10) -> list[bool]:
        cur = self._conn.execute(
            "SELECT reproducible FROM stake_audit_traces "
            "WHERE finished_at IS NOT NULL "
            "ORDER BY finished_at DESC LIMIT ?",
            (n,),
        )
        return [bool(row[0]) for row in cur.fetchall() if row[0] is not None]
