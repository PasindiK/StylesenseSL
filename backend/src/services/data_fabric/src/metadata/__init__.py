"""Metadata catalog layer for Data Fabric.

Handles metadata management including:
- Data catalog and discovery
- Data lineage tracking
- Schema management
- Metadata versioning
"""

from .catalog import MetadataCatalog, DataAsset, DatasetMetadata
from .lineage import LineageTracker, LineageNode, DataLineage
from .registry import MetadataRegistry

__all__ = [
    "MetadataCatalog",
    "DataAsset",
    "DatasetMetadata",
    "LineageTracker",
    "LineageNode",
    "DataLineage",
    "MetadataRegistry",
]
