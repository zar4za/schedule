# File: Dockerfile
FROM python:3.12-slim

# Set a working directory
WORKDIR /app

# Copy requirement spec and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py solver.py ./

# Environment variables for Redis configuration
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV REDIS_DB=0

# Default command
CMD ["python", "scheduler_service.py"]