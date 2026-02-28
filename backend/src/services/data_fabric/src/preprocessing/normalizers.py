"""Data normalization utilities."""

from abc import ABC, abstractmethod
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataNormalizer(ABC):
    """Abstract base class for data normalizers."""

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> "DataNormalizer":
        """Fit normalizer to data."""
        pass

    @abstractmethod
    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Normalize data.

        Args:
            data: Input DataFrame

        Returns:
            Normalized DataFrame
        """
        pass

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Fit and normalize data."""
        return self.fit(data).transform(data)


class StandardScaler(DataNormalizer):
    """Standardize features by removing mean and scaling to unit variance."""

    def __init__(self):
        """Initialize standard scaler."""
        self.mean = None
        self.std = None

    def fit(self, data: pd.DataFrame) -> "StandardScaler":
        """Fit scaler to data."""
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        self.mean = data[numeric_cols].mean()
        self.std = data[numeric_cols].std()
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data using fitted parameters."""
        if self.mean is None or self.std is None:
            raise ValueError("Scaler not fitted. Call fit() first.")

        df = data.copy()
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            if col in self.mean.index:
                df[col] = (df[col] - self.mean[col]) / self.std[col]

        logger.info(f"Applied standard scaling to {len(numeric_cols)} columns")
        return df


class MinMaxScaler(DataNormalizer):
    """Scale features to a fixed range (0, 1)."""

    def __init__(self, feature_range: tuple = (0, 1)):
        """Initialize MinMax scaler.

        Args:
            feature_range: Desired range (min, max)
        """
        self.feature_range = feature_range
        self.data_min = None
        self.data_max = None

    def fit(self, data: pd.DataFrame) -> "MinMaxScaler":
        """Fit scaler to data."""
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        self.data_min = data[numeric_cols].min()
        self.data_max = data[numeric_cols].max()
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data using fitted parameters."""
        if self.data_min is None or self.data_max is None:
            raise ValueError("Scaler not fitted. Call fit() first.")

        df = data.copy()
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        feature_min, feature_max = self.feature_range

        for col in numeric_cols:
            if col in self.data_min.index:
                df[col] = (
                    (df[col] - self.data_min[col])
                    / (self.data_max[col] - self.data_min[col])
                ) * (feature_max - feature_min) + feature_min

        logger.info(f"Applied MinMax scaling to {len(numeric_cols)} columns")
        return df


class RobustScaler(DataNormalizer):
    """Scale features using statistics robust to outliers."""

    def __init__(self):
        """Initialize robust scaler."""
        self.median = None
        self.q1 = None
        self.q3 = None

    def fit(self, data: pd.DataFrame) -> "RobustScaler":
        """Fit scaler to data."""
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        self.median = data[numeric_cols].median()
        self.q1 = data[numeric_cols].quantile(0.25)
        self.q3 = data[numeric_cols].quantile(0.75)
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data using fitted parameters."""
        if self.median is None or self.q1 is None or self.q3 is None:
            raise ValueError("Scaler not fitted. Call fit() first.")

        df = data.copy()
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            if col in self.median.index:
                iqr = self.q3[col] - self.q1[col]
                if iqr != 0:
                    df[col] = (df[col] - self.median[col]) / iqr

        logger.info(f"Applied robust scaling to {len(numeric_cols)} columns")
        return df


class LogNormalizer(DataNormalizer):
    """Apply log normalization to skewed data."""

    def __init__(self, columns: list[str]):
        """Initialize log normalizer.

        Args:
            columns: Columns to apply log transformation
        """
        self.columns = columns

    def fit(self, data: pd.DataFrame) -> "LogNormalizer":
        """Fit normalizer (no fitting needed for log transformation)."""
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply log transformation."""
        df = data.copy()

        for col in self.columns:
            if col in df.columns:
                # Add small value to avoid log(0)
                df[col] = np.log1p(df[col])

        logger.info(f"Applied log normalization to {len(self.columns)} columns")
        return df
