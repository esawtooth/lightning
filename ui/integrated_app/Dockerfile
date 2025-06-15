FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY ui/integrated_app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ui/integrated_app/ .

# Expose HTTP port
EXPOSE 80

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
