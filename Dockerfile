# Dockerfile for Stake Racing Advisor
# Slim image: no Playwright/Chromium (~500MB savings vs old TabTouch image)

FROM python:3.11-slim AS base

WORKDIR /app

# Install only stake dependencies (no Playwright, no scraping libs)
COPY requirements-stake.txt .
RUN pip install --no-cache-dir -r requirements-stake.txt

# Copy source code
COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Entrypoint runs migrations before service start
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# ── Targets ──────────────────────────────────────────────────

# Stake Racing Advisor bot
FROM base AS stake
CMD ["python3", "services/stake/main.py"]

# Legacy TabTouch targets (require Dockerfile.base with Playwright)
# Use: docker build -f Dockerfile.base -t racehorse-base:latest .
#      then docker compose --profile tabtouch up
# FROM base AS monitor  — see Dockerfile.base
# FROM base AS orchestrator
# FROM base AS results
# FROM base AS telegram
