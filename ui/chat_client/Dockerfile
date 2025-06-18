# Chat Client UI Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ui/chat_client/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ui/chat_client/ .

# Expose port
EXPOSE 8501

# Run the application
CMD ["chainlit", "run", "chainlit_app.py", "--host", "0.0.0.0", "--port", "8501"]