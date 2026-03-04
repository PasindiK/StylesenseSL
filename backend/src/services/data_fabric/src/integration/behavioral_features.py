"""Behavioral feature extraction for relationship confidence.

These features are derived from historical system behavior. If logs are missing,
all scores default to 0.0.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, Optional, Set, Tuple, Union


PairKey = Tuple[str, str]


class BehavioralFeatureExtractor:
    """Extract behavior-based relationship features from usage history."""

    def __init__(
        self,
        join_history: Optional[Dict[PairKey, int]] = None,
        co_query_history: Optional[Dict[PairKey, int]] = None,
        total_queries: Optional[int] = None,
        lineage_graph: Optional[Dict[str, Iterable[str]]] = None,
        inference_history: Optional[Dict[PairKey, Union[Tuple[int, int], Dict[str, int]]]] = None,
    ):
        self.join_history = join_history or {}
        self.co_query_history = co_query_history or {}
        self.total_queries = total_queries
        self.lineage_graph = {
            node: set(neighbors)
            for node, neighbors in (lineage_graph or {}).items()
        }
        self.inference_history = inference_history or {}

    def join_frequency_score(self, left: str, right: str) -> float:
        """joins_between_columns / max_join_frequency_in_system."""
        if not self.join_history:
            return 0.0

        key = self._pair_key(left, right)
        joins_between = float(self.join_history.get(key, 0))
        max_frequency = float(max(self.join_history.values())) if self.join_history else 0.0
        if max_frequency <= 0.0:
            return 0.0
        return float(max(0.0, min(1.0, joins_between / max_frequency)))

    def co_query_frequency_score(self, left_dataset: str, right_dataset: str) -> float:
        """co_occurrence / total_queries."""
        if not self.co_query_history:
            return 0.0

        key = self._pair_key(left_dataset, right_dataset)
        co_occurrence = float(self.co_query_history.get(key, 0))

        if self.total_queries is not None and self.total_queries > 0:
            denominator = float(self.total_queries)
        else:
            denominator = float(sum(self.co_query_history.values()))

        if denominator <= 0.0:
            return 0.0
        return float(max(0.0, min(1.0, co_occurrence / denominator)))

    def lineage_proximity_score(self, left_dataset: str, right_dataset: str) -> float:
        """score = 1 / (1 + graph_distance), using lineage graph hops."""
        if not self.lineage_graph:
            return 0.0

        if left_dataset == right_dataset:
            return 1.0

        distance = self._shortest_hop_distance(left_dataset, right_dataset)
        if distance is None:
            return 0.0
        return float(1.0 / (1.0 + distance))

    def stability_score(self, left: str, right: str) -> float:
        """stable_runs / total_inference_runs."""
        if not self.inference_history:
            return 0.0

        key = self._pair_key(left, right)
        record = self.inference_history.get(key)
        if record is None:
            return 0.0

        if isinstance(record, dict):
            stable_runs = int(record.get("stable_runs", 0))
            total_runs = int(record.get("total_runs", 0))
        else:
            stable_runs = int(record[0])
            total_runs = int(record[1])

        if total_runs <= 0:
            return 0.0
        return float(max(0.0, min(1.0, stable_runs / total_runs)))

    def extract(
        self,
        left_column: str,
        right_column: str,
        left_dataset: str,
        right_dataset: str,
    ) -> Dict[str, float]:
        """Extract all behavioral features for a candidate relationship."""
        return {
            "join_frequency_score": round(self.join_frequency_score(left_column, right_column), 6),
            "co_query_frequency_score": round(
                self.co_query_frequency_score(left_dataset, right_dataset),
                6,
            ),
            "lineage_proximity_score": round(
                self.lineage_proximity_score(left_dataset, right_dataset),
                6,
            ),
            "stability_score": round(self.stability_score(left_column, right_column), 6),
        }

    @staticmethod
    def _pair_key(left: str, right: str) -> PairKey:
        return tuple(sorted((left, right)))

    def _shortest_hop_distance(self, source: str, target: str) -> Optional[int]:
        if source not in self.lineage_graph and target not in self.lineage_graph:
            return None

        queue = deque([(source, 0)])
        visited: Set[str] = {source}

        while queue:
            current, distance = queue.popleft()
            if current == target:
                return distance

            neighbors = set(self.lineage_graph.get(current, set()))
            # Treat lineage connections as undirected for proximity lookup.
            reverse_neighbors = {
                node
                for node, linked in self.lineage_graph.items()
                if current in linked
            }
            for neighbor in neighbors.union(reverse_neighbors):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, distance + 1))

        return None
