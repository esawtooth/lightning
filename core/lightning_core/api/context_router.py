"""
Context Hub API router for Lightning Core.

Provides proxy endpoints to the Context Hub service for managing
user context, documents, and folders.
"""

import os
from typing import Any, Dict, List, Optional
import logging
import asyncio
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel

from lightning_core.llm import get_completions_api
from lightning_core.abstractions.llm import Message, MessageRole
from lightning_core.abstractions import EventMessage
from lightning_core.runtime import get_runtime
from lightning_core.events.models import (
    FolderCreatedEvent,
    IndexGuideGenerationEvent,
    IndexGuideGeneratedEvent
)

# Context Hub service URL
CONTEXT_HUB_URL = os.getenv("CONTEXT_HUB_URL", "http://context-hub:3000")

router = APIRouter(prefix="/context", tags=["context"])
logger = logging.getLogger(__name__)


async def get_user_id(
    x_user_id: Optional[str] = Header(None, description="User ID header"),
    authorization: Optional[str] = Header(None, description="Authorization header"),
) -> str:
    """Get user ID from headers or use default."""
    # For now, always use default_user to match context-hub's behavior
    # TODO: Fix context-hub to properly handle user-specific documents
    return "default_user"


class FolderCreate(BaseModel):
    """Folder creation request."""
    name: str
    parent_id: Optional[str] = None


class DocumentCreate(BaseModel):
    """Document creation request."""
    name: str
    content: str
    folder_id: Optional[str] = None
    doc_type: Optional[str] = None


class ContextStatus(BaseModel):
    """Context hub status response."""
    initialized: bool
    document_count: int
    folder_count: int


