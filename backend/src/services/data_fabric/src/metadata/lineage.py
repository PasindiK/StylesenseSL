"""Data lineage tracking."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class LineageNode:
    """A node in the lineage graph."""

    id: str
    name: str
    node_type: str  # source, transformation, output
    timestamp: datetime


class DataLineage:
    """Data lineage information."""

    def __init__(self):
        """Initialize lineage."""
        self.nodes: Dict[str, LineageNode] = {}
        self.edges: List[tuple[str, str]] = []  # (source_id, target_id)

    def add_node(self, node: LineageNode) -> None:
        """Add a node to the lineage.

        Args:
            node: LineageNode to add
        """
        self.nodes[node.id] = node

    def add_edge(self, source_id: str, target_id: str) -> None:
        """Add an edge to the lineage.

        Args:
            source_id: Source node ID
            target_id: Target node ID
        """
        if (source_id, target_id) not in self.edges:
            self.edges.append((source_id, target_id))

    def get_upstream(self, node_id: str) -> Set[str]:
        """Get all upstream nodes."""
        upstream = set()
        to_visit = [node_id]

        while to_visit:
            current = to_visit.pop()
            for src, tgt in self.edges:
                if tgt == current and src not in upstream:
                    upstream.add(src)
                    to_visit.append(src)

        return upstream

    def get_downstream(self, node_id: str) -> Set[str]:
        """Get all downstream nodes."""
        downstream = set()
        to_visit = [node_id]

        while to_visit:
            current = to_visit.pop()
            for src, tgt in self.edges:
                if src == current and tgt not in downstream:
                    downstream.add(tgt)
                    to_visit.append(tgt)

        return downstream


class LineageTracker:
    """Track data lineage across the fabric."""

    def __init__(self):
        """Initialize lineage tracker."""
        self.lineages: Dict[str, DataLineage] = {}
        self.operation_lineages: Dict[str, DataLineage] = {}

    def create_lineage(self, lineage_id: str) -> DataLineage:
        """Create a new lineage.

        Args:
            lineage_id: Unique lineage ID

        Returns:
            New DataLineage
        """
        lineage = DataLineage()
        self.lineages[lineage_id] = lineage
        logger.info(f"Created lineage: {lineage_id}")
        return lineage

    def get_lineage(self, lineage_id: str) -> Optional[DataLineage]:
        """Get lineage by ID.

        Args:
            lineage_id: Lineage ID

        Returns:
            DataLineage or None
        """
        return self.lineages.get(lineage_id)

    def track_transformation(
        self,
        operation_id: str,
        source_asset_id: str,
        target_asset_id: str,
        operation_type: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Track a transformation operation.

        Args:
            operation_id: Unique operation ID
            source_asset_id: Source asset ID
            target_asset_id: Target asset ID
            operation_type: Type of operation
            metadata: Additional metadata
        """
        lineage = self.operation_lineages.get(
            target_asset_id, self.create_operation_lineage(target_asset_id)
        )

        # Add nodes
        source_node = LineageNode(
            id=source_asset_id,
            name=f"Source: {source_asset_id}",
            node_type="source",
            timestamp=datetime.now(),
        )
        operation_node = LineageNode(
            id=operation_id,
            name=f"Operation: {operation_type}",
            node_type="transformation",
            timestamp=datetime.now(),
        )
        target_node = LineageNode(
            id=target_asset_id,
            name=f"Output: {target_asset_id}",
            node_type="output",
            timestamp=datetime.now(),
        )

        lineage.add_node(source_node)
        lineage.add_node(operation_node)
        lineage.add_node(target_node)

        # Add edges
        lineage.add_edge(source_asset_id, operation_id)
        lineage.add_edge(operation_id, target_asset_id)

        logger.info(
            f"Tracked transformation: {source_asset_id} -> {operation_id} -> {target_asset_id}"
        )

    def create_operation_lineage(self, asset_id: str) -> DataLineage:
        """Create lineage for an operation.

        Args:
            asset_id: Asset ID

        Returns:
            DataLineage
        """
        lineage = DataLineage()
        self.operation_lineages[asset_id] = lineage
        return lineage

    def get_impact_analysis(self, asset_id: str) -> Dict[str, Set[str]]:
        """Get impact analysis for an asset.

        Args:
            asset_id: Asset ID

        Returns:
            Dictionary with upstream and downstream impacts
        """
        lineage = self.operation_lineages.get(asset_id)
        if not lineage:
            return {"upstream": set(), "downstream": set()}

        return {
            "upstream": lineage.get_upstream(asset_id),
            "downstream": lineage.get_downstream(asset_id),
        }
