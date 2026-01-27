"""
Database migrations for the betting agent system.
Extends the existing races.db schema with new tables.
"""

import sqlite3
from pathlib import Path


def add_odds_columns(cursor: sqlite3.Cursor) -> None:
    """Add odds_snapshot_json and actual_dividends_json columns if they don't exist."""
    # Check if odds_snapshot_json exists in predictions table
    cursor.execute("PRAGMA table_info(predictions)")
    columns = [row[1] for row in cursor.fetchall()]

    if "odds_snapshot_json" not in columns:
        cursor.execute("""
            ALTER TABLE predictions
            ADD COLUMN odds_snapshot_json TEXT
        """)
        print("  ✓ Added odds_snapshot_json to predictions table")

    # Check if actual_dividends_json exists in prediction_outcomes table
    cursor.execute("PRAGMA table_info(prediction_outcomes)")
    columns = [row[1] for row in cursor.fetchall()]

    if "actual_dividends_json" not in columns:
        cursor.execute("""
            ALTER TABLE prediction_outcomes
            ADD COLUMN actual_dividends_json TEXT
        """)
        print("  ✓ Added actual_dividends_json to prediction_outcomes table")


def run_migrations(db_path: str = "races.db") -> None:
    """Run all database migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL UNIQUE,
                model_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                config_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                agent_id INTEGER NOT NULL,
                race_url TEXT NOT NULL,
                race_location TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                race_start_time TEXT,

                -- Analysis fields
                analysis_summary TEXT,
                confidence_score REAL,
                risk_level TEXT,
                key_factors TEXT,

                -- Structured bet JSON
                structured_bet_json TEXT NOT NULL,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
        """)

        # Create prediction_outcomes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER NOT NULL,

                -- Race result info
                race_finished_at TIMESTAMP,
                finishing_order TEXT,
                dividends_json TEXT,

                -- Bet outcomes (1=won, 0=lost, NULL=pending)
                win_result INTEGER,
                place_result INTEGER,
                exacta_result INTEGER,
                quinella_result INTEGER,
                trifecta_result INTEGER,
                first4_result INTEGER,
                qps_result INTEGER,

                -- Payouts (if won)
                win_payout REAL DEFAULT 0.0,
                place_payout REAL DEFAULT 0.0,
                exacta_payout REAL DEFAULT 0.0,
                quinella_payout REAL DEFAULT 0.0,
                trifecta_payout REAL DEFAULT 0.0,
                first4_payout REAL DEFAULT 0.0,
                qps_payout REAL DEFAULT 0.0,

                -- Total profit/loss for this prediction
                total_bet_amount REAL NOT NULL,
                total_payout REAL DEFAULT 0.0,
                net_profit_loss REAL DEFAULT 0.0,

                -- Timestamps
                evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
            )
        """)

        # Create agent_statistics table (aggregated stats)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_statistics (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,

                -- Overall statistics
                total_predictions INTEGER DEFAULT 0,
                total_bets INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,

                -- Financial statistics
                total_bet_amount REAL DEFAULT 0.0,
                total_payout REAL DEFAULT 0.0,
                net_profit_loss REAL DEFAULT 0.0,
                roi_percentage REAL DEFAULT 0.0,

                -- Bet type breakdown
                win_bets_placed INTEGER DEFAULT 0,
                win_bets_won INTEGER DEFAULT 0,
                place_bets_placed INTEGER DEFAULT 0,
                place_bets_won INTEGER DEFAULT 0,
                exacta_bets_placed INTEGER DEFAULT 0,
                exacta_bets_won INTEGER DEFAULT 0,
                quinella_bets_placed INTEGER DEFAULT 0,
                quinella_bets_won INTEGER DEFAULT 0,
                trifecta_bets_placed INTEGER DEFAULT 0,
                trifecta_bets_won INTEGER DEFAULT 0,
                first4_bets_placed INTEGER DEFAULT 0,
                first4_bets_won INTEGER DEFAULT 0,
                qps_bets_placed INTEGER DEFAULT 0,
                qps_bets_won INTEGER DEFAULT 0,

                -- Timestamps
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
                UNIQUE(agent_id)
            )
        """)

        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_race_id
            ON predictions(race_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_agent_id
            ON predictions(agent_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_race_url
            ON predictions(race_url)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_prediction_id
            ON prediction_outcomes(prediction_id)
        """)

        # Add new columns for odds and dividends (Stage 1)
        add_odds_columns(cursor)

        conn.commit()
        print("✓ Database migrations completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


def initialize_default_agents(db_path: str = "races.db") -> None:
    """Initialize default AI agents in the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Insert Gemini agent
        cursor.execute("""
            INSERT OR IGNORE INTO agents (agent_name, model_id, provider, config_json)
            VALUES (?, ?, ?, ?)
        """, (
            "gemini",
            "google/gemini-3-flash-preview",
            "openrouter",
            '{"temperature": 0.7, "max_tokens": 16928}'
        ))

        # Insert Grok agent
        cursor.execute("""
            INSERT OR IGNORE INTO agents (agent_name, model_id, provider, config_json)
            VALUES (?, ?, ?, ?)
        """, (
            "grok",
            "x-ai/grok-4.1-fast",
            "openrouter",
            '{"temperature": 0.7, "max_tokens": 16928, "reasoning_effort": "high"}'
        ))

        # Initialize statistics for both agents
        cursor.execute("""
            INSERT OR IGNORE INTO agent_statistics (agent_id)
            SELECT agent_id FROM agents WHERE agent_name IN ('gemini', 'grok')
        """)

        conn.commit()
        print("✓ Default agents initialized")

    except Exception as e:
        conn.rollback()
        print(f"✗ Failed to initialize agents: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    """Run migrations when executed directly."""
    run_migrations()
    initialize_default_agents()
