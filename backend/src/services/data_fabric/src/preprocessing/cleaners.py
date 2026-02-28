"""Data cleaning utilities."""

from abc import ABC, abstractmethod
from typing import Optional, List
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataCleaner(ABC):
    """Abstract base class for data cleaners."""

    @abstractmethod
    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Clean data.

        Args:
            data: Input DataFrame

        Returns:
            Cleaned DataFrame
        """
        pass


class MissingValueHandler(DataCleaner):
    """Handle missing values in data."""

    def __init__(
        self,
        strategy: str = "drop",
        fill_value: Optional[any] = None,
        threshold: float = 0.5,
    ):
        """Initialize missing value handler.

        Args:
            strategy: 'drop', 'forward_fill', 'backward_fill', or 'fill'
            fill_value: Value to fill with (for 'fill' strategy)
            threshold: Drop columns with missing > threshold
        """
        self.strategy = strategy
        self.fill_value = fill_value
        self.threshold = threshold

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Handle missing values."""
        df = data.copy()

        # Drop columns with too many missing values
        missing_ratio = df.isnull().sum() / len(df)
        cols_to_drop = missing_ratio[missing_ratio > self.threshold].index
        df = df.drop(columns=cols_to_drop)

        if cols_to_drop.any():
            logger.info(f"Dropped {len(cols_to_drop)} columns with high missing values")

        # Handle remaining missing values
        if self.strategy == "drop":
            initial_rows = len(df)
            df = df.dropna()
            logger.info(f"Dropped {initial_rows - len(df)} rows with missing values")

        elif self.strategy == "forward_fill":
            df = df.fillna(method="ffill")
            logger.info("Applied forward fill for missing values")

        elif self.strategy == "backward_fill":
            df = df.fillna(method="bfill")
            logger.info("Applied backward fill for missing values")

        elif self.strategy == "fill":
            df = df.fillna(self.fill_value)
            logger.info(f"Filled missing values with {self.fill_value}")

        return df


class OutlierHandler(DataCleaner):
    """Handle outliers in data."""

    def __init__(self, method: str = "iqr", threshold: float = 1.5):
        """Initialize outlier handler.

        Args:
            method: 'iqr', 'zscore', or 'percentile'
            threshold: Threshold for outlier detection
        """
        self.method = method
        self.threshold = threshold

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Handle outliers."""
        df = data.copy()
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        outliers_removed = 0

        for col in numeric_cols:
            initial_size = len(df)

            if self.method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - self.threshold * IQR
                upper_bound = Q3 + self.threshold * IQR
                df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]

            elif self.method == "zscore":
                z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
                df = df[z_scores <= self.threshold]

            elif self.method == "percentile":
                lower = df[col].quantile(self.threshold / 100)
                upper = df[col].quantile(1 - self.threshold / 100)
                df = df[(df[col] >= lower) & (df[col] <= upper)]

            outliers_removed += initial_size - len(df)

        logger.info(f"Removed {outliers_removed} outlier records")
        return df


class DuplicateHandler(DataCleaner):
    """Handle duplicate records."""

    def __init__(self, subset: Optional[List[str]] = None, keep: str = "first"):
        """Initialize duplicate handler.

        Args:
            subset: Column names to consider for duplicates
            keep: 'first', 'last', or False to remove all duplicates
        """
        self.subset = subset
        self.keep = keep

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicates."""
        df = data.copy()
        initial_size = len(df)
        df = df.drop_duplicates(subset=self.subset, keep=self.keep)
        duplicates_removed = initial_size - len(df)

        logger.info(f"Removed {duplicates_removed} duplicate records")
        return df


class DataTypeValidator(DataCleaner):
    """Validate and correct data types."""

    def __init__(self, type_mapping: Optional[dict[str, str]] = None):
        """Initialize type validator.

        Args:
            type_mapping: Expected column types
        """
        self.type_mapping = type_mapping or {}

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Validate and correct types."""
        df = data.copy()

        for col, dtype in self.type_mapping.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                    logger.info(f"Corrected type for {col} to {dtype}")
                except Exception as e:
                    logger.warning(f"Could not convert {col} to {dtype}: {e}")

        return df


class WhitespaceStripper(DataCleaner):
    """Remove leading/trailing whitespace from strings."""

    def clean(self, data: pd.DataFrame) -> pd.DataFrame:
        """Strip whitespace from string columns."""
        df = data.copy()
        string_cols = df.select_dtypes(include=["object"]).columns

        for col in string_cols:
            df[col] = df[col].str.strip()

        logger.info(f"Stripped whitespace from {len(string_cols)} string columns")
        return df
