# Integrated App UI Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ui/integrated_app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ui/integrated_app/ .

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]