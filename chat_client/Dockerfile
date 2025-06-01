FROM python:3.11-slim

WORKDIR /app

# Copy the chat client code and dependencies
COPY chat_client/chainlit_app.py ./chainlit_app.py
COPY events/ ./events/
COPY dashboard/ ./dashboard/

# Install Python dependencies
RUN pip install --no-cache-dir chainlit fastapi uvicorn requests jinja2

# Expose the port
EXPOSE 8000

# Run the Chainlit app
CMD ["bash", "-c", "chainlit run chainlit_app.py --host 0.0.0.0 --port 8000"]
