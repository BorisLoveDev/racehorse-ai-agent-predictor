# Multi-target Dockerfile for all services
# Docker caches the base stage once, each target just adds CMD

# Stage 1: Base with all dependencies (built ONCE, shared by all targets)
FROM python:3.11-slim AS base

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libfreetype6-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy source code
COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Target: monitor
FROM base AS monitor
CMD ["python3", "services/monitor/main.py"]

# Target: orchestrator
FROM base AS orchestrator
CMD ["python3", "services/orchestrator/main.py"]

# Target: results
FROM base AS results
CMD ["python3", "services/results/main.py"]

# Target: telegram
FROM base AS telegram
CMD ["python3", "services/telegram/main.py"]
