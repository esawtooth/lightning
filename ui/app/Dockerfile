# Unified Lightning UI Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Build argument for deployment mode
ARG LIGHTNING_MODE=local

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    aiohttp \
    websockets \
    jinja2 \
    python-multipart \
    pydantic \
    itsdangerous \
    requests \
    pyjwt

# For Azure deployment, add Azure-specific dependencies
RUN if [ "$LIGHTNING_MODE" = "azure" ]; then \
        pip install --no-cache-dir \
            azure-identity \
            opencensus-ext-azure \
            opencensus-ext-logging; \
    fi

# Copy the app files based on build context
# When building from root: COPY ui/integrated_app/* .
# When building from ui/integrated_app: COPY . .
COPY ui/integrated_app/app.py .
COPY ui/integrated_app/lightning_ui.py .

# Copy templates and static directories
COPY ui/integrated_app/templates ./templates
COPY ui/integrated_app/static ./static

# Copy common utilities
COPY ui/integrated_app/common ./common

# Set environment variables
ENV LIGHTNING_MODE=${LIGHTNING_MODE}
ENV SERVICE_TYPE=ui

# Expose port (Azure Container Instances will override this)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the appropriate application based on environment variable
CMD if [ "$LIGHTNING_UI" = "true" ]; then \
        uvicorn lightning_ui:app --host 0.0.0.0 --port 8080; \
    elif [ -f "app.py" ]; then \
        uvicorn app:app --host 0.0.0.0 --port 8080; \
    else \
        uvicorn app:app --host 0.0.0.0 --port 8080; \
    fi