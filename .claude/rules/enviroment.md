# Environment Setup

## Virtual Environment

Always use the project's virtual environment:

```bash
# Activate venv
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Deactivate when done
deactivate
```

## Git Workflow

- Always commit significant changes
- Use descriptive commit messages
- Commit BEFORE major refactoring
- Commit AFTER completing features

## Running the Application

### Development Mode

For local testing and development:

```bash
# Activate venv
source venv/bin/activate

# Run individual scripts
python show_next_races.py
python show_race_details.py
python test_agent.py --url <race_url> --agent both
```

### Production Mode

Use Docker Compose for running all microservices:

```bash
# Build base image (required after code changes)
docker build -f Dockerfile.base -t racehorse-base:latest .

# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

## Environment Variables

Required in `.env`:

```bash
SOURCE_TIMEZONE=Australia/Perth
CLIENT_TIMEZONE=Asia/Kuala_Lumpur
OPENROUTER_API_KEY=sk-or-...
TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_CHAT_ID=-100...
```

## Dependencies

- Python 3.13+
- Docker & Docker Compose
- Redis (via Docker)
- SQLite (included)
- Playwright browsers (auto-installed) 