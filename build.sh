#!/bin/bash
# Build and deployment script for Horse Racing Betting Agent

set -e

echo "🏇 Horse Racing Betting Agent - Build Script"
echo "=============================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please copy .env.example to .env and configure your API keys:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Validate required environment variables
echo "🔍 Validating configuration..."
required_vars=(
    "RACEHORSE_API_KEYS__OPENROUTER_API_KEY"
    "RACEHORSE_API_KEYS__TELEGRAM_BOT_TOKEN"
    "RACEHORSE_API_KEYS__TELEGRAM_CHAT_ID"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if ! grep -q "^$var=.." .env; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "❌ Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please configure these in your .env file"
    exit 1
fi

echo "✅ Configuration validated"
echo ""

# Run database migrations
echo "📊 Running database migrations..."
python3 src/database/migrations.py

if [ $? -ne 0 ]; then
    echo "❌ Database migrations failed"
    exit 1
fi

echo "✅ Database ready"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install docker-compose first."
    exit 1
fi

echo "🐳 Building Docker images..."
echo ""

# Build base image
echo "Building base image..."
docker build -t racehorse-base:latest -f Dockerfile.base .

if [ $? -ne 0 ]; then
    echo "❌ Base image build failed"
    exit 1
fi

echo "✅ Base image built successfully"
echo ""

# Start services
echo "🚀 Starting services..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Failed to start services"
    exit 1
fi

echo ""
echo "✅ All services started successfully!"
echo ""
echo "📋 Service Status:"
docker-compose ps
echo ""
echo "📝 View logs:"
echo "  docker-compose logs -f           # All services"
echo "  docker-compose logs -f monitor   # Monitor service"
echo "  docker-compose logs -f orchestrator  # Orchestrator service"
echo "  docker-compose logs -f results   # Results service"
echo "  docker-compose logs -f telegram  # Telegram service"
echo ""
echo "🛑 Stop services:"
echo "  docker-compose down"
echo ""
echo "🏇 System is now monitoring races and will send notifications to Telegram!"
