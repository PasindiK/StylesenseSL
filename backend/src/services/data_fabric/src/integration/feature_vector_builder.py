"""Feature vector builder for ML-ready relationship inference.

Collects structural, statistical, and behavioral features and returns a flat
numeric dictionary with schema versioning.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .behavioral_features import BehavioralFeatureExtractor
from .statistical_features import StatisticalFeatureExtractor
from .structural_features import StructuralFeatureExtractor


class FeatureVectorBuilder:
    """Build flat feature vectors from Modules 1-3."""

    def __init__(
        self,
        structural_extractor: StructuralFeatureExtractor,
        statistical_extractor: StatisticalFeatureExtractor,
        behavioral_extractor: BehavioralFeatureExtractor,
        version: str = "v1.0",
    ):
        self.structural_extractor = structural_extractor
        self.statistical_extractor = statistical_extractor
        self.behavioral_extractor = behavioral_extractor
        self.version = version

    def build(
        self,
        left_dataset: str,
        right_dataset: str,
        left_column: str,
        right_column: str,
        left_series: pd.Series,
        right_series: pd.Series,
    ) -> Dict[str, float]:
        structural = self.structural_extractor.extract(
            left_col=left_column,
            right_col=right_column,
            left_series=left_series,
            right_series=right_series,
        )
        statistical = self.statistical_extractor.extract(left_series, right_series)
        behavioral = self.behavioral_extractor.extract(
            left_column=left_column,
            right_column=right_column,
            left_dataset=left_dataset,
            right_dataset=right_dataset,
        )

        return {
            "name_similarity": float(structural["name_similarity"]),
            "type_score": float(structural["type_score"]),
            "uniqueness_ratio_left": float(structural["uniqueness_ratio_left"]),
            "uniqueness_ratio_right": float(structural["uniqueness_ratio_right"]),
            "null_percentage_left": float(structural["null_percentage_left"]),
            "null_percentage_right": float(structural["null_percentage_right"]),
            "overlap_ratio": float(statistical["overlap_ratio"]),
            "containment_left_in_right": float(statistical["containment_left_in_right"]),
            "containment_right_in_left": float(statistical["containment_right_in_left"]),
            "numeric_range_similarity": float(statistical["numeric_range_similarity"]),
            "duplication_ratio_left": float(statistical["duplication_ratio_left"]),
            "duplication_ratio_right": float(statistical["duplication_ratio_right"]),
            "join_frequency_score": float(behavioral["join_frequency_score"]),
            "co_query_frequency_score": float(behavioral["co_query_frequency_score"]),
            "lineage_proximity_score": float(behavioral["lineage_proximity_score"]),
            "stability_score": float(behavioral["stability_score"]),
            "feature_vector_version": self.version,
        }
