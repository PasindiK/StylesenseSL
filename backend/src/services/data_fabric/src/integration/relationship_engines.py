"""Relationship discovery engines for virtual integration.

Provides modular components for:
- Feature extraction (structural/statistical/behavioral)
- Feature vector construction
- Confidence scoring and decisioning
- Cross-dataset relationship discovery
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Callable, Dict, List, Optional
import warnings

import pandas as pd
from .behavioral_features import BehavioralFeatureExtractor as BaseBehavioralFeatureExtractor
from .feature_vector_builder import FeatureVectorBuilder as BaseFeatureVectorBuilder
from .scoring_engine import RelationshipScoringEngine as BaseRelationshipScoringEngine
from .structural_features import StructuralFeatureExtractor as BaseStructuralFeatureExtractor
from .statistical_features import StatisticalFeatureExtractor as BaseStatisticalFeatureExtractor


class BehavioralFeatureExtractor(BaseBehavioralFeatureExtractor):
    """Extract behavioral compatibility features between value distributions."""

    def __init__(self, sample_size: int = 10000, **kwargs):
        super().__init__(**kwargs)
        self.sample_size = sample_size

    def convertibility_score(self, left: pd.Series, right: pd.Series) -> float:
        """Estimate cross-series conversion compatibility.

        Uses best score from numeric/date convertibility in [0, 1].
        """
        left_non_null = left.dropna().astype(str)
        right_non_null = right.dropna().astype(str)
        if left_non_null.empty or right_non_null.empty:
            return 0.0

        left_sample = left_non_null.head(min(self.sample_size, len(left_non_null)))
        right_sample = right_non_null.head(min(self.sample_size, len(right_non_null)))

        left_to_numeric = pd.to_numeric(left_sample, errors="coerce").notna().mean()
        right_to_numeric = pd.to_numeric(right_sample, errors="coerce").notna().mean()
        numeric_score = min(left_to_numeric, right_to_numeric)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            left_to_date = pd.to_datetime(left_sample, errors="coerce").notna().mean()
            right_to_date = pd.to_datetime(right_sample, errors="coerce").notna().mean()
        datetime_score = min(left_to_date, right_to_date)

        return max(float(numeric_score), float(datetime_score))


class StructuralFeatureExtractor(BaseStructuralFeatureExtractor):
    """Extract structural compatibility features for candidate join columns."""

    def __init__(self, behavioral_extractor: BehavioralFeatureExtractor):
        self.behavioral_extractor = behavioral_extractor

    def type_compatibility_score(self, left: pd.Series, right: pd.Series) -> float:
        structural_score = self.type_score(left, right)
        if structural_score > 0:
            return structural_score

        if self.behavioral_extractor.convertibility_score(left, right) >= 0.8:
            return 0.7

        return 0.0

    @staticmethod
    def detect_cardinality(left: pd.Series, right: pd.Series) -> str:
        left_non_null = left.dropna()
        right_non_null = right.dropna()
        if left_non_null.empty or right_non_null.empty:
            return "unknown"

        left_unique_ratio = float(left_non_null.nunique() / len(left_non_null))
        right_unique_ratio = float(right_non_null.nunique() / len(right_non_null))

        left_unique = left_unique_ratio >= 0.95
        right_unique = right_unique_ratio >= 0.95

        if left_unique and right_unique:
            return "one_to_one"
        if left_unique and not right_unique:
            return "one_to_many"
        if not left_unique and right_unique:
            return "many_to_one"
        return "many_to_many"


class StatisticalFeatureExtractor(BaseStatisticalFeatureExtractor):
    """Extract statistical overlap and distribution-based features."""


class FeatureVectorBuilder(BaseFeatureVectorBuilder):
    """Build rich feature vectors for relationship candidates."""


class RelationshipScoringEngine(BaseRelationshipScoringEngine):
    """Compute confidence and decision from extracted features."""

    def confidence(self, name_similarity: float, type_score: float, overlap_ratio: float) -> float:
        feature_vector = {
            "name_similarity": float(name_similarity),
            "type_score": float(type_score),
            "overlap_ratio": float(overlap_ratio),
        }
        return self.score(feature_vector)


class RelationshipDiscoveryEngine:
    """Discover relationships by combining extractors and scoring engines."""

    def __init__(
        self,
        structural_extractor: StructuralFeatureExtractor,
        statistical_extractor: StatisticalFeatureExtractor,
        behavioral_extractor: BehavioralFeatureExtractor,
        feature_vector_builder: FeatureVectorBuilder,
        scoring_engine: RelationshipScoringEngine,
    ):
        self.structural_extractor = structural_extractor
        self.statistical_extractor = statistical_extractor
        self.behavioral_extractor = behavioral_extractor
        self.feature_vector_builder = feature_vector_builder
        self.scoring_engine = scoring_engine

    def discover(
        self,
        datasets: Dict[str, pd.DataFrame],
        relationship_factory: Callable[..., Any],
    ) -> List[Any]:
        inferences: List[Any] = []
        dataset_names = sorted(datasets.keys())

        for left_name, right_name in combinations(dataset_names, 2):
            left_df = datasets[left_name]
            right_df = datasets[right_name]

            for left_col in left_df.columns:
                for right_col in right_df.columns:
                    left_series = left_df[left_col]
                    right_series = right_df[right_col]

                    name_similarity = self.structural_extractor.name_similarity(left_col, right_col)
                    type_score = self.structural_extractor.type_compatibility_score(
                        left_series,
                        right_series,
                    )
                    if type_score == 0:
                        continue

                    overlap_ratio = self.statistical_extractor.value_overlap_ratio(left_series, right_series)
                    feature_vector = self.feature_vector_builder.build(
                        left_dataset=left_name,
                        right_dataset=right_name,
                        left_column=left_col,
                        right_column=right_col,
                        left_series=left_series,
                        right_series=right_series,
                    )
                    score_details = self.scoring_engine.score_with_details(feature_vector)
                    confidence = float(score_details["confidence"])
                    decision = str(score_details["decision"])
                    if decision == "weak":
                        continue

                    feature_vector = {
                        **feature_vector,
                        "models_used": score_details.get("models_used", {}),
                        "confidence_source": score_details.get("confidence_source", "static"),
                    }

                    cardinality = self.structural_extractor.detect_cardinality(left_series, right_series)
                    inferences.append(
                        relationship_factory(
                            left_dataset=left_name,
                            right_dataset=right_name,
                            left_column=left_col,
                            right_column=right_col,
                            name_similarity=name_similarity,
                            type_score=type_score,
                            overlap_ratio=overlap_ratio,
                            confidence=confidence,
                            cardinality=cardinality,
                            decision=decision,
                            feature_vector=feature_vector,
                            model_version=str(self.scoring_engine.model_version),
                            feature_vector_version=str(feature_vector.get("feature_vector_version", "unknown")),
                        )
                    )

        inferences.sort(key=lambda rel: rel.confidence, reverse=True)
        return inferences

    @staticmethod
    def get_best_relationship(
        left_dataset: str,
        right_dataset: str,
        relationships: List[Any],
    ) -> Optional[Any]:
        candidates = [
            rel
            for rel in relationships
            if {rel.left_dataset, rel.right_dataset} == {left_dataset, right_dataset}
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda rel: rel.confidence, reverse=True)
        return candidates[0]
