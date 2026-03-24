#!/bin/bash
# Run database migrations before starting service
python3 -c "
from src.database.migrations import run_migrations, initialize_default_agents
import os
db_path = os.environ.get('RACEHORSE_DATABASE__PATH', os.environ.get('STAKE_DATABASE_PATH', 'races.db'))
run_migrations(db_path)
initialize_default_agents(db_path)
# Stake-specific migrations
try:
    from services.stake.bankroll.migrations import run_stake_migrations
    run_stake_migrations(db_path)
except ImportError:
    pass  # Not all services need stake migrations
"

# Start the service
exec "$@"
