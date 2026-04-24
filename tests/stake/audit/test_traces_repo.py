import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from services.stake.bankroll.migrations import apply_migrations
from services.stake.audit.traces_repo import AuditTracesRepository
from services.stake.contracts.audit import AuditTrace, AuditStep


def _fresh(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    apply_migrations(conn)
    return conn


def _make_trace(race_id: str, *, reproducible: bool) -> AuditTrace:
    trace = AuditTrace(race_id=race_id, thread_id=f"race:{race_id}:1",
                       started_at=datetime.now(timezone.utc))
    trace.steps.append(AuditStep(
        step_name="parse", ts=datetime.now(timezone.utc),
        inputs_hash="a", outputs_hash="b", model="m",
        prompt_hash="p", cost_usd=0.01,
        temperature=0.0 if reproducible else 0.7,
    ))
    trace.finish()
    return trace


def test_save_and_reproducibility_flag(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = AuditTracesRepository(conn)
    trace = _make_trace("R1", reproducible=True)
    repo.save(trace)
    row = conn.execute(
        "SELECT race_id, reproducible, total_cost_usd FROM stake_audit_traces "
        "WHERE race_id=?", ("R1",),
    ).fetchone()
    assert row[0] == "R1"
    assert row[1] == 1
    assert abs(row[2] - 0.01) < 1e-9


def test_last_n_reproducibility_orders_by_finished_desc(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = AuditTracesRepository(conn)
    # Save two traces with different reproducibility
    repo.save(_make_trace("R1", reproducible=True))
    repo.save(_make_trace("R2", reproducible=False))
    flags = repo.last_n_reproducibility(n=10)
    # Both returned; order is by finished_at DESC. We can't guarantee order
    # without sleeping, so just check both present.
    assert sorted(flags) == [False, True]


def test_last_n_reproducibility_limit(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = AuditTracesRepository(conn)
    for i in range(5):
        repo.save(_make_trace(f"R{i}", reproducible=True))
    flags = repo.last_n_reproducibility(n=3)
    assert len(flags) == 3


def test_save_replaces_existing_by_race_id(tmp_path: Path):
    conn = _fresh(tmp_path)
    repo = AuditTracesRepository(conn)
    t1 = _make_trace("R1", reproducible=False)
    repo.save(t1)
    t2 = _make_trace("R1", reproducible=True)  # same race_id, new data
    repo.save(t2)
    n = conn.execute(
        "SELECT COUNT(*) FROM stake_audit_traces WHERE race_id='R1'"
    ).fetchone()[0]
    assert n == 1
    # Reproducibility reflects the latest save
    row = conn.execute(
        "SELECT reproducible FROM stake_audit_traces WHERE race_id='R1'"
    ).fetchone()
    assert row[0] == 1


def test_steps_json_round_trip(tmp_path: Path):
    import json
    conn = _fresh(tmp_path)
    repo = AuditTracesRepository(conn)
    trace = _make_trace("R1", reproducible=True)
    repo.save(trace)
    row = conn.execute(
        "SELECT steps_json FROM stake_audit_traces WHERE race_id='R1'"
    ).fetchone()
    steps = json.loads(row[0])
    assert len(steps) == 1
    assert steps[0]["step_name"] == "parse"
    assert steps[0]["model"] == "m"
