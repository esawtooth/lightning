# Lightning Core Unified Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Build argument for deployment mode
ARG LIGHTNING_MODE=local
ARG SERVICE_TYPE=api

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

# Install Python dependencies based on mode
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN if [ "$LIGHTNING_MODE" = "azure" ]; then \
        echo "Installing Azure dependencies"; \
        pip install --no-cache-dir -e .[azure,dev]; \
    elif [ "$LIGHTNING_MODE" = "aws" ]; then \
        echo "Installing AWS dependencies"; \
        pip install --no-cache-dir -e .[aws,dev]; \
    else \
        echo "Installing local dependencies"; \
        pip install --no-cache-dir -e .[local,dev]; \
    fi

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV LIGHTNING_MODE=${LIGHTNING_MODE}
ENV SERVICE_TYPE=${SERVICE_TYPE}

# Use the service launcher as entry point
CMD ["python", "-m", "lightning_core.service_launcher"]