# Debugging Guide

## Common Issues

### No Predictions Being Created

**Symptoms**: Orchestrator receives messages but no predictions in database

**Check**:
1. Verify OPENROUTER_API_KEY is set: `docker compose exec orchestrator env | grep OPENROUTER`
2. Check orchestrator logs: `docker compose logs orchestrator | tail -50`
3. Test agent manually: `python test_agent.py --url <race_url> --agent gemini`

**Common causes**:
- Invalid API key
- Rate limiting from OpenRouter
- Malformed race data
- Network connectivity issues

### Results Not Being Evaluated

**Symptoms**: Predictions created but no outcomes in database

**Check**:
1. Verify result checks are scheduled: `docker compose logs monitor | grep schedule_result_check`
2. Check results service: `docker compose logs results | tail -50`
3. Verify race timing: Check if race has finished and results are available

**Common causes**:
- Race start time not parsed correctly (check `race.start_time_parsed`)
- TabTouch results not yet available (system retries automatically)
- Results service crashed (check logs for exceptions)

### Services Not Receiving Messages

**Symptoms**: Publisher sends but subscriber never receives

**Check**:
1. Verify Redis is healthy: `docker compose logs redis | tail -20`
2. Monitor pub/sub: `docker compose exec redis redis-cli MONITOR`
3. Check service connections: `docker compose ps`

**Common causes**:
- Redis not running
- Network issues between containers
- Service crashed before subscribing
- Channel name mismatch

### Scraper Failures

**Symptoms**: TabTouchParser raises exceptions

**Check**:
1. Test manually: `python show_next_races.py`
2. Check Playwright browser: `docker compose logs monitor | grep playwright`
3. Verify TabTouch site is accessible

**Common causes**:
- TabTouch site structure changed
- Browser not installed in container
- Network timeout
- Cloudflare blocking

## Debugging Commands

### Check Service Health

```bash
# All services status
docker compose ps

# View logs for specific service
docker compose logs -f <service_name>

# Restart specific service
docker compose restart <service_name>

# Check resource usage
docker stats
```

### Database Inspection

```bash
# Open database
sqlite3 races.db

# Check recent predictions
SELECT agent_name, confidence_score, created_at
FROM predictions
ORDER BY created_at DESC
LIMIT 10;

# Check outcomes
SELECT agent_name, win_loss, profit_loss
FROM prediction_outcomes
ORDER BY created_at DESC
LIMIT 10;

# Agent performance
SELECT * FROM agent_statistics;
```

### Redis Debugging

```bash
# Check Redis connectivity
docker compose exec redis redis-cli ping

# Monitor all pub/sub activity
docker compose exec redis redis-cli MONITOR

# List active channels
docker compose exec redis redis-cli PUBSUB CHANNELS

# Check subscribers
docker compose exec redis redis-cli PUBSUB NUMSUB race:ready_for_analysis
```

### Manual Testing

```bash
# Activate venv
source venv/bin/activate

# Test scraper
python show_next_races.py
python show_race_details.py

# Test specific race
python show_specific_race.py --url <race_url>

# Test AI agents
python test_agent.py --url <race_url> --agent both
python test_agent.py --url <race_url> --agent gemini
python test_agent.py --url <race_url> --agent grok
```

## Performance Monitoring

### Check Timing

- Monitor analysis trigger: Should fire 3-5 minutes before race
- Result checks: Should fire 15 minutes after race start
- Poll interval: Monitor runs every 60 seconds

### Database Size

```bash
# Check database size
du -h races.db

# Count records
sqlite3 races.db "SELECT
  (SELECT COUNT(*) FROM predictions) as predictions,
  (SELECT COUNT(*) FROM prediction_outcomes) as outcomes;"
```

### Memory Usage

```bash
# Service memory usage
docker stats --no-stream

# If service using too much memory, restart:
docker compose restart <service_name>
```
