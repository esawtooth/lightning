FROM python:3.11-slim

WORKDIR /app

# Copy the chat client code and dependencies
COPY chat_client/chainlit_app.py ./chainlit_app.py
COPY chat_client/auth_app.py ./auth_app.py
COPY chat_client/templates/ ./templates/
COPY chat_client/start.sh ./start.sh
COPY events/ ./events/
COPY dashboard/ ./dashboard/
COPY common/ ./common/

# Install Python dependencies
RUN pip install --no-cache-dir \
    chainlit \
    fastapi \
    uvicorn \
    requests \
    jinja2 \
    python-multipart \
    python-jose[cryptography] \
    PyJWT \
    itsdangerous

# Make startup script executable
RUN chmod +x ./start.sh

# Expose ports for both services
EXPOSE 8000 8001

# Run the multi-service startup script
CMD ["./start.sh"]
