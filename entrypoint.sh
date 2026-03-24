#!/bin/bash
# Run database migrations before starting service
python3 -c "
import os
db_path = os.environ.get('STAKE_DATABASE_PATH', 'races.db')

from services.stake.bankroll.migrations import run_stake_migrations
run_stake_migrations(db_path)
print(f'Stake migrations OK: {db_path}')
"

# Start the service
exec "$@"
