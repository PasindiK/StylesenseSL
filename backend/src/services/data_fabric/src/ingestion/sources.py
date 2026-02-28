"""Data source definitions and registry."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class SourceType(str, Enum):
    """Supported data source types."""

    CSV = "csv"
    PARQUET = "parquet"
    DATABASE = "database"
    API = "api"
    S3 = "s3"
    KAFKA = "kafka"


@dataclass
class DataSource:
    """Data source configuration."""

    id: str
    name: str
    source_type: SourceType
    connection_string: str
    schema_name: Optional[str] = None
    credentials: Dict[str, Any] = field(default_factory=dict)
    partition_by: Optional[str] = None
    incremental: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type.value,
            "connection_string": self.connection_string,
            "schema_name": self.schema_name,
            "partition_by": self.partition_by,
            "incremental": self.incremental,
        }


class SourceRegistry:
    """Registry for managing data sources."""

    def __init__(self):
        """Initialize the registry."""
        self.sources: Dict[str, DataSource] = {}

    def register(self, source: DataSource) -> None:
        """Register a data source."""
        self.sources[source.id] = source

    def get(self, source_id: str) -> Optional[DataSource]:
        """Get a data source by ID."""
        return self.sources.get(source_id)

    def list_sources(self) -> list[DataSource]:
        """List all registered sources."""
        return list(self.sources.values())

    def unregister(self, source_id: str) -> bool:
        """Unregister a data source."""
        if source_id in self.sources:
            del self.sources[source_id]
            return True
        return False
