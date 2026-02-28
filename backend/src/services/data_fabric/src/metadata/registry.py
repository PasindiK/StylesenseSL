"""Metadata registry and versioning."""

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MetadataVersion:
    """A version of metadata."""

    def __init__(self, version_number: int, metadata: Dict[str, Any], created_by: str):
        """Initialize metadata version.

        Args:
            version_number: Version number
            metadata: Metadata content
            created_by: User who created this version
        """
        self.version_number = version_number
        self.metadata = metadata
        self.created_by = created_by
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_number": self.version_number,
            "metadata": self.metadata,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }


class MetadataRegistry:
    """Registry for managing metadata and versions."""

    def __init__(self):
        """Initialize metadata registry."""
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
        self.version_history: Dict[str, List[MetadataVersion]] = {}
        self.current_versions: Dict[str, int] = {}

    def register_metadata(
        self, entity_id: str, metadata: Dict[str, Any], created_by: str
    ) -> None:
        """Register new metadata.

        Args:
            entity_id: Entity ID
            metadata: Metadata dictionary
            created_by: User creating this metadata
        """
        if entity_id not in self.metadata_store:
            self.metadata_store[entity_id] = {}
            self.version_history[entity_id] = []
            self.current_versions[entity_id] = 0

        version_number = self.current_versions[entity_id] + 1
        version = MetadataVersion(version_number, metadata, created_by)

        self.metadata_store[entity_id] = metadata
        self.version_history[entity_id].append(version)
        self.current_versions[entity_id] = version_number

        logger.info(f"Registered metadata for {entity_id}, version {version_number}")

    def get_metadata(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get current metadata.

        Args:
            entity_id: Entity ID

        Returns:
            Metadata dictionary or None
        """
        return self.metadata_store.get(entity_id)

    def get_metadata_version(self, entity_id: str, version: int) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific version.

        Args:
            entity_id: Entity ID
            version: Version number

        Returns:
            Metadata dictionary or None
        """
        if entity_id not in self.version_history:
            return None

        for v in self.version_history[entity_id]:
            if v.version_number == version:
                return v.metadata

        return None

    def get_version_history(self, entity_id: str) -> List[MetadataVersion]:
        """Get version history for an entity.

        Args:
            entity_id: Entity ID

        Returns:
            List of MetadataVersion objects
        """
        return self.version_history.get(entity_id, [])

    def update_metadata(
        self, entity_id: str, updates: Dict[str, Any], updated_by: str
    ) -> bool:
        """Update metadata.

        Args:
            entity_id: Entity ID
            updates: Updates to apply
            updated_by: User applying updates

        Returns:
            True if successful
        """
        if entity_id not in self.metadata_store:
            logger.warning(f"Entity {entity_id} not found")
            return False

        current_metadata = self.metadata_store[entity_id].copy()
        current_metadata.update(updates)

        self.register_metadata(entity_id, current_metadata, updated_by)
        logger.info(f"Updated metadata for {entity_id}")
        return True

    def compare_versions(self, entity_id: str, v1: int, v2: int) -> Dict[str, Any]:
        """Compare two versions of metadata.

        Args:
            entity_id: Entity ID
            v1: First version number
            v2: Second version number

        Returns:
            Dictionary with differences
        """
        metadata1 = self.get_metadata_version(entity_id, v1)
        metadata2 = self.get_metadata_version(entity_id, v2)

        if not metadata1 or not metadata2:
            return {"error": "Version not found"}

        added = {k: v for k, v in metadata2.items() if k not in metadata1}
        removed = {k: v for k, v in metadata1.items() if k not in metadata2}
        modified = {
            k: {"old": metadata1[k], "new": metadata2[k]}
            for k in metadata1
            if k in metadata2 and metadata1[k] != metadata2[k]
        }

        return {"added": added, "removed": removed, "modified": modified}
