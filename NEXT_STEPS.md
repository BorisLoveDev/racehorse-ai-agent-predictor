# Next Steps - Getting Started

## ✅ What's Been Implemented

The complete Horse Racing Betting Agent System is now ready. All 4 phases have been implemented:

1. **Core Setup** - Configuration, models, database
2. **AI Agents** - Gemini and Grok agents with LangGraph workflows
3. **Services** - Monitor, Orchestrator, Results, Telegram
4. **Docker** - Complete containerized deployment

---

## 🚀 Quick Start (3 Steps)

### Step 1: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your API keys
nano .env  # or use your preferred editor
```

**Required API Keys:**

1. **OpenRouter API Key** (Required)
   - Sign up at: https://openrouter.ai/
   - Get your API key from: https://openrouter.ai/keys
   - Add to `.env`: `RACEHORSE_API_KEYS__OPENROUTER_API_KEY=sk-or-v1-...`

2. **Telegram Bot** (Required)
   - Message @BotFather on Telegram
   - Create new bot: `/newbot`
   - Copy the token
   - Add to `.env`: `RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN=123456:ABC...`
   - Get your chat ID from @userinfobot
   - Add to `.env`: `RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID=-100...`

3. **Tavily API Key** (Optional but Recommended)
   - Sign up at: https://tavily.com/
   - Get your API key from dashboard
   - Add to `.env`: `RACEHORSE_API_KEYS__TAVILY_API_KEY=tvly-...`
   - This enables web research for better predictions

### Step 2: Build and Deploy

```bash
# Make build script executable (if not already)
chmod +x build.sh

# Run the build script
./build.sh
```

This will:
- Validate your configuration
- Run database migrations
- Build Docker images
- Start all services

### Step 3: Monitor and Test

```bash
# View logs from all services
docker-compose logs -f

# Or view specific services
docker-compose logs -f monitor      # Race monitoring
docker-compose logs -f orchestrator # AI agents
docker-compose logs -f results      # Result evaluation
docker-compose logs -f telegram     # Notifications

# Check service status
docker-compose ps
```

---

## 🧪 Testing Before Live Deployment

### Test Individual Agents

Before running the full system, test the agents on a specific race:

```bash
# Get a race URL from tabtouch.mobi
# Example: python3 show_next_races.py

# Test both agents
python3 test_agent.py https://www.tabtouch.mobi/racing/... both

# Test only Gemini (faster)
python3 test_agent.py https://www.tabtouch.mobi/racing/... gemini

# Test only Grok (deeper analysis)
python3 test_agent.py https://www.tabtouch.mobi/racing/... grok
```

This will show you:
- Analysis summary
- Confidence score
- Recommended bets
- Key factors
- Execution time

---

## 📊 Monitoring Performance

### View Statistics

After the system has analyzed some races:

```bash
python3 view_stats.py
```

This shows:
- Overall performance per agent
- Win rates and ROI
- Bet type breakdown
- Agent comparison
- Performance insights

### Query Database Directly

```bash
sqlite3 races.db

# View all agents
SELECT * FROM agents;

# View recent predictions
SELECT
  p.prediction_id,
  a.agent_name,
  p.race_location,
  p.race_number,
  p.confidence_score,
  p.created_at
FROM predictions p
JOIN agents a ON p.agent_id = a.agent_id
ORDER BY p.created_at DESC
LIMIT 10;

# View outcomes with P/L
SELECT
  a.agent_name,
  COUNT(*) as races,
  SUM(o.total_bet_amount) as total_bet,
  SUM(o.total_payout) as total_payout,
  SUM(o.net_profit_loss) as net_pl,
  ROUND(AVG(o.net_profit_loss), 2) as avg_pl_per_race
FROM prediction_outcomes o
JOIN predictions p ON o.prediction_id = p.prediction_id
JOIN agents a ON p.agent_id = a.agent_id
GROUP BY a.agent_name;

# Exit
.quit
```

---

## ⚙️ Configuration Tuning

### Timing Settings

Adjust when predictions are made and how results are checked:

```bash
# In .env file:

# Trigger analysis 5 minutes before race (default: 3)
RACEHORSE_TIMING__MINUTES_BEFORE_RACE=5

# Wait 20 minutes for results (default: 15)
RACEHORSE_TIMING__RESULT_WAIT_MINUTES=20

# Check for races every 30 seconds (default: 60)
RACEHORSE_TIMING__MONITOR_POLL_INTERVAL=30
```

### Betting Strategy

Control bet amounts and confidence thresholds:

```bash
# In .env file:

# Only place bets with 70%+ confidence (default: 0.5)
RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET=0.7

# Increase virtual bet amount (default: 100)
RACEHORSE_BETTING__DEFAULT_BET_AMOUNT=200