async def proxy_to_context_hub(
    method: str,
    path: str,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Proxy a request to the Context Hub service."""
    url = f"{CONTEXT_HUB_URL}{path}"
    
    # Ensure we have headers dict and add X-User-Id
    if headers is None:
        headers = {}
    
    # Use provided user_id or default
    headers["X-User-Id"] = user_id or "default_user"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                json=json,
                params=params,
                headers=headers,
                timeout=30.0,
            )
            
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text,
                )
            
            # Handle empty responses (like 204 No Content)
            if response.status_code == 204 or not response.text:
                return {}
            
            return response.json()
            
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Context Hub service unavailable: {str(e)}",
            )


@router.get("/status", response_model=ContextStatus)
async def get_context_status(user_id: str = Depends(get_user_id)):
    """Get the status of the user's context hub."""
    try:
        # Get all documents to count folders and documents
        result = await proxy_to_context_hub("GET", "/docs", user_id=user_id)
        # Context-hub returns a list directly, not wrapped in an object
        docs = result if isinstance(result, list) else result.get("docs", [])
        
        # Count folders and documents
        folder_count = sum(1 for doc in docs if doc.get("doc_type") == "Folder")
        document_count = sum(1 for doc in docs if doc.get("doc_type") != "Folder")
        
        return ContextStatus(
            initialized=True,
            document_count=document_count,
            folder_count=folder_count,
        )
    except Exception as e:
        # If there's an error, assume not initialized
        import logging
        logging.error(f"Error getting context status: {e}")
        return ContextStatus(
            initialized=False,
            document_count=0,
            folder_count=0,
        )


@router.post("/initialize")
async def initialize_context():
    """Initialize the user's context hub."""
    # For now, return success since initialization may be automatic
    return {"status": "initialized"}


@router.get("/folders")
async def get_folders(user_id: str = Depends(get_user_id)):
    """Get all folders and root-level documents in the user's context hub with hierarchical structure."""
    try:
        result = await proxy_to_context_hub("GET", "/docs", user_id=user_id)
        # Context-hub returns a list directly, not wrapped in an object
        docs = result if isinstance(result, list) else result.get("docs", [])
        
        logger.info(f"Got {len(docs)} total documents from context hub")
        
        # Filter for folders and build hierarchy
        all_folders = [doc for doc in docs if doc.get("doc_type") == "Folder"]
        
        # Get root-level documents (documents without a parent folder)
        root_documents = [
            doc for doc in docs 
            if doc.get("doc_type") != "Folder" and not doc.get("parent_folder_id")
        ]
        
        # Build folder hierarchy with document counts
        def build_folder_tree(parent_id=None, level=0):
            tree = []
            for folder in all_folders:
                folder_parent_id = folder.get("parent_folder_id")
                if folder_parent_id == parent_id:
                    folder_id = folder.get("id")
                    
                    # Map parent_folder_id to parent_id for frontend compatibility
                    if "parent_folder_id" in folder:
                        folder["parent_id"] = folder["parent_folder_id"]
                    
                    # Get documents in this folder
                    folder_docs = [
                        doc for doc in docs 
                        if doc.get("parent_folder_id") == folder_id and doc.get("doc_type") != "Folder"
                    ]
                    
                    # Debug logging for new folders
                    if "Test Folder" in folder.get("name", ""):
                        logger.info(f"Processing {folder.get('name')} (ID: {folder_id})")
                        logger.info(f"  Total docs in folder: {len(folder_docs)}")
                        for doc in folder_docs:
                            logger.info(f"  - Doc: {doc.get('name')} (Type: {doc.get('doc_type')})")
                    
                    if folder.get("name") == "Machine Learning Projects":
                        logger.info(f"ML Projects folder has {len(folder_docs)} documents")
                        for doc in folder_docs:
                            logger.info(f"  - {doc.get('name')} ({doc.get('doc_type')})")
                    
                    # Find Index Guide for this folder
                    index_guide_content = None
                    index_guide_id = None
                    for doc in folder_docs:
                        if doc.get("name") == "Index Guide" or doc.get("doc_type") == "IndexGuide":
                            index_guide_id = doc.get("id")
                            logger.debug(f"Found Index Guide {index_guide_id} for folder {folder_id}")
                            break
                    
                    # If no Index Guide found in folder_docs, try checking all docs
                    # This is a workaround for context-hub not returning IndexGuide type docs
                    if not index_guide_id:
                        for doc in docs:
                            if (doc.get("parent_folder_id") == folder_id and 
                                (doc.get("name") == "Index Guide" or doc.get("doc_type") == "IndexGuide")):
                                index_guide_id = doc.get("id")
                                logger.info(f"Found Index Guide {index_guide_id} for folder {folder_id} in all docs")
                                break
                    
                    # Store the Index Guide ID for later fetching
                    folder["index_guide_id"] = index_guide_id
                    
                    # Filter out Index Guide from regular documents
                    folder["documents"] = [
                        doc for doc in folder_docs
                        if doc.get("name") != "Index Guide" and doc.get("doc_type") != "IndexGuide"
                    ]
                    folder["document_count"] = len(folder["documents"])
                    folder["level"] = level
                    folder["index_guide"] = index_guide_content
                    
                    # Get subfolders recursively
                    folder["subfolders"] = build_folder_tree(folder_id, level + 1)
                    
                    tree.append(folder)
            return tree
        
        # Build the hierarchical tree starting from root folders (no parent)
        folder_tree = build_folder_tree()
        
        # Add a virtual "root" folder for root-level documents if there are any
        if root_documents:
            root_folder = {
                "id": "root",
                "name": "Root Documents", 
                "doc_type": "Folder",
                "parent_id": None,
                "documents": root_documents,
                "document_count": len(root_documents),
                "level": 0,
                "subfolders": []
            }
            folder_tree.append(root_folder)
        
        # Flatten the tree for easier frontend consumption while preserving hierarchy info
        def flatten_tree(tree, flat_list=None):
            if flat_list is None:
                flat_list = []
            
            for folder in tree:
                flat_list.append(folder)
                if folder.get("subfolders"):
                    flatten_tree(folder["subfolders"], flat_list)
            
            return flat_list
        
        flattened_folders = flatten_tree(folder_tree)
        
        return {"folders": flattened_folders, "tree": folder_tree}
    except Exception as e:
        return {"folders": [], "tree": [], "error": str(e)}


async def _gather_folder_hierarchy(folder_id: Optional[str], user_id: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Gather the folder hierarchy and Index Guides for context.
    
    Returns a dict with:
    - path: List of folder names from root to target
    - index_guides: List of Index Guide contents in hierarchy order
    """
    if not folder_id:
        return {"path": ["Root"], "index_guides": []}
    
    try:
        # Get all documents to find the folder hierarchy
        result = await proxy_to_context_hub("GET", "/docs", headers=headers, user_id=user_id)
        docs = result if isinstance(result, list) else result.get("docs", [])
        
        # Build folder lookup
        folders_by_id = {}
        for doc in docs:
            if doc.get("doc_type") == "Folder":
                folders_by_id[doc["id"]] = doc
        
        # Build path from folder to root
        path = []
        index_guides = []
        current_id = folder_id
        
        while current_id:
            if current_id not in folders_by_id:
                break
                
            folder = folders_by_id[current_id]
            path.append(folder["name"])
            
            # Find Index Guide for this folder
            for doc in docs:
                if (doc.get("parent_folder_id") == current_id and 
                    (doc.get("name") == "Index Guide" or doc.get("doc_type") == "IndexGuide")):
                    # Fetch full content
                    guide_doc = await proxy_to_context_hub("GET", f"/docs/{doc['id']}", headers=headers, user_id=user_id)
                    if guide_doc and guide_doc.get("content"):
                        index_guides.append(guide_doc["content"])
                    break
            
            current_id = folder.get("parent_folder_id")
        
        # Reverse to get root-to-folder order
        path.reverse()
        index_guides.reverse()
        
        # Add root if not already there
        if not path or path[0] != "Root":
            path.insert(0, "Root")
        
        return {"path": path, "index_guides": index_guides}
    except Exception as e:
        logger.error(f"Error gathering folder hierarchy: {e}")
        return {"path": ["Root"], "index_guides": []}


@router.post("/folders", status_code=201)
async def create_folder(folder: FolderCreate, user_id: str = Depends(get_user_id)):
    """Create a new folder in the user's context hub."""
    # Folders are created as documents with type "Folder"
    doc_data = {
        "name": folder.name,
        "content": "",  # Folders have empty content
        "parent_folder_id": folder.parent_id,
        "doc_type": "Folder"
    }
    
    # Create the folder
    folder_response = await proxy_to_context_hub(
        "POST",
        "/docs",
        json=doc_data,
        user_id=user_id,
    )
    
    # Use event-driven approach for Index Guide generation
    if folder_response and "id" in folder_response:
        folder_id = folder_response["id"]
        folder_name = folder_response.get("name", folder.name)
        
        logger.info(f"Starting event-driven Index Guide creation for folder {folder_id} ({folder_name})")
        
        try:
            # Get runtime instance
            runtime = get_runtime()
            if not runtime:
                logger.warning("Runtime not available, falling back to direct generation")
                # Fall back to creating a simple index guide directly
                await _create_simple_index_guide(folder_id, folder_name, user_id)
                return folder_response
            
            logger.info(f"Runtime available: {runtime}")
            logger.info(f"Event bus available: {runtime.event_bus if runtime else 'No runtime'}")
            
            # Gather folder hierarchy for context
            hierarchy = await _gather_folder_hierarchy(folder.parent_id, user_id)
            
            # Get parent folders and sibling folders for context
            parent_folders = hierarchy["path"] if hierarchy["path"] else []
            
            # Get sibling folders (other folders in the same parent)
            sibling_folders = []
            if folder.parent_id:
                try:
                    parent_contents = await proxy_to_context_hub(
                        "GET",
                        f"/folders/{folder.parent_id}",
                        user_id=user_id,
                    )
                    if parent_contents and "children" in parent_contents:
                        sibling_folders = [
                            child["name"] for child in parent_contents["children"]
                            if child.get("doc_type") == "Folder" and child["id"] != folder_id
                        ]
                except Exception as e:
                    logger.debug(f"Could not get sibling folders: {e}")
            
            # For now, since the event-driven approach requires more setup,
            # let's use the direct LLM approach but emit events for tracking
            logger.info("Using direct LLM generation for index guide")
            
            # Emit folder creation tracking event
            folder_created_event = FolderCreatedEvent(
                data={
                    "folder_id": folder_id,
                    "folder_name": folder_name,
                    "parent_id": folder.parent_id,
                    "parent_folders": parent_folders,
                    "sibling_folders": sibling_folders
                },
                source="context_api",
                user_id=user_id
            )
            
            # Publish the event for tracking
            try:
                await runtime.event_bus.publish(folder_created_event)
                logger.info(f"Published folder creation event for {folder_name}")
            except Exception as e:
                logger.error(f"Failed to publish folder creation event: {e}")
            
            # Generate index guide using direct LLM call
            try:
                # Build prompt with context
                prompt = f"""Generate an index guide for the folder: '{folder_name}'
Full path: {"/".join(parent_folders + [folder_name])}"""
                
                if parent_folders:
                    prompt += f"\nParent folders: {', '.join(parent_folders)}"
                
                if sibling_folders:
                    prompt += f"\nSibling folders: {', '.join(sibling_folders[:10])}"
                
                prompt += "\n\nCreate a comprehensive, practical index guide for this folder."
                
                # Generate using LLM
                from lightning_core.llm import get_completions_api
                from lightning_core.abstractions.llm import Message, MessageRole
                
                completions_api = get_completions_api()
                response = await completions_api.create(
                    model="gpt-4o-mini",
                    messages=[
                        Message(role=MessageRole.SYSTEM, content="""You are an expert at creating helpful index guides for folders in a personal knowledge management system.

Create index guides that:
- Start with a clear purpose statement for the folder
- Provide specific organization guidelines relevant to the folder's content
- Include best practices that make sense for this type of content
- Consider the folder's relationship to parent and sibling folders
- Make recommendations concrete and actionable
- Use markdown formatting with proper headers"""),
                        Message(role=MessageRole.USER, content=prompt)
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
                
                index_guide_content = response.choices[0].message.content
                logger.info(f"Generated index guide with {len(index_guide_content)} characters")
                
            except Exception as e:
                logger.error(f"Failed to generate index guide: {e}")
                index_guide_content = None
            
            # Use generated content or fall back to template
            if not index_guide_content:
                logger.info("No index guide content received, using template")
                index_guide_content = f"""# {folder_name}

## Purpose
This folder is for organizing your {folder_name.lower()} content.

## Organization Guidelines
- Keep related documents together
- Use descriptive names for your files
- Consider creating subfolders for better organization
- Update documents regularly to keep information current

## Best Practices
- Add dates to time-sensitive documents
- Use consistent naming conventions
- Include relevant keywords for easy searching
- Regular review and cleanup of outdated content
"""
            else:
                logger.info(f"Received LLM-generated index guide with {len(index_guide_content)} characters")
            
            # Create the Index Guide document
            index_guide_data = {
                "name": "Index Guide",
                "content": index_guide_content,
                "parent_folder_id": folder_id,
                "doc_type": "IndexGuide"
            }
            
            logger.info(f"Creating Index Guide for folder {folder_id}")
            
            index_guide_response = await proxy_to_context_hub(
                "POST",
                "/docs",
                json=index_guide_data,
                user_id=user_id,
            )
            
            logger.info(f"Index Guide creation response: {index_guide_response}")
            
        except Exception as e:
            logger.error(f"Error in event-driven index guide creation: {e}", exc_info=True)
            # Fall back to simple creation
            await _create_simple_index_guide(folder_id, folder_name, user_id)
    
    return folder_response


async def _create_simple_index_guide(folder_id: str, folder_name: str, user_id: str):
    """Create a simple index guide when event system is not available."""
    try:
        index_guide_content = f"""# {folder_name}

## Purpose
This folder is for organizing your {folder_name.lower()} content.

## Organization Guidelines
- Keep related documents together
- Use descriptive names for your files
- Consider creating subfolders for better organization
- Update documents regularly to keep information current

## Best Practices
- Add dates to time-sensitive documents
- Use consistent naming conventions
- Include relevant keywords for easy searching
- Regular review and cleanup of outdated content
"""
        
        index_guide_data = {
            "name": "Index Guide",
            "content": index_guide_content,
            "parent_folder_id": folder_id,
            "doc_type": "IndexGuide"
        }
        
        await proxy_to_context_hub(
            "POST",
            "/docs",
            json=index_guide_data,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"Failed to create simple index guide: {e}")


@router.get("/search")
async def search_context(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, description="Maximum number of results"),
):
    """Search documents in the user's context hub."""
    return await proxy_to_context_hub(
        "GET",
        "/search",
        params={"q": q, "limit": limit},
    )


@router.post("/documents", status_code=201)
async def create_document(document: DocumentCreate, user_id: str = Depends(get_user_id)):
    """Create a new document in the user's context hub."""
    doc_data = {
        "name": document.name,
        "content": document.content,
        "parent_folder_id": document.folder_id,
        "doc_type": document.doc_type or "Text"
    }
    return await proxy_to_context_hub(
        "POST",
        "/docs",
        json=doc_data,
        user_id=user_id,
    )


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    format: str = Query(None, description="Format for document content (e.g., 'numbered')"),
    user_id: str = Depends(get_user_id),
):
    """Get a specific document from the user's context hub."""
    params = {}
    if format:
        params["format"] = format
    return await proxy_to_context_hub("GET", f"/docs/{document_id}", params=params, user_id=user_id)


class DocumentUpdate(BaseModel):
    """Document update request."""
    content: str


class DocumentPatch(BaseModel):
    """Document patch request."""
    patch: str


@router.put("/documents/{document_id}")
async def update_document(document_id: str, update: DocumentUpdate, user_id: str = Depends(get_user_id)):
    """Update a document in the user's context hub."""
    return await proxy_to_context_hub(
        "PUT",
        f"/docs/{document_id}",
        json={"content": update.content},
        user_id=user_id,
    )


@router.patch("/documents/{document_id}")
async def patch_document(document_id: str, patch: DocumentPatch):
    """Apply a patch to a document in the user's context hub."""
    return await proxy_to_context_hub(
        "PATCH",
        f"/docs/{document_id}",
        json={"patch": patch.patch},
    )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document from the user's context hub."""
    return await proxy_to_context_hub("DELETE", f"/docs/{document_id}")


@router.patch("/documents/{document_id}")
async def rename_document(document_id: str, update: Dict[str, Any]):
    """Rename a document in the user's context hub."""
    return await proxy_to_context_hub(
        "PUT",
        f"/docs/{document_id}",
        json={"name": update.get("name"), "content": update.get("content")},
    )


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str):
    """Delete a folder from the user's context hub."""
    # Folders are just documents with type "Folder", so use the same endpoint
    return await proxy_to_context_hub("DELETE", f"/docs/{folder_id}")


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: str, update: Dict[str, Any]):
    """Update a folder in the user's context hub."""
    # Folders are just documents with type "Folder", so use the same endpoint
    return await proxy_to_context_hub(
        "PUT",
        f"/docs/{folder_id}",
        json={"name": update.get("name"), "content": update.get("content", "")},
    )


