FROM python:3.11-slim

WORKDIR /app

# Copy the chat client code and dependencies
COPY chat_client/chainlit_app.py ./chainlit_app.py
COPY chat_client/auth_app.py ./auth_app.py
COPY chat_client/templates/ ./templates/
COPY chat_client/start.sh ./start.sh
COPY chat_client/gateway_app.py ./gateway_app.py
COPY events/ ./events/
COPY dashboard/ ./dashboard/
COPY common/ ./common/

# Copy Python dependencies
COPY chat_client/requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make startup script executable
RUN chmod +x ./start.sh

# Expose HTTPS port for the gateway
EXPOSE 443

# Run the multi-service startup script
CMD ["./start.sh"]
