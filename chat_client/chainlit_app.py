import os
from datetime import datetime

import requests
import chainlit as cl
from fastapi import HTTPException
from chainlit.server import app as fastapi_app

EVENT_API_URL = os.environ.get("EVENT_API_URL")


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user message and queue a chat event."""
    if not EVENT_API_URL:
        await cl.Message(content="EVENT_API_URL not configured", author="system").send()
        return

    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "chainlit",
        "type": "llm.chat",
        "metadata": {
            "messages": [{"role": "user", "content": message.content}]
        },
    }

    headers = {"X-User-ID": message.author}
    try:
        requests.post(EVENT_API_URL, json=event, headers=headers)
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
