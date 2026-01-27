# Monitor Service Dockerfile
FROM racehorse-base:latest

WORKDIR /app

# Copy source code (base image only has dependencies)
COPY . .

CMD ["python3", "services/monitor/main.py"]
