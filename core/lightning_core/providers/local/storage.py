"""
Local file-based storage provider implementation.

Uses SQLite for structured data and file system for documents.
"""

import os
import json
import sqlite3
import asyncio
from typing import Any, Dict, List, Optional, Type, TypeVar
from datetime import datetime
from pathlib import Path
import aiosqlite
import uuid

from lightning_core.abstractions.storage import StorageProvider, DocumentStore, Document


T = TypeVar("T", bound=Document)


class LocalDocumentStore(DocumentStore[T]):
    """SQLite-based document store implementation."""
    
    def __init__(
        self,
        db_path: str,
        table_name: str,
        document_type: Type[T]
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.document_type = document_type
        self._initialized = False
    
    async def _ensure_initialized(self) -> None:
        """Ensure the table exists."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    partition_key TEXT,
                    data TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    etag TEXT,
                    UNIQUE(id, partition_key)
                )
            """)
            await db.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_partition 
                ON {self.table_name}(partition_key)
            """)
            await db.commit()
        
        self._initialized = True
    
    async def create(self, document: T) -> T:
        """Create a new document."""
        await self._ensure_initialized()
        
        document.updated_at = datetime.utcnow()
        document.etag = str(uuid.uuid4())
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"""
                INSERT INTO {self.table_name} 
                (id, partition_key, data, created_at, updated_at, etag)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                document.id,
                document.partition_key,
                json.dumps(document.data),
                document.created_at.isoformat(),
                document.updated_at.isoformat(),
                document.etag
            ))
            await db.commit()
        
        return document
    
    async def read(self, id: str, partition_key: Optional[str] = None) -> Optional[T]:
        """Read a document by ID."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.db_path) as db:
            if partition_key is not None:
                cursor = await db.execute(
                    f"SELECT * FROM {self.table_name} WHERE id = ? AND partition_key = ?",
                    (id, partition_key)
                )
            else:
                cursor = await db.execute(
                    f"SELECT * FROM {self.table_name} WHERE id = ?",
                    (id,)
                )
            
            row = await cursor.fetchone()
            if row:
                return self._row_to_document(row)
        
        return None
    
    async def update(self, document: T) -> T:
        """Update an existing document."""
        await self._ensure_initialized()
        
        document.updated_at = datetime.utcnow()
        document.etag = str(uuid.uuid4())
        
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute(f"""
                UPDATE {self.table_name}
                SET data = ?, updated_at = ?, etag = ?
                WHERE id = ? AND partition_key = ?
            """, (
                json.dumps(document.data),
                document.updated_at.isoformat(),
                document.etag,
                document.id,
                document.partition_key
            ))
            await db.commit()
            
            if result.rowcount == 0:
                raise ValueError(f"Document not found: {document.id}")
        
        return document
    
    async def delete(self, id: str, partition_key: Optional[str] = None) -> bool:
        """Delete a document by ID."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.db_path) as db:
            if partition_key is not None:
                result = await db.execute(
                    f"DELETE FROM {self.table_name} WHERE id = ? AND partition_key = ?",
                    (id, partition_key)
                )
            else:
                result = await db.execute(
                    f"DELETE FROM {self.table_name} WHERE id = ?",
                    (id,)
                )
            await db.commit()
            
            return result.rowcount > 0
    
    async def query(
        self,
        query: Dict[str, Any],
        partition_key: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[T]:
        """Query documents based on criteria."""
        await self._ensure_initialized()
        
        # Build WHERE clause from query dict
        where_clauses = []
        params = []
        
        if partition_key is not None:
            where_clauses.append("partition_key = ?")
            params.append(partition_key)
        
        # Simple query implementation - matches JSON fields
        for key, value in query.items():
            where_clauses.append(f"json_extract(data, '$.{key}') = ?")
            params.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        limit_sql = f"LIMIT {max_items}" if max_items else ""
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT * FROM {self.table_name} WHERE {where_sql} {limit_sql}",
                params
            )
            rows = await cursor.fetchall()
            
            return [self._row_to_document(row) for row in rows]
    
    async def list_all(
        self,
        partition_key: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[T]:
        """List all documents in the store."""
        await self._ensure_initialized()
        
        async with aiosqlite.connect(self.db_path) as db:
            if partition_key is not None:
                cursor = await db.execute(
                    f"SELECT * FROM {self.table_name} WHERE partition_key = ? LIMIT ?",
                    (partition_key, max_items or -1)
                )
            else:
                cursor = await db.execute(
                    f"SELECT * FROM {self.table_name} LIMIT ?",
                    (max_items or -1,)
                )
            
            rows = await cursor.fetchall()
            return [self._row_to_document(row) for row in rows]
    
    def _row_to_document(self, row: tuple) -> T:
        """Convert a database row to a document."""
        doc = self.document_type()
        doc.id = row[0]
        doc.partition_key = row[1]
        doc.data = json.loads(row[2])
        doc.created_at = datetime.fromisoformat(row[3])
        doc.updated_at = datetime.fromisoformat(row[4])
        doc.etag = row[5]
        return doc


class LocalStorageProvider(StorageProvider):
    """Local file-based storage provider."""
    
    def __init__(
        self,
        path: str = "./data",
        **kwargs: Any
    ):
        self.base_path = Path(path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._stores: Dict[str, LocalDocumentStore] = {}
    
    def get_document_store(self, container_name: str, document_type: Type[T]) -> DocumentStore[T]:
        """Get a document store for a specific container/collection."""
        if container_name not in self._stores:
            db_path = self.base_path / f"{container_name}.db"
            self._stores[container_name] = LocalDocumentStore(
                str(db_path),
                "documents",
                document_type
            )
        return self._stores[container_name]
    
    async def initialize(self) -> None:
        """Initialize the storage provider."""
        # Ensure base directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def close(self) -> None:
        """Close storage provider connections."""
        # SQLite connections are closed automatically
        pass
    
    async def create_container_if_not_exists(
        self,
        container_name: str,
        partition_key_path: str = "/partition_key"
    ) -> None:
        """Create a container/collection if it doesn't exist."""
        # For local storage, just ensure the database file will be created
        db_path = self.base_path / f"{container_name}.db"
        # The actual table creation happens in LocalDocumentStore._ensure_initialized
    
    async def delete_container(self, container_name: str) -> None:
        """Delete a container/collection."""
        db_path = self.base_path / f"{container_name}.db"
        if db_path.exists():
            db_path.unlink()
        
        if container_name in self._stores:
            del self._stores[container_name]
    
    async def container_exists(self, container_name: str) -> bool:
        """Check if a container/collection exists."""
        db_path = self.base_path / f"{container_name}.db"
        return db_path.exists()