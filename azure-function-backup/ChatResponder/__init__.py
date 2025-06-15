import json
import logging
import os
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import openai

from events import Event, LLMChatEvent

SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
CONTEXT_HUB_URL = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")

missing = []
if not SERVICEBUS_CONN:
    missing.append("SERVICEBUS_CONNECTION")
if not SERVICEBUS_QUEUE:
    missing.append("SERVICEBUS_QUEUE")
if not OPENAI_API_KEY:
    missing.append("OPENAI_API_KEY")
if missing:
    logging.error("Missing required environment variable(s): %s", ", ".join(missing))
    raise RuntimeError("Azure Function misconfigured")

client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)


def search_user_context(user_id: str, query: str, limit: int = 5) -> Optional[Dict[str, Any]]:
    """Search user's context-hub for relevant documents."""
    try:
        url = f"{CONTEXT_HUB_URL.rstrip('/')}/search"
        headers = {"X-User-Id": user_id}
        params = {"q": query, "limit": limit}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logging.warning(f"Context search failed for user {user_id}: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error searching context for user {user_id}: {e}")
        return None


def get_context_search_tool() -> Dict[str, Any]:
    """Define the context search tool for function calling."""
    return {
        "type": "function",
        "function": {
            "name": "search_user_context",
            "description": "Search the user's personal context hub for relevant documents, notes, and information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant content in the user's documents"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }


def handle_function_call(function_name: str, arguments: Dict[str, Any], user_id: str) -> str:
    """Handle function calls from the LLM."""
    if function_name == "search_user_context":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        
        if not query:
            return "Error: No search query provided"
        
        results = search_user_context(user_id, query, limit)
        if not results:
            return "No relevant documents found in your context hub."
        
        # Format results for the LLM
        formatted_results = []
        for result in results.get("results", []):
            formatted_results.append(f"**{result.get('name', 'Untitled')}**\n{result.get('content', '')[:500]}...")
        
        if formatted_results:
            return f"Found {len(formatted_results)} relevant documents:\n\n" + "\n\n".join(formatted_results)
        else:
            return "No relevant documents found in your context hub."
    
    return f"Unknown function: {function_name}"


def main(msg: func.ServiceBusMessage) -> None:
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = LLMChatEvent.from_dict(data)
    except Exception as e:
        logging.error("Invalid event: %s", e)
        return

    # Prepare messages with system prompt about context search
    messages = event.messages.copy()
    
    # Add system message about context search capability
    system_message = {
        "role": "system",
        "content": "You are a helpful AI assistant with access to the user's personal context hub. You can search their documents, notes, and files using the search_user_context function when relevant to their questions. Always cite sources when referencing information from their context hub."
    }
    
    # Insert system message at the beginning if not already present
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, system_message)
    else:
        # Update existing system message to include context search info
        messages[0]["content"] += "\n\n" + system_message["content"]

    try:
        # First attempt with function calling
        response = openai.ChatCompletion.create(
            messages=messages,
            model=OPENAI_MODEL,
            tools=[get_context_search_tool()],
            tool_choice="auto"
        )
        
        message = response["choices"][0]["message"]
        usage = response.get("usage", {})
        
        # Check if the model wants to call a function
        if message.get("tool_calls"):
            # Handle function calls
            messages.append(message)
            
            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                try:
                    arguments = json.loads(tool_call["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}
                
                function_result = handle_function_call(function_name, arguments, event.user_id)
                
                # Add function result to messages
                messages.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": function_name,
                    "content": function_result
                })
            
            # Get final response with function results
            final_response = openai.ChatCompletion.create(
                messages=messages,
                model=OPENAI_MODEL,
            )
            
            reply = final_response["choices"][0]["message"]["content"]
            usage.update(final_response.get("usage", {}))
        else:
            reply = message["content"]
        
        logging.info("Assistant reply: %s", reply)
        
    except Exception as e:
        logging.error("ChatCompletion failed: %s", e)
        return

    out_event = Event(
        timestamp=datetime.utcnow(),
        source="ChatResponder",
        type="llm.chat.response",
        user_id=event.user_id,
        metadata={"reply": reply, "usage": usage},
        history=event.history + [event.to_dict()],
    )

    message = ServiceBusMessage(json.dumps(out_event.to_dict()))
    message.application_properties = {"topic": out_event.type}

    try:
        with client:
            sender = client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
            with sender:
                sender.send_messages(message)
    except Exception as e:
        logging.error("Failed to publish response: %s", e)
