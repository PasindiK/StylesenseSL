"""Phase 4 Relationship Discovery Engine facade.

Core responsibilities:
- Iterate dataset pairs and column pairs
- Build feature vectors
- Score with RelationshipScoringEngine
- Detect cardinality
- Apply decision thresholds via scoring engine
- Return structured inferred relationships
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .relationship_engines import (
    BehavioralFeatureExtractor,
    FeatureVectorBuilder,
    RelationshipDiscoveryEngine as CoreRelationshipDiscoveryEngine,
    RelationshipScoringEngine,
    StatisticalFeatureExtractor,
    StructuralFeatureExtractor,
)


@dataclass
class InferredRelationship:
    """Structured relationship output for Phase 4 module."""

    source_dataset: str
    target_dataset: str
    source_column: str
    target_column: str
    confidence: float
    decision: str
    cardinality: str
    feature_vector: Dict[str, Any]
    model_version: str
    feature_vector_version: str


class RelationshipDiscoveryEngine:
    """Facade wrapper that exposes Phase 4 contract output."""

    def __init__(
        self,
        scoring_engine: RelationshipScoringEngine,
        structural_extractor: Optional[StructuralFeatureExtractor] = None,
        statistical_extractor: Optional[StatisticalFeatureExtractor] = None,
        behavioral_extractor: Optional[BehavioralFeatureExtractor] = None,
        feature_vector_builder: Optional[FeatureVectorBuilder] = None,
    ):
        self.scoring_engine = scoring_engine
        self.behavioral_extractor = behavioral_extractor or BehavioralFeatureExtractor(sample_size=10000)
        self.structural_extractor = structural_extractor or StructuralFeatureExtractor(self.behavioral_extractor)
        self.statistical_extractor = statistical_extractor or StatisticalFeatureExtractor(sample_size=10000)
        self.feature_vector_builder = feature_vector_builder or FeatureVectorBuilder(
            structural_extractor=self.structural_extractor,
            statistical_extractor=self.statistical_extractor,
            behavioral_extractor=self.behavioral_extractor,
        )
        self.core_engine = CoreRelationshipDiscoveryEngine(
            structural_extractor=self.structural_extractor,
            statistical_extractor=self.statistical_extractor,
            behavioral_extractor=self.behavioral_extractor,
            feature_vector_builder=self.feature_vector_builder,
            scoring_engine=self.scoring_engine,
        )

    def discover(
        self,
        datasets: Dict[str, pd.DataFrame],
        threshold_high: Optional[float] = None,
        threshold_mid: Optional[float] = None,
    ) -> List[InferredRelationship]:
        """Run discovery and return structured Phase 4 relationships."""
        if threshold_high is not None:
            self.scoring_engine.strong_threshold = float(threshold_high)
        if threshold_mid is not None:
            self.scoring_engine.probable_threshold = float(threshold_mid)

        results: List[Any] = self.core_engine.discover(datasets=datasets, relationship_factory=lambda **kwargs: kwargs)

        structured: List[InferredRelationship] = []
        for row in results:
            structured.append(
                InferredRelationship(
                    source_dataset=str(row["left_dataset"]),
                    target_dataset=str(row["right_dataset"]),
                    source_column=str(row["left_column"]),
                    target_column=str(row["right_column"]),
                    confidence=float(row["confidence"]),
                    decision=str(row["decision"]),
                    cardinality=str(row["cardinality"]),
                    feature_vector=dict(row["feature_vector"]),
                    model_version=str(row.get("model_version", self.scoring_engine.model_version)),
                    feature_vector_version=str(row.get("feature_vector_version", row["feature_vector"].get("feature_vector_version", "unknown"))),
                )
            )
        return structured
