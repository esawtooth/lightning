"""
Context Hub API router for Lightning Core.

Provides proxy endpoints to the Context Hub service for managing
user context, documents, and folders.
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

# Context Hub service URL
CONTEXT_HUB_URL = os.getenv("CONTEXT_HUB_URL", "http://context-hub:3000")

router = APIRouter(prefix="/context", tags=["context"])


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
) -> Dict[str, Any]:
    """Proxy a request to the Context Hub service."""
    url = f"{CONTEXT_HUB_URL}{path}"
    
    # Ensure we have headers dict and add X-User-Id
    if headers is None:
        headers = {}
    # TODO: Get actual user ID from auth context
    headers["X-User-Id"] = "demo-user"
    
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
async def get_context_status():
    """Get the status of the user's context hub."""
    try:
        # Get all documents to count folders and documents
        result = await proxy_to_context_hub("GET", "/docs")
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
async def get_folders():
    """Get all folders in the user's context hub."""
    # Get all documents with type "Folder"
    try:
        result = await proxy_to_context_hub("GET", "/docs")
        # Context-hub returns a list directly, not wrapped in an object
        docs = result if isinstance(result, list) else result.get("docs", [])
        
        # Filter for folders and build hierarchy
        folders = [doc for doc in docs if doc.get("doc_type") == "Folder"]
        
        # Add document count to each folder and normalize fields
        for folder in folders:
            folder_id = folder.get("id")
            # Map parent_folder_id to parent_id for frontend compatibility
            if "parent_folder_id" in folder:
                folder["parent_id"] = folder["parent_folder_id"]
            folder["documents"] = [
                doc for doc in docs 
                if doc.get("parent_folder_id") == folder_id and doc.get("doc_type") != "Folder"
            ]
            folder["document_count"] = len(folder["documents"])
        
        return {"folders": folders}
    except Exception as e:
        return {"folders": [], "error": str(e)}


@router.post("/folders", status_code=201)
async def create_folder(folder: FolderCreate):
    """Create a new folder in the user's context hub."""
    # Folders are created as documents with type "Folder"
    doc_data = {
        "name": folder.name,
        "content": "",  # Folders have empty content
        "parent_folder_id": folder.parent_id,
        "doc_type": "Folder"
    }
    return await proxy_to_context_hub(
        "POST",
        "/docs",
        json=doc_data,
    )


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
async def create_document(document: DocumentCreate):
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
    )


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    format: str = Query(None, description="Format for document content (e.g., 'numbered')")
):
    """Get a specific document from the user's context hub."""
    params = {}
    if format:
        params["format"] = format
    return await proxy_to_context_hub("GET", f"/docs/{document_id}", params=params)


class DocumentUpdate(BaseModel):
    """Document update request."""
    content: str


class DocumentPatch(BaseModel):
    """Document patch request."""
    patch: str


@router.put("/documents/{document_id}")
async def update_document(document_id: str, update: DocumentUpdate):
    """Update a document in the user's context hub."""
    return await proxy_to_context_hub(
        "PUT",
        f"/docs/{document_id}",
        json={"content": update.content},
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