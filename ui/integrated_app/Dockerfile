# Unified UI Dockerfile (Gateway + Auth + Integrated Apps)
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from both apps
COPY ui/chat_client/requirements.txt chat_client_requirements.txt
COPY ui/integrated_app/requirements.txt integrated_app_requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r chat_client_requirements.txt
RUN pip install --no-cache-dir -r integrated_app_requirements.txt

# Copy all application code
COPY ui/chat_client/*.py .
COPY ui/chat_client/static ./static
COPY ui/chat_client/templates ./templates
COPY ui/integrated_app/ ./integrated_app

# Expose port
EXPOSE 8000

# Run the gateway application which mounts both auth and integrated apps
CMD ["uvicorn", "gateway_app:app", "--host", "0.0.0.0", "--port", "8000"]