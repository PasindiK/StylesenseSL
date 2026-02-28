"""Unit tests for preprocessing layer."""

import pytest
import pandas as pd
import numpy as np
from src.preprocessing import (
    DataCleaner,
    MissingValueHandler,
    OutlierHandler,
    StandardScaler,
)
from tests.fixtures.sample_data import (
    get_sample_with_missing_values,
    get_sample_with_outliers,
)


class TestMissingValueHandler:
    """Tests for missing value handler."""

    def test_drop_missing_values(self):
        """Test dropping missing values."""
        df = get_sample_with_missing_values()
        initial_rows = len(df)

        handler = MissingValueHandler(strategy="drop")
        result = handler.clean(df)

        assert len(result) < initial_rows
        assert result.isnull().sum().sum() == 0

    def test_fill_missing_values(self):
        """Test filling missing values."""
        df = get_sample_with_missing_values()

        handler = MissingValueHandler(strategy="fill", fill_value=0)
        result = handler.clean(df)

        assert result.isnull().sum().sum() == 0


class TestOutlierHandler:
    """Tests for outlier handler."""

    def test_iqr_outlier_detection(self):
        """Test IQR-based outlier detection."""
        df = get_sample_with_outliers()
        initial_rows = len(df)

        handler = OutlierHandler(method="iqr")
        result = handler.clean(df)

        assert len(result) < initial_rows

    def test_zscore_outlier_detection(self):
        """Test Z-score based outlier detection."""
        df = get_sample_with_outliers()

        handler = OutlierHandler(method="zscore", threshold=3)
        result = handler.clean(df)

        assert len(result) <= len(df)


class TestStandardScaler:
    """Tests for standard scaler."""

    def test_fit_transform(self):
        """Test fitting and transforming."""
        df = pd.DataFrame(
            {
                "feature_1": [1, 2, 3, 4, 5],
                "feature_2": [10, 20, 30, 40, 50],
            }
        )

        scaler = StandardScaler()
        result = scaler.fit_transform(df)

        # Check that features are scaled
        assert result["feature_1"].mean() < 0.1  # Should be ~0
        assert result["feature_2"].mean() < 0.1  # Should be ~0

    def test_separate_fit_transform(self):
        """Test separate fit and transform."""
        df_train = pd.DataFrame({"feature": [1, 2, 3, 4, 5]})
        df_test = pd.DataFrame({"feature": [2, 3, 4]})

        scaler = StandardScaler()
        scaler.fit(df_train)
        result = scaler.transform(df_test)

        assert len(result) == len(df_test)
