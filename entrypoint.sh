#!/bin/bash
# Run database migrations before starting service
python3 -c "
from src.database.migrations import run_migrations, initialize_default_agents
import os
db_path = os.environ.get('RACEHORSE_DATABASE__PATH', 'races.db')
run_migrations(db_path)
initialize_default_agents(db_path)
"

# Start the service
exec "$@"
