"""
Database migrations for the Stake Advisor Bot.
Creates stake-specific tables in the shared SQLite database.
"""

import sqlite3


def run_stake_migrations(db_path: str = "races.db") -> None:
    """Run all Stake service database migrations.

    Creates:
    - stake_bankroll: Singleton row for bankroll state (balance + stake_pct)
    - stake_pipeline_runs: Log of each pipeline invocation

    Args:
        db_path: Path to SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
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

        # Phase 3: stake_bet_outcomes — one row per evaluated bet
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

        # Phase 3: stake_lessons — extracted rules from post-race reflection
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

        # Phase 3: peak_balance_usdt and drawdown_unlocked columns on stake_bankroll.
        # ALTER TABLE is not idempotent, so check column existence first.
        cursor.execute("PRAGMA table_info(stake_bankroll)")
        cols = [row[1] for row in cursor.fetchall()]
        if "peak_balance_usdt" not in cols:
            cursor.execute("ALTER TABLE stake_bankroll ADD COLUMN peak_balance_usdt REAL")
        if "drawdown_unlocked" not in cols:
            cursor.execute("ALTER TABLE stake_bankroll ADD COLUMN drawdown_unlocked INTEGER DEFAULT 0")

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Stake migrations failed: {e}") from e
    finally:
        conn.close()
