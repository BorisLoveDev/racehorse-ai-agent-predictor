"""
Database migrations for the Stake Advisor Bot.
Creates stake-specific tables in the shared SQLite database.

Phase 1 adds:
- stake_calibration_samples: per-runner probability calibration log
- stake_audit_traces: per-race pipeline audit trail
- stake_bet_slips: pre-race approved/confirmed bet intents (distinct from stake_bet_outcomes)
- stake_lessons extensions: pnl_track, evidence_bet_ids, status, confidence, tag,
  lesson_id (UUID), condition, action
"""

import sqlite3


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all stake migrations to the given open connection.

    Idempotent: can be called multiple times without error.
    Commits on success, rolls back + raises RuntimeError on failure.
    """
    try:
        cursor = conn.cursor()

        # ------------------------------------------------------------------
        # Existing (pre-Phase 1) tables — mirror of run_stake_migrations
        # ------------------------------------------------------------------

        # Singleton bankroll table — CHECK (id = 1) enforces only one row.
        # ON CONFLICT ... DO UPDATE is used for upsert in the repository.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_bankroll (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance_usdt REAL NOT NULL,
                stake_pct REAL NOT NULL DEFAULT 0.02,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Pipeline run log — each paste the user sends creates one run.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_pipeline_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_input TEXT NOT NULL,
                parsed_race_json TEXT,
                user_confirmed INTEGER DEFAULT 0,
                user_changes_json TEXT,
                bankroll_at_run REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Phase 3 (pre-existing): stake_bet_outcomes — one row per evaluated bet.
        # Note: distinct from stake_bet_slips (below). Outcomes = post-race eval;
        # slips = pre-race approved intent.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_bet_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                is_placed INTEGER NOT NULL DEFAULT 0,
                runner_name TEXT NOT NULL,
                runner_number INTEGER,
                bet_type TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                decimal_odds REAL,
                place_odds REAL,
                won INTEGER NOT NULL DEFAULT 0,
                profit_usdt REAL NOT NULL,
                evaluable INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Phase 3 (pre-existing): stake_lessons — extracted rules from post-race reflection
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_tag TEXT NOT NULL,
                rule_sentence TEXT NOT NULL,
                is_failure INTEGER NOT NULL DEFAULT 0,
                application_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Phase 3 (pre-existing): peak_balance_usdt and drawdown_unlocked on stake_bankroll.
        cursor.execute("PRAGMA table_info(stake_bankroll)")
        cols = [row[1] for row in cursor.fetchall()]
        if "peak_balance_usdt" not in cols:
            cursor.execute("ALTER TABLE stake_bankroll ADD COLUMN peak_balance_usdt REAL")
        if "drawdown_unlocked" not in cols:
            cursor.execute("ALTER TABLE stake_bankroll ADD COLUMN drawdown_unlocked INTEGER DEFAULT 0")

        # Hotfix: message_id + chat_id + user_id on stake_pipeline_runs so
        # reply-to-message routing can map a Telegram reply to the original
        # recommendation run. Idempotent PRAGMA+ALTER pattern.
        cursor.execute("PRAGMA table_info(stake_pipeline_runs)")
        cols = [row[1] for row in cursor.fetchall()]
        if "message_id" not in cols:
            cursor.execute("ALTER TABLE stake_pipeline_runs ADD COLUMN message_id INTEGER")
        if "chat_id" not in cols:
            cursor.execute("ALTER TABLE stake_pipeline_runs ADD COLUMN chat_id INTEGER")
        if "user_id" not in cols:
            cursor.execute("ALTER TABLE stake_pipeline_runs ADD COLUMN user_id INTEGER")
        if "result_positions" not in cols:
            cursor.execute("ALTER TABLE stake_pipeline_runs ADD COLUMN result_positions TEXT")
        if "result_reported_at" not in cols:
            cursor.execute("ALTER TABLE stake_pipeline_runs ADD COLUMN result_reported_at TEXT")

        # ------------------------------------------------------------------
        # Phase 1 new tables
        # ------------------------------------------------------------------

        # Probability calibration samples: one row per runner per race
        # whose probability was scored (whether we bet or not).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_calibration_samples (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id      TEXT    NOT NULL,
                horse_no     INTEGER NOT NULL,
                market       TEXT    NOT NULL,
                track        TEXT,
                jurisdiction TEXT,
                p_model_raw        REAL NOT NULL,
                p_model_calibrated REAL NOT NULL,
                p_market     REAL NOT NULL,
                outcome      INTEGER,
                placed_bet   INTEGER NOT NULL,
                ts           TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sample_race "
            "ON stake_calibration_samples(race_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sample_market_track "
            "ON stake_calibration_samples(market, track)"
        )

        # Audit traces: one row per race-pipeline invocation.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_audit_traces (
                race_id        TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                thread_id      TEXT NOT NULL,
                started_at     TEXT NOT NULL,
                finished_at    TEXT,
                reproducible   INTEGER,
                steps_json     TEXT NOT NULL,
                total_cost_usd REAL NOT NULL DEFAULT 0.0
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_finished "
            "ON stake_audit_traces(finished_at)"
        )

        # Bet slips: pre-race approved/confirmed intents.
        # Intentionally separate from stake_bet_outcomes (post-race eval);
        # Phase 3 may unify, Phase 1 keeps separate.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stake_bet_slips (
                id              TEXT PRIMARY KEY,
                race_id         TEXT NOT NULL,
                user_id         INTEGER NOT NULL,
                market          TEXT NOT NULL,
                selections      TEXT NOT NULL,
                stake           REAL NOT NULL,
                confidence      REAL,
                idempotency_key TEXT UNIQUE,
                status          TEXT NOT NULL DEFAULT 'draft',
                mode            TEXT NOT NULL DEFAULT 'paper',
                max_loss          REAL,
                profit_if_win     REAL,
                portfolio_var_95  REAL,
                caps_applied      TEXT,
                sizing_params     TEXT,
                user_edits        TEXT,
                confirmed_at      TEXT,
                created_at        TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bs_race ON stake_bet_slips(race_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bs_status ON stake_bet_slips(status)"
        )

        # ------------------------------------------------------------------
        # Phase 1 extensions to stake_lessons (idempotent ADD COLUMN)
        # ------------------------------------------------------------------
        cursor.execute("PRAGMA table_info(stake_lessons)")
        lesson_cols = [row[1] for row in cursor.fetchall()]
        lesson_additions = [
            # JSON: applied_count/realized_pnl/roi/last_applied_at
            ("pnl_track", "TEXT"),
            # JSON array of bet_slip ids
            ("evidence_bet_ids", "TEXT"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("confidence", "REAL NOT NULL DEFAULT 0.5"),
            ("tag", "TEXT"),
            # UUID, distinct from autoincrement primary key `id`
            ("lesson_id", "TEXT"),
            # Contract fields from Lesson Pydantic model
            ("condition", "TEXT"),
            ("action", "TEXT"),
        ]
        for col_name, col_sql in lesson_additions:
            if col_name not in lesson_cols:
                cursor.execute(
                    f"ALTER TABLE stake_lessons ADD COLUMN {col_name} {col_sql}"
                )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Stake migrations failed: {e}") from e


def run_stake_migrations(db_path: str = "races.db") -> None:
    """Run all Stake service database migrations against ``db_path``.

    Opens its own connection. For test scenarios that need to apply
    migrations to an already-open connection, use :func:`apply_migrations`.

    Args:
        db_path: Path to SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
