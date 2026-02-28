"""Quality checking utilities."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class QualityMetric:
    """Quality metric result."""

    def __init__(self, name: str, value: float, threshold: Optional[float] = None):
        """Initialize quality metric.

        Args:
            name: Metric name
            value: Metric value
            threshold: Acceptable threshold
        """
        self.name = name
        self.value = value
        self.threshold = threshold
        self.passed = value >= threshold if threshold else True

    def __repr__(self) -> str:
        """String representation."""
        return f"QualityMetric({self.name}={self.value:.2%}, passed={self.passed})"


class QualityChecker(ABC):
    """Abstract base class for quality checks."""

    @abstractmethod
    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check data quality.

        Args:
            data: DataFrame to check

        Returns:
            QualityMetric
        """
        pass


class CompletenessCheck(QualityChecker):
    """Check data completeness (non-null values)."""

    def __init__(self, threshold: float = 0.95):
        """Initialize completeness check.

        Args:
            threshold: Minimum acceptable completeness (0-1)
        """
        self.threshold = threshold

    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check completeness."""
        total_values = data.shape[0] * data.shape[1]
        non_null_values = data.count().sum()
        completeness = non_null_values / total_values

        logger.info(f"Completeness check: {completeness:.2%}")
        return QualityMetric("completeness", completeness, self.threshold)


class UniqueConstraintCheck(QualityChecker):
    """Check unique constraint violations."""

    def __init__(self, columns: list[str], threshold: float = 0.99):
        """Initialize uniqueness check.

        Args:
            columns: Columns to check for uniqueness
            threshold: Minimum acceptable uniqueness ratio
        """
        self.columns = columns
        self.threshold = threshold

    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check uniqueness constraints."""
        violations = 0
        for col in self.columns:
            if col in data.columns:
                duplicates = len(data) - data[col].nunique()
                violations += duplicates

        uniqueness = 1 - (violations / len(data)) if len(data) > 0 else 1.0

        logger.info(f"Uniqueness check: {uniqueness:.2%} ({violations} violations)")
        return QualityMetric("uniqueness", uniqueness, self.threshold)


class DataTypeConsistencyCheck(QualityChecker):
    """Check data type consistency."""

    def __init__(self, type_mapping: Dict[str, str], threshold: float = 0.99):
        """Initialize type consistency check.

        Args:
            type_mapping: Expected column types
            threshold: Minimum acceptable success rate
        """
        self.type_mapping = type_mapping
        self.threshold = threshold

    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check type consistency."""
        successes = 0
        total = len(self.type_mapping)

        for col, expected_type in self.type_mapping.items():
            if col not in data.columns:
                continue

            actual_type = str(data[col].dtype)
            if expected_type in actual_type:
                successes += 1

        consistency = successes / total if total > 0 else 1.0

        logger.info(f"Type consistency check: {consistency:.2%}")
        return QualityMetric("type_consistency", consistency, self.threshold)


class DistributionCheck(QualityChecker):
    """Check data distribution for anomalies."""

    def __init__(self, threshold: float = 0.9):
        """Initialize distribution check.

        Args:
            threshold: Minimum acceptable score
        """
        self.threshold = threshold

    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check distribution."""
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        # Check for extreme outliers (beyond 3 standard deviations)
        anomalies = 0
        total_values = 0

        for col in numeric_cols:
            z_scores = np.abs((data[col] - data[col].mean()) / data[col].std())
            anomalies += (z_scores > 3).sum()
            total_values += len(data)

        anomaly_ratio = anomalies / total_values if total_values > 0 else 0
        score = 1 - min(anomaly_ratio, 1.0)

        logger.info(f"Distribution check: {score:.2%} (anomalies: {anomalies})")
        return QualityMetric("distribution", score, self.threshold)


class DuplicateRecordsCheck(QualityChecker):
    """Check for duplicate records."""

    def __init__(self, threshold: float = 0.985):
        """Initialize duplicate records check.

        Args:
            threshold: Maximum acceptable duplicate ratio
        """
        self.threshold = threshold

    def check(self, data: pd.DataFrame) -> QualityMetric:
        """Check for duplicates."""
        duplicate_rows = data.duplicated().sum()
        unique_ratio = 1 - (duplicate_rows / len(data)) if len(data) > 0 else 1.0

        logger.info(f"Duplicate records check: {unique_ratio:.2%} unique")
        return QualityMetric("duplicate_records", unique_ratio, self.threshold)
