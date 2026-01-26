# Deployment Guide

## Production Deployment Checklist

### Prerequisites

- ✅ Linux server (Ubuntu 20.04+ or similar)
- ✅ Docker Engine 20.10+
- ✅ Docker Compose V2
- ✅ 2GB+ RAM
- ✅ 10GB+ disk space
- ✅ Stable internet connection

### Required API Keys

1. **OpenRouter API Key** - https://openrouter.ai/
   - For Gemini and Grok LLM access
   - Cost: ~$0.01-0.05 per race analysis

2. **Tavily API Key** - https://tavily.com/
   - For web search functionality
   - Free tier: 1000 requests/month

3. **Telegram Bot Token** - https://core.telegram.org/bots
   - Create via @BotFather
   - Get chat ID from @userinfobot

## Step-by-Step Deployment

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker compose version
```

### 2. Clone Repository

```bash
# Clone from GitHub
git clone https://github.com/your-username/racehorse-agent.git
cd racehorse-agent

# Or upload via SCP
scp -r racehorse-agent user@server:/path/to/deploy
```

### 3. Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env
```

**Required changes in .env:**
```bash
# API Keys (REQUIRED)
RACEHORSE_API_KEYS__OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE
RACEHORSE_API_KEYS__TAVILY_API_KEY=tvly-YOUR_KEY_HERE
RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE

# Timezone (adjust to your location)
CLIENT_TIMEZONE=Asia/Kuala_Lumpur

# Optional: Adjust timing
RACEHORSE_TIMING__MINUTES_BEFORE_RACE=5
RACEHORSE_TIMING__RESULT_WAIT_MINUTES=15
```

### 4. Build and Start Services

```bash
# Build base image (required first time)
docker build -t racehorse-base:latest -f Dockerfile.base .

# Start all services
docker compose up -d

# Verify services are running
docker compose ps
```

Expected output:
```
NAME                     STATUS
racehorse-monitor        Up (healthy)
racehorse-orchestrator   Up
racehorse-results        Up
racehorse-telegram       Up
racehorse-redis          Up (healthy)
```

### 5. Verify Operation

```bash
# Check logs
docker compose logs -f

# Monitor specific service
docker compose logs -f monitor

# Check database was created
docker compose exec monitor ls -la /app/data/
```

You should see:
- Monitor finding upcoming races
- Services connecting to Redis
- No error messages

### 6. Test Telegram Bot

1. Send `/start` to your bot
2. Wait for next race (check logs)
3. You should receive prediction notification
4. After race completes, you'll receive results

## Production Recommendations

### Security

1. **Firewall Configuration**
```bash
# Only allow SSH and necessary ports
sudo ufw allow 22/tcp
sudo ufw enable
```

2. **Redis Security**
   - Redis is NOT exposed externally (runs on internal Docker network)
   - To add password protection:
```yaml
# In docker-compose.yml, update redis command:
command: redis-server --appendonly yes --requirepass YOUR_SECURE_PASSWORD
```
```bash
# In .env, add:
RACEHORSE_REDIS__PASSWORD=YOUR_SECURE_PASSWORD
```

3. **Secrets Management**
   - Never commit `.env` to git
   - Use environment-specific `.env` files
   - Consider Docker secrets for sensitive data

### Monitoring

1. **Service Health**
```bash
# Check all services
docker compose ps

# Resource usage
docker stats

# Service logs
docker compose logs --tail=100 <service>
```

2. **Disk Space**
```bash
# Check volume usage
docker volume ls
docker system df

# Clean old images
docker system prune -a
```

3. **Database Monitoring**
```bash
# Backup database
docker compose exec monitor sqlite3 /app/data/races.db ".backup '/app/data/races_backup.db'"

# Copy backup to host
docker cp racehorse-monitor:/app/data/races_backup.db ./backup/
```

### Logging

1. **Log Rotation** (add to docker-compose.yml):
```yaml
services:
  monitor:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

2. **View Logs**
```bash
# All services
docker compose logs -f

# Last hour
docker compose logs --since 1h

# Specific service, last 100 lines
docker compose logs --tail=100 monitor
```

### Backup Strategy

1. **Database Backup Script**
```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)

docker compose exec -T monitor sqlite3 /app/data/races.db ".backup '/app/data/backup_${DATE}.db'"
docker cp racehorse-monitor:/app/data/backup_${DATE}.db ${BACKUP_DIR}/
docker compose exec monitor rm /app/data/backup_${DATE}.db

# Keep only last 7 days
find ${BACKUP_DIR} -name "backup_*.db" -mtime +7 -delete
```

2. **Cron Schedule**
```bash
# Daily backup at 3 AM
crontab -e
0 3 * * * /path/to/backup.sh
```

### Updates and Maintenance

1. **Update Application**
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose build
docker compose up -d

# Check logs for errors
docker compose logs -f
```

2. **Update Dependencies**
```bash
# Rebuild base image
docker build -t racehorse-base:latest -f Dockerfile.base .

# Rebuild all services
docker compose build --no-cache

# Restart
docker compose up -d
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker daemon
sudo systemctl status docker

# Check disk space
df -h

# Check logs
docker compose logs <service>
```

### Database Issues

```bash
# Reset database (WARNING: deletes all data)
docker compose down
docker volume rm racehorse-agent_db_data
docker compose up -d
```

### Network Issues

```bash
# Check network
docker network ls
docker network inspect racehorse-network

# Restart network
docker compose down
docker compose up -d
```

### Memory Issues

```bash
# Check memory usage
free -h
docker stats

# Add swap if needed
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## Scaling Considerations

### Multiple Instances

To run multiple instances (different regions, different configurations):

1. Clone to separate directories
2. Update `.env` with different Redis DB numbers
3. Use different container names in docker-compose.yml
4. Run each instance independently

### Resource Limits

Add to docker-compose.yml:
```yaml
services:
  monitor:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          memory: 256M
```

## Performance Tuning

### Adjust Timing
```bash
# Check races more frequently (higher load)
RACEHORSE_TIMING__MONITOR_POLL_INTERVAL=30

# Or less frequently (lower load)
RACEHORSE_TIMING__MONITOR_POLL_INTERVAL=120
```

### Disable Features
```bash
# Disable web search to save API costs
RACEHORSE_AGENTS__GEMINI__ENABLE_WEB_SEARCH=false
RACEHORSE_AGENTS__GROK__ENABLE_WEB_SEARCH=false

# Disable exotic bets
RACEHORSE_BETTING__ENABLE_EXOTIC_BETS=false
```

## Support

For issues or questions:
1. Check CLAUDE.md for architecture details
2. Review logs: `docker compose logs -f`
3. Check GitHub Issues
4. Verify API keys are valid and have credits

## License

MIT License - See LICENSE file
