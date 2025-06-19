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

# Copy application code and common module
COPY ui/integrated_app/ .
# Ensure common directory is properly copied
RUN if [ ! -d "common" ]; then echo "ERROR: common directory not found!"; exit 1; fi

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "app.py"]