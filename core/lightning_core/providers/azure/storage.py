"""
Azure Cosmos DB storage provider implementation.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar

from azure.cosmos import ContainerProxy, CosmosClient, exceptions
from azure.cosmos.partition_key import PartitionKey

from lightning_core.abstractions.storage import Document, DocumentStore, StorageProvider

T = TypeVar("T", bound=Document)


class CosmosDocumentStore(DocumentStore[T]):
    """Cosmos DB document store implementation."""

    def __init__(self, container: ContainerProxy, document_type: Type[T]):
        self.container = container
        self.document_type = document_type

    async def create(self, document: T) -> T:
        """Create a new document."""
        document.updated_at = datetime.utcnow()

        try:
            item = document.to_dict()
            # Cosmos DB requires 'id' field
            if "id" not in item:
                item["id"] = document.id

            response = self.container.create_item(
                body=item, enable_automatic_id_generation=False
            )

            # Update etag from response
            document.etag = response.get("_etag")
            return document

        except exceptions.CosmosResourceExistsError:
            raise ValueError(f"Document already exists: {document.id}")
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to create document: {e}")

    async def read(self, id: str, partition_key: Optional[str] = None) -> Optional[T]:
        """Read a document by ID."""
        try:
            if partition_key:
                response = self.container.read_item(
                    item=id, partition_key=partition_key
                )
            else:
                # Try to read without partition key (will fail if partitioned)
                response = self.container.read_item(item=id)

            doc = self.document_type.from_dict(response)
            doc.etag = response.get("_etag")
            return doc

        except exceptions.CosmosResourceNotFoundError:
            return None
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to read document: {e}")

    async def update(self, document: T) -> T:
        """Update an existing document."""
        document.updated_at = datetime.utcnow()

        try:
            item = document.to_dict()
            if "id" not in item:
                item["id"] = document.id

            # Use etag for optimistic concurrency if available
            access_condition = (
                {"type": "IfMatch", "condition": document.etag}
                if document.etag
                else None
            )

            response = self.container.replace_item(
                item=document.id, body=item, access_condition=access_condition
            )

            document.etag = response.get("_etag")
            return document

        except exceptions.CosmosResourceNotFoundError:
            raise ValueError(f"Document not found: {document.id}")
        except exceptions.CosmosAccessConditionFailedError:
            raise ValueError("Document was modified by another process")
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to update document: {e}")

    async def delete(self, id: str, partition_key: Optional[str] = None) -> bool:
        """Delete a document by ID."""
        try:
            if partition_key:
                self.container.delete_item(item=id, partition_key=partition_key)
            else:
                self.container.delete_item(item=id)
            return True

        except exceptions.CosmosResourceNotFoundError:
            return False
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to delete document: {e}")

    async def query(
        self,
        query: Dict[str, Any],
        partition_key: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> List[T]:
        """Query documents based on criteria."""
        # Build Cosmos DB SQL query from dict
        where_clauses = []
        parameters = []

        for i, (key, value) in enumerate(query.items()):
            param_name = f"@param{i}"
            if "." in key:
                # Support nested fields
                where_clauses.append(f"c.{key} = {param_name}")
            else:
                where_clauses.append(f"c.data.{key} = {param_name}")
            parameters.append({"name": param_name, "value": value})

        query_text = "SELECT * FROM c"
        if where_clauses:
            query_text += " WHERE " + " AND ".join(where_clauses)

        # Add OFFSET and LIMIT if specified
        if max_items:
            query_text += f" OFFSET 0 LIMIT {max_items}"

        # Execute query
        kwargs = {"query": query_text, "parameters": parameters}
        if partition_key:
            kwargs["partition_key"] = partition_key

        items = list(self.container.query_items(**kwargs))

        # Convert to documents
        documents = []
        for item in items:
            doc = self.document_type.from_dict(item)
            doc.etag = item.get("_etag")
            documents.append(doc)

        return documents

    async def list_all(
        self, partition_key: Optional[str] = None, max_items: Optional[int] = None
    ) -> List[T]:
        """List all documents in the store."""
        query = "SELECT * FROM c"
        if max_items:
            query += f" OFFSET 0 LIMIT {max_items}"

        kwargs = {"query": query}
        if partition_key:
            kwargs["partition_key"] = partition_key

        items = list(self.container.query_items(**kwargs))

        # Convert to documents
        documents = []
        for item in items:
            doc = self.document_type.from_dict(item)
            doc.etag = item.get("_etag")
            documents.append(doc)

        return documents


class CosmosStorageProvider(StorageProvider):
    """Azure Cosmos DB storage provider."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        endpoint: Optional[str] = None,
        key: Optional[str] = None,
        database_name: str = "lightning",
        **kwargs: Any,
    ):
        # Initialize Cosmos client
        if connection_string:
            self.client = CosmosClient.from_connection_string(connection_string)
        elif endpoint and key:
            self.client = CosmosClient(endpoint, key)
        else:
            # Try to get from environment
            conn_str = os.getenv("COSMOS_CONNECTION_STRING")
            if conn_str:
                self.client = CosmosClient.from_connection_string(conn_str)
            else:
                raise ValueError("Cosmos DB connection string or endpoint/key required")

        self.database_name = database_name
        self.database = None
        self._containers: Dict[str, ContainerProxy] = {}
        self._stores: Dict[str, CosmosDocumentStore] = {}

    def get_document_store(
        self, container_name: str, document_type: Type[T]
    ) -> DocumentStore[T]:
        """Get a document store for a specific container/collection."""
        if container_name not in self._stores:
            if container_name not in self._containers:
                raise ValueError(
                    f"Container {container_name} does not exist. Call create_container_if_not_exists first."
                )

            self._stores[container_name] = CosmosDocumentStore(
                self._containers[container_name], document_type
            )

        return self._stores[container_name]

    async def initialize(self) -> None:
        """Initialize the storage provider."""
        try:
            # Create database if it doesn't exist
            self.database = self.client.create_database_if_not_exists(
                id=self.database_name
            )
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to initialize Cosmos DB: {e}")

    async def close(self) -> None:
        """Close storage provider connections."""
        # Cosmos client doesn't need explicit closing
        pass

    async def create_container_if_not_exists(
        self, container_name: str, partition_key_path: str = "/partition_key"
    ) -> None:
        """Create a container/collection if it doesn't exist."""
        if not self.database:
            await self.initialize()

        try:
            container = self.database.create_container_if_not_exists(
                id=container_name,
                partition_key=PartitionKey(path=partition_key_path),
                offer_throughput=400,  # RU/s
            )
            self._containers[container_name] = container
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to create container: {e}")

    async def delete_container(self, container_name: str) -> None:
        """Delete a container/collection."""
        if not self.database:
            await self.initialize()

        try:
            self.database.delete_container(container_name)

            # Remove from caches
            if container_name in self._containers:
                del self._containers[container_name]
            if container_name in self._stores:
                del self._stores[container_name]

        except exceptions.CosmosResourceNotFoundError:
            pass
        except exceptions.CosmosHttpResponseError as e:
            raise RuntimeError(f"Failed to delete container: {e}")

    async def container_exists(self, container_name: str) -> bool:
        """Check if a container/collection exists."""
        if not self.database:
            await self.initialize()

        try:
            container = self.database.get_container_client(container_name)
            # Try to read container properties to verify it exists
            container.read()
            self._containers[container_name] = container
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False
        except exceptions.CosmosHttpResponseError:
            return False
