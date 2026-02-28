"""Data transformation utilities."""

from abc import ABC, abstractmethod
from typing import Any, Optional, List
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataTransformer(ABC):
    """Abstract base class for data transformers."""

    @abstractmethod
    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data.

        Args:
            data: Input DataFrame

        Returns:
            Transformed DataFrame
        """
        pass

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> "DataTransformer":
        """Fit transformer to data."""
        pass

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform data."""
        return self.fit(data).transform(data)


class ColumnTypeTransformer(DataTransformer):
    """Transform column data types."""

    def __init__(self, type_mapping: dict[str, str]):
        """Initialize with column type mapping.

        Args:
            type_mapping: Dictionary mapping column names to target types
        """
        self.type_mapping = type_mapping

    def fit(self, data: pd.DataFrame) -> "ColumnTypeTransformer":
        """Fit transformer."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform column types."""
        df = data.copy()
        for column, dtype in self.type_mapping.items():
            if column in df.columns:
                try:
                    df[column] = df[column].astype(dtype)
                    logger.info(f"Converted {column} to {dtype}")
                except Exception as e:
                    logger.error(f"Failed to convert {column}: {e}")
        return df


class DateTimeTransformer(DataTransformer):
    """Transform columns to datetime format."""

    def __init__(self, date_columns: List[str], format: Optional[str] = None):
        """Initialize with columns to transform.

        Args:
            date_columns: List of column names to convert
            format: Optional datetime format string
        """
        self.date_columns = date_columns
        self.format = format

    def fit(self, data: pd.DataFrame) -> "DateTimeTransformer":
        """Fit transformer."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform to datetime."""
        df = data.copy()
        for column in self.date_columns:
            if column in df.columns:
                try:
                    df[column] = pd.to_datetime(df[column], format=self.format)
                    logger.info(f"Converted {column} to datetime")
                except Exception as e:
                    logger.error(f"Failed to convert {column} to datetime: {e}")
        return df


class FeatureEngineering(DataTransformer):
    """Feature engineering transformer."""

    def __init__(self):
        """Initialize feature engineering."""
        self.custom_transformations = {}

    def fit(self, data: pd.DataFrame) -> "FeatureEngineering":
        """Fit transformer."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply feature engineering transformations."""
        df = data.copy()

        # Example: Create derived features
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            # Log transformation
            if (df[col] > 0).all():
                df[f"{col}_log"] = np.log(df[col])

            # Square transformation
            df[f"{col}_squared"] = df[col] ** 2

        logger.info(f"Created {len(df.columns) - len(data.columns)} new features")
        return df

    def add_custom_transformation(self, name: str, func: callable) -> None:
        """Add custom transformation function.

        Args:
            name: Name of the transformation
            func: Callable that takes DataFrame and returns DataFrame
        """
        self.custom_transformations[name] = func

    def apply_custom_transformations(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply all custom transformations."""
        df = data.copy()
        for name, func in self.custom_transformations.items():
            try:
                df = func(df)
                logger.info(f"Applied custom transformation: {name}")
            except Exception as e:
                logger.error(f"Failed to apply {name}: {e}")
        return df


class ColumnRenamer(DataTransformer):
    """Rename DataFrame columns."""

    def __init__(self, column_mapping: dict[str, str]):
        """Initialize with column mapping.

        Args:
            column_mapping: Dictionary mapping old names to new names
        """
        self.column_mapping = column_mapping

    def fit(self, data: pd.DataFrame) -> "ColumnRenamer":
        """Fit transformer."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Rename columns."""
        df = data.rename(columns=self.column_mapping)
        logger.info(f"Renamed {len(self.column_mapping)} columns")
        return df


class ColumnDropper(DataTransformer):
    """Drop columns from DataFrame."""

    def __init__(self, columns_to_drop: List[str]):
        """Initialize with columns to drop.

        Args:
            columns_to_drop: List of column names to remove
        """
        self.columns_to_drop = columns_to_drop

    def fit(self, data: pd.DataFrame) -> "ColumnDropper":
        """Fit transformer."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Drop columns."""
        cols_to_drop = [c for c in self.columns_to_drop if c in data.columns]
        df = data.drop(columns=cols_to_drop)
        logger.info(f"Dropped {len(cols_to_drop)} columns")
        return df
