import json
import logging
import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey

from events import ContextUpdateEvent

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
USER_CONTAINER = os.environ.get("USER_CONTAINER", "users")
HUB_URL = os.environ.get("HUB_URL", "http://localhost:3000")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

_client = CosmosClient.from_connection_string(COSMOS_CONN) if COSMOS_CONN else None
_db = _client.create_database_if_not_exists(COSMOS_DB) if _client else None
_user_container = _db.create_container_if_not_exists(
    id=USER_CONTAINER, partition_key=PartitionKey(path="/pk")
) if _db else None


def _make_hub_request(method: str, endpoint: str, user_id: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """Make authenticated request to context-hub."""
    try:
        url = f"{HUB_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "X-User-Id": user_id,
            "Content-Type": "application/json"
        }
        
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=10)
        else:
            return None
        
        if response.status_code < 300:
            return response.json() if response.content else {}
        else:
            logging.error(f"Hub request failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"Error making hub request: {e}")
        return None


def _get_context_document(user_id: str, context_key: str) -> Optional[Dict]:
    """Get or create a context document in the hub."""
    # Search for existing context document
    search_result = _make_hub_request("GET", f"/search?q={context_key}&limit=1", user_id)
    
    if search_result and search_result.get("results"):
        # Return existing document
        return search_result["results"][0]
    
    # Create new context document
    user = _get_user_record(user_id)
    if not user or not user.get("context_hub_root_id"):
        logging.error(f"User {user_id} does not have context hub initialized")
        return None
    
    root_folder_id = user["context_hub_root_id"]
    
    new_doc = _make_hub_request("POST", "/docs", user_id, {
        "name": f"Context: {context_key}",
        "content": f"# {context_key.replace('_', ' ').title()}\n\nThis document maintains a running summary of {context_key}.\n\n## Summary\n\n*No content yet*",
        "parent_folder_id": root_folder_id,
        "doc_type": "ContextSummary"
    })
    
    return new_doc


def _get_user_record(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user record from Cosmos DB."""
    if not _user_container:
        return None
    
    try:
        items = list(_user_container.query_items(
            query="SELECT * FROM c WHERE c.user_id=@user_id",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else None
    except Exception as e:
        logging.error(f"Error fetching user record: {e}")
        return None


def _synthesize_content_with_llm(current_content: str, new_content: str, synthesis_prompt: str) -> str:
    """Use OpenAI to synthesize new content with existing content."""
    if not OPENAI_API_KEY:
        # Fallback to simple append if no API key
        return f"{current_content}\n\n## Update ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})\n\n{new_content}"
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = f"""You are a context synthesizer. Your job is to update a running summary with new information.

Instructions: {synthesis_prompt}

Guidelines:
- Maintain the most important information
- Remove redundant or outdated information
- Keep the summary concise but comprehensive
- Preserve key dates, names, and action items
- Structure the content clearly with headers
- Update timestamps when relevant"""

        user_prompt = f"""Current Summary:
{current_content}

New Information to Integrate:
{new_content}

Please provide an updated summary that integrates this new information appropriately."""

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0.3
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            logging.error(f"OpenAI API error: {response.status_code} - {response.text}")
            # Fallback to simple append
            return f"{current_content}\n\n## Update ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})\n\n{new_content}"
    
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        # Fallback to simple append
        return f"{current_content}\n\n## Update ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})\n\n{new_content}"


def _update_context_document(user_id: str, doc_id: str, new_content: str) -> bool:
    """Update a context document in the hub."""
    try:
        result = _make_hub_request("PUT", f"/docs/{doc_id}", user_id, {
            "content": new_content
        })
        return result is not None
    except Exception as e:
        logging.error(f"Error updating context document: {e}")
        return False


def _process_context_update(event: ContextUpdateEvent) -> bool:
    """Process a context update event."""
    try:
        # Get or create context document
        context_doc = _get_context_document(event.user_id, event.context_key)
        if not context_doc:
            logging.error(f"Failed to get/create context document for {event.context_key}")
            return False
        
        current_content = context_doc.get("content", "")
        
        # Process based on update operation
        if event.update_operation == "replace":
            new_content = event.content
        
        elif event.update_operation == "append":
            new_content = f"{current_content}\n\n## Update ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})\n\n{event.content}"
        
        elif event.update_operation == "synthesize":
            synthesis_prompt = event.synthesis_prompt or "Integrate this new information into the existing summary."
            new_content = _synthesize_content_with_llm(current_content, event.content, synthesis_prompt)
        
        elif event.update_operation == "merge":
            # Simple merge - could be enhanced with more sophisticated logic
            new_content = f"{current_content}\n\n{event.content}"
        
        else:
            logging.error(f"Unknown update operation: {event.update_operation}")
            return False
        
        # Update the document
        success = _update_context_document(event.user_id, context_doc["id"], new_content)
        
        if success:
            logging.info(f"Successfully updated context {event.context_key} for user {event.user_id}")
        else:
            logging.error(f"Failed to update context {event.context_key} for user {event.user_id}")
        
        return success
    
    except Exception as e:
        logging.error(f"Error processing context update: {e}")
        return False


def main(msg: func.ServiceBusMessage) -> None:
    """Main handler for context synthesis operations."""
    
    if not _user_container:
        logging.error("User container not configured")
        return
    
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = ContextUpdateEvent.from_dict(data)
    except Exception as e:
        logging.error(f"Invalid context update event: {e}")
        return
    
    # Process the context update
    success = _process_context_update(event)
    
    if not success:
        logging.error(f"Failed to process context update for user {event.user_id}")
