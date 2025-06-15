import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey

from simple_auth import get_user_id_permissive

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
INSTRUCTION_CONTAINER = os.environ.get("INSTRUCTION_CONTAINER", "instructions")

_client = CosmosClient.from_connection_string(COSMOS_CONN) if COSMOS_CONN else None
_db = _client.create_database_if_not_exists(COSMOS_DB) if _client else None
_container = _db.create_container_if_not_exists(
    id=INSTRUCTION_CONTAINER, partition_key=PartitionKey(path="/pk")
) if _db else None


def _validate_instruction(instruction_data: Dict[str, Any]) -> bool:
    """Validate instruction structure."""
    required_fields = ["name", "trigger", "action"]
    for field in required_fields:
        if field not in instruction_data:
            return False
    
    # Validate trigger structure
    trigger = instruction_data["trigger"]
    if not isinstance(trigger, dict) or "event_type" not in trigger:
        return False
    
    # Validate action structure
    action = instruction_data["action"]
    if not isinstance(action, dict) or "type" not in action:
        return False
    
    return True


def _create_instruction(user_id: str, instruction_data: Dict[str, Any]) -> Optional[str]:
    """Create a new instruction for the user."""
    if not _validate_instruction(instruction_data):
        return None
    
    instruction_id = uuid.uuid4().hex
    entity = {
        "id": instruction_id,
        "pk": user_id,
        "name": instruction_data["name"],
        "description": instruction_data.get("description", ""),
        "trigger": instruction_data["trigger"],
        "action": instruction_data["action"],
        "enabled": instruction_data.get("enabled", True),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "execution_count": 0,
        "last_executed": None,
    }
    
    try:
        _container.upsert_item(entity)
        return instruction_id
    except Exception as e:
        logging.error(f"Failed to create instruction: {e}")
        return None


def _get_user_instructions(user_id: str) -> List[Dict[str, Any]]:
    """Get all instructions for a user."""
    try:
        items = list(_container.query_items(
            query="SELECT * FROM c WHERE c.pk=@user_id",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        return items
    except Exception as e:
        logging.error(f"Failed to get instructions: {e}")
        return []


def _get_instruction(user_id: str, instruction_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific instruction."""
    try:
        item = _container.read_item(instruction_id, partition_key=user_id)
        return item
    except Exception as e:
        logging.error(f"Failed to get instruction {instruction_id}: {e}")
        return None


def _update_instruction(user_id: str, instruction_id: str, updates: Dict[str, Any]) -> bool:
    """Update an existing instruction."""
    try:
        item = _container.read_item(instruction_id, partition_key=user_id)
        if not item:
            return False
        
        # Update allowed fields
        allowed_updates = ["name", "description", "trigger", "action", "enabled"]
        for key, value in updates.items():
            if key in allowed_updates:
                item[key] = value
        
        item["updated_at"] = datetime.utcnow().isoformat()
        _container.upsert_item(item)
        return True
    except Exception as e:
        logging.error(f"Failed to update instruction {instruction_id}: {e}")
        return False


def _delete_instruction(user_id: str, instruction_id: str) -> bool:
    """Delete an instruction."""
    try:
        _container.delete_item(instruction_id, partition_key=user_id)
        return True
    except Exception as e:
        logging.error(f"Failed to delete instruction {instruction_id}: {e}")
        return False


def _increment_execution_count(user_id: str, instruction_id: str) -> bool:
    """Increment execution count for an instruction."""
    try:
        item = _container.read_item(instruction_id, partition_key=user_id)
        if not item:
            return False
        
        item["execution_count"] = item.get("execution_count", 0) + 1
        item["last_executed"] = datetime.utcnow().isoformat()
        _container.upsert_item(item)
        return True
    except Exception as e:
        logging.error(f"Failed to update execution count for {instruction_id}: {e}")
        return False


def main(req: func.HttpRequest) -> func.HttpResponse:
    """Main handler for instruction management operations."""
    
    # Check if Cosmos DB is configured
    if not _container:
        return func.HttpResponse("Service not configured", status_code=500)
    
    # Extract user from request
    try:
        user_id = get_user_id_permissive(req)
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)
    
    method = req.method
    route_params = req.route_params
    instruction_id = route_params.get("instruction_id")
    
    try:
        # Create instruction
        if method == "POST" and not instruction_id:
            try:
                data = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON", status_code=400)
            
            created_id = _create_instruction(user_id, data)
            if created_id:
                return func.HttpResponse(
                    json.dumps({"id": created_id}),
                    status_code=201,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Failed to create instruction", status_code=400)
        
        # Get all instructions
        elif method == "GET" and not instruction_id:
            instructions = _get_user_instructions(user_id)
            return func.HttpResponse(
                json.dumps(instructions),
                status_code=200,
                mimetype="application/json"
            )
        
        # Get specific instruction
        elif method == "GET" and instruction_id:
            instruction = _get_instruction(user_id, instruction_id)
            if instruction:
                return func.HttpResponse(
                    json.dumps(instruction),
                    status_code=200,
                    mimetype="application/json"
                )
            else:
                return func.HttpResponse("Instruction not found", status_code=404)
        
        # Update instruction
        elif method == "PUT" and instruction_id:
            try:
                data = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON", status_code=400)
            
            success = _update_instruction(user_id, instruction_id, data)
            if success:
                return func.HttpResponse("Updated", status_code=200)
            else:
                return func.HttpResponse("Failed to update instruction", status_code=400)
        
        # Delete instruction
        elif method == "DELETE" and instruction_id:
            success = _delete_instruction(user_id, instruction_id)
            if success:
                return func.HttpResponse("Deleted", status_code=200)
            else:
                return func.HttpResponse("Failed to delete instruction", status_code=400)
        
        # Increment execution count (internal use)
        elif method == "POST" and instruction_id and req.params.get("action") == "increment":
            success = _increment_execution_count(user_id, instruction_id)
            if success:
                return func.HttpResponse("Updated", status_code=200)
            else:
                return func.HttpResponse("Failed to update", status_code=400)
        
        else:
            return func.HttpResponse("Invalid request", status_code=400)
    
    except Exception as e:
        logging.error(f"Error in instruction manager: {e}")
        return func.HttpResponse(f"Internal error: {str(e)}", status_code=500)
