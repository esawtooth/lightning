"""
Storage abstraction layer for Lightning Core.

Provides abstract base classes for storage operations,
supporting both cloud (e.g., Cosmos DB) and local implementations.
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from .health import HealthCheckable, HealthCheckResult, HealthStatus


@dataclass
class Document:
    """Base document class for storage operations."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    partition_key: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    etag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary."""
        return {
            "id": self.id,
            "partition_key": self.partition_key,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "etag": self.etag,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Create document from dictionary."""
        doc = cls()
        doc.id = data.get("id", doc.id)
        doc.partition_key = data.get("partition_key", "")
        doc.data = data.get("data", {})

        if "created_at" in data:
            doc.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            doc.updated_at = datetime.fromisoformat(data["updated_at"])

        doc.etag = data.get("etag")
        return doc


T = TypeVar("T", bound=Document)


class DocumentStore(ABC, Generic[T]):
    """Abstract base class for document storage operations."""

    @abstractmethod
    async def create(self, document: T) -> T:
        """Create a new document."""
        pass

    @abstractmethod
    async def read(self, id: str, partition_key: Optional[str] = None) -> Optional[T]:
        """Read a document by ID."""
        pass

    @abstractmethod
    async def update(self, document: T) -> T:
        """Update an existing document."""
        pass

    @abstractmethod
    async def delete(self, id: str, partition_key: Optional[str] = None) -> bool:
        """Delete a document by ID."""
        pass

    @abstractmethod
    async def query(
        self,
        query: Dict[str, Any],
        partition_key: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> List[T]:
        """Query documents based on criteria."""
        pass

    @abstractmethod
    async def list_all(
        self, partition_key: Optional[str] = None, max_items: Optional[int] = None
    ) -> List[T]:
        """List all documents in the store."""
        pass


class StorageProvider(ABC, HealthCheckable):
    """Abstract base class for storage provider implementations."""

    @abstractmethod
    def get_document_store(
        self, container_name: str, document_type: type[T]
    ) -> DocumentStore[T]:
        """Get a document store for a specific container/collection."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage provider."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close storage provider connections."""
        pass

    @abstractmethod
    async def create_container_if_not_exists(
        self, container_name: str, partition_key_path: str = "/partition_key"
    ) -> None:
        """Create a container/collection if it doesn't exist."""
        pass

    @abstractmethod
    async def delete_container(self, container_name: str) -> None:
        """Delete a container/collection."""
        pass

    @abstractmethod
    async def container_exists(self, container_name: str) -> bool:
        """Check if a container/collection exists."""
        pass
    
    async def health_check(self) -> HealthCheckResult:
        """
        Default health check implementation for storage providers.
        Providers should override this for specific health checks.
        """
        start_time = time.time()
        try:
            # Try to check if a system container exists as a basic health check
            await self.container_exists("_health_check")
            latency_ms = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                details={"check_type": "container_exists"}
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )

# Backwards compatibility: expose ProviderFactory here
try:
    from .factory import ProviderFactory  # type: ignore
except Exception:  # pragma: no cover - avoid circular import at startup
    ProviderFactory = None
