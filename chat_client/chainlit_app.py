import os
from datetime import datetime

import logging
import requests
import chainlit as cl
from fastapi import HTTPException
from chainlit.server import app as fastapi_app
from dashboard.app import app as dashboard_app

EVENT_API_URL = os.environ.get("EVENT_API_URL")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user message and queue a chat event."""
    if not EVENT_API_URL:
        await cl.Message(content="EVENT_API_URL not configured", author="system").send()
        return
    if not AUTH_TOKEN:
        await cl.Message(content="AUTH_TOKEN not configured", author="system").send()
        return

    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "chainlit",
        "type": "llm.chat",
        "metadata": {
            "messages": [{"role": "user", "content": message.content}]
        },
    }

    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    try:
        resp = requests.post(EVENT_API_URL, json=event, headers=headers)
        if not 200 <= resp.status_code < 300:
            logging.warning("Event API returned status %s: %s", resp.status_code, resp.text)
    except Exception as e:
        await cl.Message(content=f"Failed to send event: {e}", author="system").send()
        return

    await cl.Message(content="Message queued!", author="system").send()


@fastapi_app.post("/notify")
async def notify(payload: dict):
    """Forward a message to the current Chainlit session."""
    user_id = payload.get("user_id")
    message = payload.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message required")

    await cl.Message(content=message, author=user_id or "assistant").send()
    return {"status": "ok"}

# Expose the dashboard under /dashboard on the Chainlit FastAPI app
fastapi_app.mount("/dashboard", dashboard_app)
