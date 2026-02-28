"""Test fixtures and sample data."""

import pandas as pd
import numpy as np


def get_sample_csv_data() -> pd.DataFrame:
    """Get sample CSV data for testing.

    Returns:
        Sample DataFrame
    """
    np.random.seed(42)
    return pd.DataFrame(
        {
            "id": range(1, 101),
            "name": [f"user_{i}" for i in range(1, 101)],
            "age": np.random.randint(18, 80, 100),
            "salary": np.random.randint(30000, 150000, 100),
            "department": np.random.choice(["Sales", "Engineering", "HR", "Finance"], 100),
        }
    )


def get_sample_numeric_data() -> pd.DataFrame:
    """Get sample numeric data for ML testing.

    Returns:
        Sample DataFrame with numeric features
    """
    np.random.seed(42)
    n_samples = 100
    return pd.DataFrame(
        {
            "feature_1": np.random.randn(n_samples),
            "feature_2": np.random.randn(n_samples),
            "feature_3": np.random.randn(n_samples),
            "feature_4": np.random.randn(n_samples),
            "target": np.random.choice([0, 1], n_samples),
        }
    )


def get_sample_with_missing_values() -> pd.DataFrame:
    """Get sample data with missing values.

    Returns:
        Sample DataFrame with NaN values
    """
    df = get_sample_csv_data()
    # Add some missing values
    df.loc[10:15, "salary"] = np.nan
    df.loc[20:25, "department"] = np.nan
    return df


def get_sample_with_outliers() -> pd.DataFrame:
    """Get sample data with outliers.

    Returns:
        Sample DataFrame with outliers
    """
    df = get_sample_csv_data()
    # Add outliers
    df.loc[5, "salary"] = 500000  # Extreme outlier
    df.loc[8, "age"] = 150  # Impossible age
    return df


def get_validation_config() -> dict:
    """Get sample validation configuration.

    Returns:
        Validation config dictionary
    """
    return {
        "schema": {
            "id": "int",
            "name": "object",
            "age": "int",
            "salary": "int",
            "department": "object",
        },
        "ranges": {
            "age": (18, 100),
            "salary": (30000, 500000),
        },
        "required_columns": ["id", "name", "age"],
    }
