FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir chainlit fastapi uvicorn requests jinja2
EXPOSE 8000
CMD ["bash", "-c", "chainlit run chat_client/chainlit_app.py --host 0.0.0.0 --port 8000"]
