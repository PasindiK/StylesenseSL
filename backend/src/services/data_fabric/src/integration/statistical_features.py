"""Statistical feature extraction for relationship candidates.

This module focuses on value-level behavior with sampling for performance:
- overlap_ratio
- containment_left_in_right
- containment_right_in_left
- numeric_range_similarity
- duplication_ratio_left
- duplication_ratio_right
"""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


class StatisticalFeatureExtractor:
    """Extract statistical/value-distribution features for candidate joins."""

    def __init__(self, sample_size: int = 10000):
        self.sample_size = sample_size

    def sample_series(self, series: pd.Series) -> pd.Series:
        """Sample a series for performance when row count exceeds sample size."""
        cleaned = series.dropna()
        if len(cleaned) > self.sample_size:
            return cleaned.sample(self.sample_size, random_state=42)
        return cleaned

    def sample_unique_values(self, series: pd.Series) -> set:
        """Return sampled unique values as normalized strings."""
        sampled = self.sample_series(series)
        if sampled.empty:
            return set()
        return set(sampled.astype(str).unique().tolist())

    def overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        """Compute |intersection| / min(|unique_left|, |unique_right|)."""
        left_values = self.sample_unique_values(left)
        right_values = self.sample_unique_values(right)
        if not left_values or not right_values:
            return 0.0

        intersection = len(left_values.intersection(right_values))
        denominator = min(len(left_values), len(right_values))
        if denominator == 0:
            return 0.0
        return float(intersection / denominator)

    def containment_left_in_right(self, left: pd.Series, right: pd.Series) -> float:
        """Compute |intersection| / |unique_left|."""
        left_values = self.sample_unique_values(left)
        right_values = self.sample_unique_values(right)
        if not left_values:
            return 0.0
        intersection = len(left_values.intersection(right_values))
        return float(intersection / len(left_values))

    def containment_right_in_left(self, left: pd.Series, right: pd.Series) -> float:
        """Compute |intersection| / |unique_right|."""
        left_values = self.sample_unique_values(left)
        right_values = self.sample_unique_values(right)
        if not right_values:
            return 0.0
        intersection = len(left_values.intersection(right_values))
        return float(intersection / len(right_values))

    @staticmethod
    def uniqueness_ratio(series: pd.Series) -> float:
        total_rows = len(series)
        if total_rows == 0:
            return 0.0
        return float(series.nunique(dropna=True) / total_rows)

    def duplication_ratio(self, series: pd.Series) -> float:
        """Compute 1 - uniqueness_ratio for one side."""
        return float(1.0 - self.uniqueness_ratio(series))

    @staticmethod
    def numeric_range_similarity(left: pd.Series, right: pd.Series) -> float:
        """Compute overlap_of_ranges / union_of_ranges for numeric columns.

        Returns 0.0 when either side is non-numeric or empty after coercion.
        """
        left_num = pd.to_numeric(left, errors="coerce").dropna()
        right_num = pd.to_numeric(right, errors="coerce").dropna()

        if left_num.empty or right_num.empty:
            return 0.0

        left_min, left_max = float(left_num.min()), float(left_num.max())
        right_min, right_max = float(right_num.min()), float(right_num.max())

        overlap_start = max(left_min, right_min)
        overlap_end = min(left_max, right_max)
        overlap = max(0.0, overlap_end - overlap_start)

        union_start = min(left_min, right_min)
        union_end = max(left_max, right_max)
        union_range = union_end - union_start
        if union_range == 0.0:
            return 1.0 if overlap == 0.0 else 0.0

        return float(overlap / union_range)

    def extract(self, left: pd.Series, right: pd.Series) -> Dict[str, float]:
        """Extract full statistical feature set for a candidate pair."""
        return {
            "overlap_ratio": round(self.overlap_ratio(left, right), 6),
            "containment_left_in_right": round(self.containment_left_in_right(left, right), 6),
            "containment_right_in_left": round(self.containment_right_in_left(left, right), 6),
            "numeric_range_similarity": round(self.numeric_range_similarity(left, right), 6),
            "duplication_ratio_left": round(self.duplication_ratio(left), 6),
            "duplication_ratio_right": round(self.duplication_ratio(right), 6),
        }

    # Backward-compatible alias used by existing discovery flow.
    def value_overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        return self.overlap_ratio(left, right)

    def bidirectional_containment(self, left: pd.Series, right: pd.Series) -> Tuple[float, float]:
        return self.containment_left_in_right(left, right), self.containment_right_in_left(left, right)