# Disable exotic bets (default: true)
RACEHORSE_BETTING__ENABLE_EXOTIC_BETS=false
```

### Agent Configuration

Adjust agent behavior:

```bash
# In .env file:

# Use different Gemini model
RACEHORSE_AGENTS__GEMINI__MODEL_ID=google/gemini-pro

# Adjust temperature for more randomness
RACEHORSE_AGENTS__GEMINI__TEMPERATURE=0.9

# Disable web search to save on API costs
RACEHORSE_AGENTS__GEMINI__ENABLE_WEB_SEARCH=false

# Change Grok reasoning effort (low, medium, high)
RACEHORSE_AGENTS__GROK__REASONING_EFFORT=medium
```

After changing configuration:
```bash
docker-compose down
docker-compose up -d
```

---

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check if Redis is healthy
docker-compose ps redis

# If Redis is down, restart everything
docker-compose down
docker-compose up -d

# Check logs for errors
docker-compose logs redis
```

### No Predictions Generated

1. **Check API keys are valid:**
   ```bash
   # Verify .env has real keys, not placeholder values
   grep "OPENROUTER_API_KEY" .env
   ```

2. **Check agent logs:**
   ```bash
   docker-compose logs orchestrator
   ```

3. **Test agents manually:**
   ```bash
   python3 test_agent.py <race_url>
   ```

4. **Verify confidence threshold:**
   - Default is 0.5 (50% confidence)
   - If agents aren't confident, they won't bet
   - Lower threshold in .env: `RACEHORSE_BETTING__MIN_CONFIDENCE_TO_BET=0.3`

### No Results Evaluated

1. **Check results service logs:**
   ```bash
   docker-compose logs results
   ```

2. **Verify timing:**
   - Results may not be posted yet
   - Default wait is 15 minutes after race start
   - Some races take longer

3. **Check scheduled checks:**
   ```bash
   # This info is in the results service logs
   docker-compose logs results | grep "Scheduled"
   ```

### Telegram Not Working

1. **Verify bot token:**
   ```bash
   # Test bot is working
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

2. **Verify chat ID:**
   - Get your chat ID from @userinfobot
   - Must be a number (negative for groups)

3. **Check telegram service logs:**
   ```bash
   docker-compose logs telegram
   ```

---

## 📈 Expected First Run

When you first start the system:

1. **Monitor service** starts polling for races
2. No immediate activity until a race is 3 minutes away
3. When triggered:
   - Monitor → "Triggering analysis for: [Location] R[Number]"
   - Orchestrator → "Running agents in parallel..."
   - Orchestrator → "✓ Gemini prediction saved"
   - Orchestrator → "✓ Grok prediction saved"
   - Telegram → Sends prediction notifications
4. After race finishes:
   - Results → "Checking results: [URL]"
   - Results → "✓ Results found!"
   - Results → "Evaluating 2 predictions..."
   - Telegram → Sends result notifications
5. Statistics accumulate in database

---

## 🎯 Recommended Workflow

### Day 1: Testing
1. Configure `.env` with your API keys
2. Run `./build.sh`
3. Test agents manually on a few races
4. Monitor logs to ensure everything works

### Day 2: Live Monitoring
1. Let the system run for a full day
2. Check Telegram notifications
3. Review logs periodically
4. Let results accumulate

### Day 3: Analysis
1. Run `python3 view_stats.py`
2. Check which agent performs better
3. Adjust configuration based on results
4. Fine-tune confidence thresholds

### Ongoing
1. Monitor ROI and win rates
2. Adjust betting strategy
3. Experiment with different models
4. Track long-term performance

---

## 📚 Documentation

- **README.md** - Complete system documentation
- **IMPLEMENTATION.md** - Technical implementation details
- **CLAUDE.md** - Project overview for Claude Code
- **.env.example** - Configuration template with comments
- **This file** - Quick start guide

---

## 🆘 Getting Help

### Check Logs
```bash
docker-compose logs -f [service]
```

### View Database
```bash
sqlite3 races.db
```

### Test Components
```bash
python3 test_agent.py <race_url>
python3 view_stats.py
```

### Common Commands
```bash
# Stop all services
docker-compose down

# Restart all services
docker-compose restart

# Rebuild after code changes
docker-compose build
docker-compose up -d

# View resource usage
docker stats

# Clean up old data
docker-compose down -v  # WARNING: Deletes Redis data
```

---

## ✅ System is Ready!

Your Horse Racing Betting Agent System is fully implemented and ready to deploy.

**Next Action:**
1. Configure your `.env` file with API keys
2. Run `./build.sh`
3. Watch the logs and enjoy automated race analysis!

Good luck with your horse racing predictions! 🏇🤖
