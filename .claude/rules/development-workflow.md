# Development Workflow

## Before Making Changes

1. Always activate virtual environment: `source venv/bin/activate`
2. Check current git status: `git status`
3. Pull latest changes: `git pull origin main`

## Code Changes

1. Run tests locally before committing
2. For service changes, test with: `python test_agent.py --url <race_url> --agent both`
3. For scraper changes, test with: `python show_next_races.py` and `python show_race_details.py`

## After Making Changes

1. Commit changes with descriptive message
2. For microservices changes:
   - Rebuild base image: `docker build -f Dockerfile.base -t racehorse-base:latest .`
   - Restart services: `docker compose down && docker compose up -d`
   - Check logs: `docker compose logs -f <service_name>`

## Testing Docker Services

```bash
# Check Redis connectivity
docker compose exec redis redis-cli ping

# Monitor Redis pub/sub
docker compose exec redis redis-cli MONITOR

# View service logs
docker compose logs -f monitor
docker compose logs -f orchestrator
docker compose logs -f results
docker compose logs -f telegram
```

## Database Operations

```bash
# Access database
sqlite3 races.db

# Common queries
SELECT * FROM agents;
SELECT * FROM predictions ORDER BY created_at DESC LIMIT 10;
SELECT * FROM prediction_outcomes ORDER BY created_at DESC LIMIT 10;
```
