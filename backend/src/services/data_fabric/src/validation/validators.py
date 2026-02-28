"""Data validators."""

from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of a validation check."""

    def __init__(self, is_valid: bool, message: str, details: Optional[Dict] = None):
        """Initialize validation result.

        Args:
            is_valid: Whether validation passed
            message: Result message
            details: Additional details
        """
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        """String representation."""
        return f"ValidationResult(valid={self.is_valid}, message='{self.message}')"


class DataValidator(ABC):
    """Abstract base class for data validators."""

    @abstractmethod
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate data.

        Args:
            data: DataFrame to validate

        Returns:
            ValidationResult
        """
        pass


class SchemaValidator(DataValidator):
    """Validate DataFrame schema."""

    def __init__(self, expected_columns: Dict[str, str]):
        """Initialize schema validator.

        Args:
            expected_columns: Dictionary mapping column names to expected types
        """
        self.expected_columns = expected_columns

    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate schema."""
        # Check for required columns
        missing_cols = set(self.expected_columns.keys()) - set(data.columns)
        if missing_cols:
            return ValidationResult(
                is_valid=False,
                message=f"Missing columns: {missing_cols}",
                details={"missing_columns": list(missing_cols)},
            )

        # Check column types
        type_mismatches = {}
        for col, expected_type in self.expected_columns.items():
            actual_type = str(data[col].dtype)
            if expected_type not in actual_type:
                type_mismatches[col] = {"expected": expected_type, "actual": actual_type}

        if type_mismatches:
            return ValidationResult(
                is_valid=False,
                message=f"Type mismatches: {len(type_mismatches)} columns",
                details={"type_mismatches": type_mismatches},
            )

        logger.info(f"Schema validation passed for {len(data.columns)} columns")
        return ValidationResult(is_valid=True, message="Schema validation passed")


class RangeValidator(DataValidator):
    """Validate numeric values are within acceptable ranges."""

    def __init__(self, ranges: Dict[str, tuple]):
        """Initialize range validator.

        Args:
            ranges: Dictionary mapping column names to (min, max) tuples
        """
        self.ranges = ranges

    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate value ranges."""
        out_of_range = {}

        for col, (min_val, max_val) in self.ranges.items():
            if col not in data.columns:
                continue

            violations = data[(data[col] < min_val) | (data[col] > max_val)]
            if len(violations) > 0:
                out_of_range[col] = len(violations)

        if out_of_range:
            return ValidationResult(
                is_valid=False,
                message=f"Out of range values in {len(out_of_range)} columns",
                details={"out_of_range": out_of_range},
            )

        logger.info("Range validation passed")
        return ValidationResult(is_valid=True, message="Range validation passed")


class PatternValidator(DataValidator):
    """Validate data matches patterns."""

    def __init__(self, patterns: Dict[str, str]):
        """Initialize pattern validator.

        Args:
            patterns: Dictionary mapping column names to regex patterns
        """
        self.patterns = patterns

    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate patterns."""
        import re

        pattern_violations = {}

        for col, pattern in self.patterns.items():
            if col not in data.columns:
                continue

            regex = re.compile(pattern)
            violations = ~data[col].astype(str).str.match(regex)
            num_violations = violations.sum()

            if num_violations > 0:
                pattern_violations[col] = num_violations

        if pattern_violations:
            return ValidationResult(
                is_valid=False,
                message=f"Pattern violations in {len(pattern_violations)} columns",
                details={"violations": pattern_violations},
            )

        logger.info("Pattern validation passed")
        return ValidationResult(is_valid=True, message="Pattern validation passed")


class CardinalityValidator(DataValidator):
    """Validate cardinality constraints."""

    def __init__(self, cardinality_limits: Dict[str, int]):
        """Initialize cardinality validator.

        Args:
            cardinality_limits: Dictionary mapping column names to max unique values
        """
        self.cardinality_limits = cardinality_limits

    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate cardinality."""
        cardinality_violations = {}

        for col, max_cardinality in self.cardinality_limits.items():
            if col not in data.columns:
                continue

            unique_count = data[col].nunique()
            if unique_count > max_cardinality:
                cardinality_violations[col] = {
                    "max_allowed": max_cardinality,
                    "actual": unique_count,
                }

        if cardinality_violations:
            return ValidationResult(
                is_valid=False,
                message=f"Cardinality violations in {len(cardinality_violations)} columns",
                details={"violations": cardinality_violations},
            )

        logger.info("Cardinality validation passed")
        return ValidationResult(is_valid=True, message="Cardinality validation passed")
