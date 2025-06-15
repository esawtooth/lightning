import os
import json
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any

import azure.functions as func
from azure.cosmos import CosmosClient
from common.jwt_utils import verify_token

# Configuration
COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
USER_CONTAINER = os.environ.get("USER_CONTAINER", "users")
HUB_URL = os.environ.get("HUB_URL", "http://localhost:3000")

_client = CosmosClient.from_connection_string(COSMOS_CONN) if COSMOS_CONN else None
_db = _client.create_database_if_not_exists(COSMOS_DB) if _client else None
_container = _db.create_container_if_not_exists(id=USER_CONTAINER, partition_key="/pk") if _db else None


def _get_user_from_token(token: str) -> Optional[str]:
    """Extract user ID from JWT token."""
    try:
        return verify_token(token)
    except Exception as e:
        logging.warning(f"Invalid token: {e}")
        return None


def _get_user_record(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user record from Cosmos DB."""
    if not _container:
        return None
    
    try:
        items = list(_container.query_items(
            query="SELECT * FROM c WHERE c.user_id=@user_id",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else None
    except Exception as e:
        logging.error(f"Error fetching user record: {e}")
        return None


def _update_user_record(user_id: str, updates: Dict[str, Any]) -> bool:
    """Update user record in Cosmos DB."""
    if not _container:
        return False
    
    try:
        user = _get_user_record(user_id)
        if not user:
            return False
        
        user.update(updates)
        _container.upsert_item(user)
        return True
    except Exception as e:
        logging.error(f"Error updating user record: {e}")
        return False


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
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
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


def _initialize_user_context(user_id: str) -> Optional[str]:
    """Initialize context-hub structure for a new user."""
    try:
        # Create root folder for user
        root_folder = _make_hub_request("POST", "/docs", user_id, {
            "name": f"{user_id}_workspace",
            "content": "",
            "parent_folder_id": None,
            "doc_type": "Folder"
        })
        
        if not root_folder:
            logging.error(f"Failed to create root folder for user {user_id}")
            return None
        
        root_folder_id = root_folder.get("id")
        
        # Create default subfolders
        default_folders = [
            {"name": "Projects", "description": "Project-related documents and notes"},
            {"name": "Documents", "description": "General documents and files"},
            {"name": "Notes", "description": "Personal notes and thoughts"},
            {"name": "Research", "description": "Research materials and references"}
        ]
        
        folder_ids = {"root": root_folder_id}
        
        for folder_info in default_folders:
            folder = _make_hub_request("POST", "/docs", user_id, {
                "name": folder_info["name"],
                "content": "",
                "parent_folder_id": root_folder_id,
                "doc_type": "Folder"
            })
            
            if folder:
                folder_ids[folder_info["name"].lower()] = folder.get("id")
                
                # Create index guide for each folder
                _make_hub_request("POST", "/docs", user_id, {
                    "name": "Index Guide",
                    "content": f"# {folder_info['name']} Folder\n\n{folder_info['description']}\n\nThis folder is for organizing your {folder_info['name'].lower()}.",
                    "parent_folder_id": folder.get("id"),
                    "doc_type": "IndexGuide"
                })
        
        # Create welcome document
        welcome_doc = _make_hub_request("POST", "/docs", user_id, {
            "name": "Welcome to Vextir",
            "content": f"""# Welcome to Vextir, {user_id}!

This is your personal context hub where you can store and organize your documents, notes, and project files.

## Getting Started

Your workspace includes the following folders:
- **Projects**: For project-related documents and notes
- **Documents**: For general documents and files  
- **Notes**: For personal notes and thoughts
- **Research**: For research materials and references

## Features

- **Search**: Use the search functionality to quickly find content across all your documents
- **Chat Integration**: Your AI assistant can access and reference your documents during conversations
- **Organization**: Create additional folders and organize your content as needed

Start by uploading some documents or creating new notes to build your personal knowledge base!
""",
            "parent_folder_id": root_folder_id,
            "doc_type": "Text"
        })
        
        logging.info(f"Successfully initialized context hub for user {user_id}")
        return root_folder_id
        
    except Exception as e:
        logging.error(f"Error initializing user context: {e}")
        return None


def _search_user_context(user_id: str, query: str, limit: int = 10) -> Optional[Dict]:
    """Search user's context-hub content."""
    try:
        response = _make_hub_request("GET", f"/search?q={query}&limit={limit}", user_id)
        return response
    except Exception as e:
        logging.error(f"Error searching user context: {e}")
        return None


def _get_user_folders(user_id: str) -> Optional[Dict]:
    """Get user's folder structure."""
    user = _get_user_record(user_id)
    if not user or not user.get("context_hub_root_id"):
        return None
    
    root_id = user["context_hub_root_id"]
    return _make_hub_request("GET", f"/folders/{root_id}", user_id)


def _create_document(user_id: str, name: str, content: str, folder_id: Optional[str] = None) -> Optional[Dict]:
    """Create a new document in user's context-hub."""
    if not folder_id:
        user = _get_user_record(user_id)
        if not user or not user.get("context_hub_root_id"):
            return None
        folder_id = user["context_hub_root_id"]
    
    return _make_hub_request("POST", "/docs", user_id, {
        "name": name,
        "content": content,
        "parent_folder_id": folder_id,
        "doc_type": "Text"
    })


def main(req: func.HttpRequest) -> func.HttpResponse:
    """Main handler for context-hub management operations."""
    
    # Extract user from authorization header
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return func.HttpResponse("Missing or invalid authorization header", status_code=401)
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    user_id = _get_user_from_token(token)
    if not user_id:
        return func.HttpResponse("Invalid token", status_code=401)
    
    method = req.method
    route_params = req.route_params
    action = route_params.get("action", "")
    
    try:
        # Initialize user context-hub
        if action == "initialize" and method == "POST":
            root_folder_id = _initialize_user_context(user_id)
            if root_folder_id:
                # Update user record with context-hub info
                _update_user_record(user_id, {
                    "context_hub_root_id": root_folder_id,
                    "context_hub_initialized": True,
                    "context_hub_initialized_at": datetime.utcnow().isoformat()
                })
                return func.HttpResponse(
                    json.dumps({"status": "success", "root_folder_id": root_folder_id}),
                    status_code=200,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Failed to initialize context hub", status_code=500)
        
        # Search user's context
        elif action == "search" and method == "GET":
            query = req.params.get("q", "")
            limit = int(req.params.get("limit", "10"))
            
            if not query:
                return func.HttpResponse("Missing search query", status_code=400)
            
            results = _search_user_context(user_id, query, limit)
            if results is not None:
                return func.HttpResponse(
                    json.dumps(results),
                    status_code=200,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Search failed", status_code=500)
        
        # Get user's folders
        elif action == "folders" and method == "GET":
            folders = _get_user_folders(user_id)
            if folders is not None:
                return func.HttpResponse(
                    json.dumps(folders),
                    status_code=200,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Failed to get folders", status_code=500)
        
        # Create document
        elif action == "documents" and method == "POST":
            try:
                data = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON", status_code=400)
            
            name = data.get("name")
            content = data.get("content", "")
            folder_id = data.get("folder_id")
            
            if not name:
                return func.HttpResponse("Missing document name", status_code=400)
            
            doc = _create_document(user_id, name, content, folder_id)
            if doc:
                return func.HttpResponse(
                    json.dumps(doc),
                    status_code=201,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Failed to create document", status_code=500)
        
        # Get user's context status
        elif action == "status" and method == "GET":
            user = _get_user_record(user_id)
            if user:
                status = {
                    "initialized": user.get("context_hub_initialized", False),
                    "root_folder_id": user.get("context_hub_root_id"),
                    "initialized_at": user.get("context_hub_initialized_at")
                }
                return func.HttpResponse(
                    json.dumps(status),
                    status_code=200,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("User not found", status_code=404)
        
        else:
            return func.HttpResponse("Invalid action or method", status_code=400)
    
    except Exception as e:
        logging.error(f"Error in context hub manager: {e}")
        return func.HttpResponse(f"Internal error: {str(e)}", status_code=500)
