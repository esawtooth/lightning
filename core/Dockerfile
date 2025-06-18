# Lightning Core API Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -e .[local,dev]

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Default command
CMD ["uvicorn", "lightning_core.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]