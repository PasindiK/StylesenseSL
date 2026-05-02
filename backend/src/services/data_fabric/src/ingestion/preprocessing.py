"""Dynamic data preprocessing for ingestion layer.

This module provides in-memory transformations:
- Column name normalization (snake_case)
- Date column normalization (ISO format)
- Numeric type conversion
"""

import re
import logging
import pandas as pd
from typing import Any, Dict, Optional
from datetime import datetime
import warnings

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """Dynamic data preprocessing with automatic transformations."""

    # Date-like tokens matched as whole words or underscore-separated terms.
    DATE_COLUMN_PATTERNS = [
        r"(^|_)(date|time|timestamp)($|_)",
        r"(^|_)(created|updated|modified)($|_)",
        r"(^|_)(birth|expiry|expired|valid|start|end)($|_)",
        r"(^|_)(year|month|day)($|_)",
    ]

    IDENTIFIER_COLUMN_PATTERNS = [
        r"_id$",
        r"^id$",
        r"^id_",
    ]

    # Common numeric column patterns
    NUMERIC_COLUMN_PATTERNS = [
        r"price",
        r"cost",
        r"amount",
        r"quantity",
        r"count",
        r"total",
        r"_id$",  # Matches columns ending with _id
        r"^id$",  # Matches exactly "id"
        r"^id_",  # Matches columns starting with id_
        r"number",
        r"score",
        r"rating",
        r"value",
        r"age",
        r"revenue",
        r"salary",
        r"sales",
    ]

    @staticmethod
    def to_snake_case(name: str) -> str:
        """Convert string to snake_case.

        Handles:
        - CamelCase -> camel_case
        - PascalCase -> pascal_case
        - kebab-case -> kebab_case
        - Space Case -> space_case
        - Consecutive capitals (ID, URL, API) -> id, url, api

        Args:
            name: Original column name

        Returns:
            snake_case version of name
        """
        # Replace spaces and hyphens with underscores
        name = re.sub(r"[\s\-]+", "_", name)

        # Insert underscore between lowercase and uppercase (camelCase)
        name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)

        # Insert underscore between consecutive capitals and lowercase (e.g., "HTMLParser" -> "HTML_Parser")
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)

        # Convert to lowercase
        name = name.lower()

        # Remove duplicate underscores
        name = re.sub(r"_+", "_", name)

        # Remove leading/trailing underscores
        name = name.strip("_")

        return name

    @staticmethod
    def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """Convert all column names to snake_case.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with normalized column names
        """
        original_columns = df.columns.tolist()
        normalized_columns = [DataPreprocessor.to_snake_case(col) for col in original_columns]

        # Check for duplicates after normalization
        if len(normalized_columns) != len(set(normalized_columns)):
            logger.warning(
                f"Column name normalization created duplicates. "
                f"Original: {original_columns}"
            )
            # Add numeric suffixes to duplicates
            seen = {}
            final_columns = []
            for col in normalized_columns:
                if col in seen:
                    seen[col] += 1
                    final_columns.append(f"{col}_{seen[col]}")
                else:
                    seen[col] = 0
                    final_columns.append(col)
            normalized_columns = final_columns

        df.columns = normalized_columns

        if original_columns != normalized_columns:
            logger.info(
                f"Normalized {len(original_columns)} column names to snake_case"
            )
            # Log sample changes
            changes = [
                (orig, norm)
                for orig, norm in zip(original_columns, normalized_columns)
                if orig != norm
            ]
            if changes:
                sample = changes[:3]
                logger.debug(f"Sample changes: {sample}")

        return df

    @staticmethod
    def is_date_column(column_name: str) -> bool:
        """Check if column name suggests it contains dates.

        Args:
            column_name: Column name to check

        Returns:
            True if column likely contains dates
        """
        column_lower = column_name.lower()
        if DataPreprocessor.is_identifier_column(column_lower):
            return False
        return any(
            re.search(pattern, column_lower)
            for pattern in DataPreprocessor.DATE_COLUMN_PATTERNS
        )

    @staticmethod
    def is_identifier_column(column_name: str) -> bool:
        """Check if column name represents an identifier key."""
        column_lower = column_name.lower()
        return any(
            re.search(pattern, column_lower)
            for pattern in DataPreprocessor.IDENTIFIER_COLUMN_PATTERNS
        )

    @staticmethod
    def is_numeric_column(column_name: str) -> bool:
        """Check if column name suggests it should be numeric.

        Args:
            column_name: Column name to check

        Returns:
            True if column should likely be numeric
        """
        column_lower = column_name.lower()
        return any(
            re.search(pattern, column_lower)
            for pattern in DataPreprocessor.NUMERIC_COLUMN_PATTERNS
        )

    @staticmethod
    def normalize_date_column(series: pd.Series) -> pd.Series:
        """Normalize date column to ISO format (YYYY-MM-DD).

        Handles various date formats automatically using pandas.to_datetime.

        Args:
            series: Date column as Series

        Returns:
            Normalized date Series in ISO format
        """
        try:
            # Parse mixed date formats explicitly; fallback keeps compatibility
            # with older pandas versions that may not support format="mixed".
            try:
                parsed = pd.to_datetime(series, errors="coerce", format="mixed")
            except (TypeError, ValueError):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=UserWarning)
                    parsed = pd.to_datetime(series, errors="coerce")
            
            # Convert to ISO format string (YYYY-MM-DD)
            # If datetime has time component, use ISO 8601 with time
            if parsed.dt.hour.sum() > 0 or parsed.dt.minute.sum() > 0:
                # Has time component - use full ISO 8601
                normalized = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Date only - use YYYY-MM-DD
                normalized = parsed.dt.strftime("%Y-%m-%d")
            
            # Count successful conversions
            null_count_before = series.isnull().sum()
            null_count_after = normalized.isnull().sum()
            success_rate = (len(series) - null_count_after) / len(series)

            if success_rate < 0.5:
                # Less than 50% success - probably not a date column
                logger.debug(
                    f"Low date parsing success rate ({success_rate:.1%}), "
                    f"keeping original values"
                )
                return series

            if null_count_after > null_count_before:
                logger.debug(
                    f"Date parsing created {null_count_after - null_count_before} "
                    f"null values"
                )

            return normalized

        except Exception as e:
            logger.debug(f"Failed to normalize date column: {e}")
            return series

    @staticmethod
    def normalize_numeric_column(series: pd.Series) -> pd.Series:
        """Convert column to numeric type (int or float).

        Args:
            series: Column to convert

        Returns:
            Numeric Series (preserves NaN values)
        """
        try:
            # Try to convert to numeric
            numeric = pd.to_numeric(series, errors="coerce")

            # Count successful conversions (excluding original nulls)
            original_nulls = series.isnull().sum()
            new_nulls = numeric.isnull().sum()
            valid_count = len(series) - original_nulls
            success_count = len(series) - new_nulls

            if valid_count == 0:
                # All nulls, return as is
                return series

            success_rate = success_count / len(series)

            if success_rate < 0.8:
                # Less than 80% success - probably not a numeric column
                logger.debug(
                    f"Low numeric conversion success rate ({success_rate:.1%}), "
                    f"keeping original values"
                )
                return series

            # Convert to int if all values are whole numbers
            if numeric.notna().any():
                if (numeric.dropna() % 1 == 0).all():
                    # All non-null values are integers
                    numeric = numeric.astype("Int64")  # Nullable integer type

            return numeric

        except Exception as e:
            logger.debug(f"Failed to normalize numeric column: {e}")
            return series

    @staticmethod
    def preprocess(
        df: pd.DataFrame,
        normalize_columns: bool = True,
        normalize_dates: bool = True,
        normalize_numeric: bool = True,
        dataset_name: Optional[str] = None,
        metadata_catalog: Optional[Any] = None,
        metadata_registry: Optional[Any] = None,
        producer_pipeline: str = "ingestion.preprocessing",
    ) -> pd.DataFrame:
        """Apply all preprocessing transformations in memory.

        Args:
            df: Input DataFrame
            normalize_columns: Convert column names to snake_case
            normalize_dates: Convert date columns to ISO format
            normalize_numeric: Convert numeric columns to proper types
            dataset_name: Optional dataset name for metadata updates
            metadata_catalog: Optional MetadataCatalog instance to notify
            metadata_registry: Optional MetadataRegistry instance for versioning
            producer_pipeline: Pipeline identifier for metadata events

        Returns:
            Preprocessed DataFrame (in-memory, no file writes)
        """
        # Create a copy to avoid modifying original
        df = df.copy()
        schema_before = {col: str(dtype) for col, dtype in df.dtypes.items()}

        logger.info(f"Starting preprocessing: {len(df)} rows, {len(df.columns)} columns")

        # Step 1: Normalize column names
        if normalize_columns:
            df = DataPreprocessor.normalize_column_names(df)

        # Step 2: Normalize date columns
        if normalize_dates:
            date_columns = [
                col for col in df.columns if DataPreprocessor.is_date_column(col)
            ]
            if date_columns:
                logger.info(f"Normalizing {len(date_columns)} date columns to ISO format")
                for col in date_columns:
                    df[col] = DataPreprocessor.normalize_date_column(df[col])

        # Step 3: Normalize numeric columns
        if normalize_numeric:
            numeric_columns = [
                col
                for col in df.columns
                if DataPreprocessor.is_numeric_column(col)
                and df[col].dtype == "object"  # Only convert string columns
            ]
            if numeric_columns:
                logger.info(
                    f"Converting {len(numeric_columns)} columns to numeric types"
                )
                for col in numeric_columns:
                    df[col] = DataPreprocessor.normalize_numeric_column(df[col])

        schema_after = {col: str(dtype) for col, dtype in df.dtypes.items()}
        schema_changed = schema_before != schema_after

        DataPreprocessor._sync_metadata_after_preprocessing(
            dataset_name=dataset_name,
            metadata_catalog=metadata_catalog,
            metadata_registry=metadata_registry,
            schema_before=schema_before,
            schema_after=schema_after,
            row_count=len(df),
            column_count=len(df.columns),
            schema_changed=schema_changed,
            producer_pipeline=producer_pipeline,
        )

        logger.info("Preprocessing complete")
        return df

    @staticmethod
    def _sync_metadata_after_preprocessing(
        dataset_name: Optional[str],
        metadata_catalog: Optional[Any],
        metadata_registry: Optional[Any],
        schema_before: Dict[str, str],
        schema_after: Dict[str, str],
        row_count: int,
        column_count: int,
        schema_changed: bool,
        producer_pipeline: str,
    ) -> None:
        """Notify metadata systems after preprocessing."""
        if not dataset_name:
            return

        now = datetime.now()

        if metadata_catalog is not None:
            asset = metadata_catalog.get_asset(dataset_name)
            if asset is not None:
                updated_metadata = asset.metadata
                updated_metadata.updated_at = now
                updated_metadata.row_count = row_count
                updated_metadata.column_count = column_count

                if schema_changed:
                    updated_metadata.schema = schema_after
                    logger.info(
                        "event=metadata_catalog.schema_changed "
                        f"dataset_name={dataset_name} producer_pipeline={producer_pipeline}"
                    )

                updated_metadata.properties = {
                    **updated_metadata.properties,
                    "last_updated": now.isoformat(),
                    "producer_pipeline": producer_pipeline,
                    "schema_changed": schema_changed,
                }

                metadata_catalog.update_asset_metadata(dataset_name, updated_metadata)
                logger.info(
                    "event=metadata_catalog.preprocess_updated "
                    f"dataset_name={dataset_name} schema_changed={schema_changed} "
                    f"last_updated={now.isoformat()}"
                )

        if metadata_registry is not None:
            metadata_registry.register_metadata(
                entity_id=dataset_name,
                metadata={
                    "event": "preprocess",
                    "dataset_name": dataset_name,
                    "producer_pipeline": producer_pipeline,
                    "schema_before": schema_before,
                    "schema_after": schema_after,
                    "schema_changed": schema_changed,
                    "row_count": row_count,
                    "column_count": column_count,
                    "last_updated": now.isoformat(),
                },
                created_by=producer_pipeline,
            )
            logger.info(
                "event=metadata_registry.version_created "
                f"dataset_name={dataset_name} schema_changed={schema_changed}"
            )

    @staticmethod
    def get_preprocessing_summary(df_before: pd.DataFrame, df_after: pd.DataFrame) -> dict:
        """Generate summary of preprocessing changes.

        Args:
            df_before: DataFrame before preprocessing
            df_after: DataFrame after preprocessing

        Returns:
            Dictionary with preprocessing statistics
        """
        column_changes = [
            (before, after)
            for before, after in zip(df_before.columns, df_after.columns)
            if before != after
        ]

        type_changes = []
        for col_before, col_after in zip(df_before.columns, df_after.columns):
            if col_before in df_before.columns and col_after in df_after.columns:
                type_before = str(df_before[col_before].dtype)
                type_after = str(df_after[col_after].dtype)
                if type_before != type_after:
                    type_changes.append((col_after, type_before, type_after))

        return {
            "total_columns": len(df_after.columns),
            "total_rows": len(df_after),
            "columns_renamed": len(column_changes),
            "column_renames": column_changes[:10],  # Sample first 10
            "types_changed": len(type_changes),
            "type_changes": type_changes[:10],  # Sample first 10
        }