@router.get("/folders/{folder_id}/guide")
async def get_folder_guide(folder_id: str):
    """Get the Index Guide for a specific folder."""
    try:
        # Get all documents
        result = await proxy_to_context_hub("GET", "/docs")
        docs = result if isinstance(result, list) else result.get("docs", [])
        
        # Find documents in this folder
        folder_docs = [
            doc for doc in docs 
            if doc.get("parent_folder_id") == folder_id
        ]
        
        # Find the Index Guide
        for doc in folder_docs:
            if doc.get("name") == "Index Guide" or doc.get("doc_type") == "IndexGuide":
                # Fetch full document content
                guide_doc = await proxy_to_context_hub("GET", f"/docs/{doc['id']}")
                return {"content": guide_doc.get("content", "")}
        
        return {"content": ""}
    except Exception as e:
        return {"content": "", "error": str(e)}


# Timeline endpoints for the enhanced context view
@router.get("/timeline/snapshots")
async def get_timeline_snapshots():
    """Get timeline snapshots from the context hub."""
    return await proxy_to_context_hub("GET", "/api/timeline/snapshots")


@router.get("/timeline/events")
async def get_timeline_events(
    start: Optional[str] = Query(None, description="Start timestamp"),
    end: Optional[str] = Query(None, description="End timestamp"),
    limit: int = Query(100, description="Maximum number of events"),
):
    """Get timeline events from the context hub."""
    params = {"limit": limit}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    
    return await proxy_to_context_hub(
        "GET",
        "/api/timeline/events",
        params=params,
    )