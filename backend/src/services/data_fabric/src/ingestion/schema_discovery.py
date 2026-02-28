"""
Dynamic schema discovery module.

Auto-detects column roles (PK, FK, temporal, numeric, text) based on
statistical properties and naming conventions. Works on any dataset.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import re
from enum import Enum


class ColumnRole(Enum):
    """Inferred role of a column in the dataset."""
    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    TEMPORAL = "temporal"
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    TEXT = "text"
    IDENTIFIER = "identifier"  # ID-like but not necessarily PK


@dataclass
class ColumnSchema:
    """Schema metadata for a single column."""
    name: str
    column_role: ColumnRole
    inferred_type: str  # 'int', 'float', 'datetime', 'string', 'bool'
    null_count: int
    null_percentage: float
    cardinality: int
    is_unique: bool
    has_duplicates: bool
    sample_values: List
    date_format: Optional[str] = None
    numeric_min: Optional[float] = None
    numeric_max: Optional[float] = None
    numeric_mean: Optional[float] = None


@dataclass
class DatasetSchema:
    """Schema metadata for an entire dataset."""
    dataset_name: str
    row_count: int
    column_schemas: Dict[str, ColumnSchema]
    primary_key_candidates: List[str]
    foreign_key_candidates: List[str]
    temporal_columns: List[str]
    numeric_columns: List[str]
    text_columns: List[str]
    contains_anomalies: bool
    anomaly_summary: Dict


class SchemaDiscovery:
    """
    Auto-detect column roles and types in any dataset.
    
    Uses statistical analysis and naming heuristics to determine:
    - Primary key candidates (high cardinality, unique, no nulls)
    - Temporal columns (date/time formats)
    - Numeric columns with anomalies (negatives, outliers)
    - Foreign key candidates (naming patterns, low cardinality)
    """
    
    # Patterns for column role detection
    ID_PATTERN = re.compile(r'_?(?:id|identifier|key)_?', re.IGNORECASE)
    DATE_PATTERN = re.compile(r'(?:date|time|created|updated|at)_?', re.IGNORECASE)
    FK_PATTERNS = [
        re.compile(r'([a-z_]*_id)$', re.IGNORECASE),  # user_id, product_id
        re.compile(r'([a-z_]*)_fk$', re.IGNORECASE),  # user_fk
    ]
    
    # Common date formats to try
    DATE_FORMATS = [
        '%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y',
        '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S',
        '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y',
        '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ',
    ]
    
    @staticmethod
    def analyze_dataframe(df: pd.DataFrame, dataset_name: str) -> DatasetSchema:
        """
        Analyze a dataframe and infer schema for all columns.
        
        Args:
            df: The dataframe to analyze
            dataset_name: Name of the dataset for reference
            
        Returns:
            DatasetSchema with inferred roles and types
        """
        column_schemas = {}
        primary_key_candidates = []
        foreign_key_candidates = []
        temporal_columns = []
        numeric_columns = []
        text_columns = []
        anomalies = {}
        
        for col in df.columns:
            schema = SchemaDiscovery._analyze_column(df, col)
            column_schemas[col] = schema
            
            # Categorize columns
            if schema.column_role == ColumnRole.PRIMARY_KEY:
                primary_key_candidates.append(col)
            elif schema.column_role == ColumnRole.FOREIGN_KEY:
                foreign_key_candidates.append(col)
            elif schema.column_role == ColumnRole.TEMPORAL:
                temporal_columns.append(col)
            elif schema.column_role == ColumnRole.NUMERIC:
                numeric_columns.append(col)
                anomalies[col] = SchemaDiscovery._detect_numeric_anomalies(df, col)
            elif schema.column_role == ColumnRole.TEXT:
                text_columns.append(col)
        
        # Check for overall issues
        has_anomalies = any(anomalies.values())
        
        return DatasetSchema(
            dataset_name=dataset_name,
            row_count=len(df),
            column_schemas=column_schemas,
            primary_key_candidates=primary_key_candidates,
            foreign_key_candidates=foreign_key_candidates,
            temporal_columns=temporal_columns,
            numeric_columns=numeric_columns,
            text_columns=text_columns,
            contains_anomalies=has_anomalies,
            anomaly_summary=anomalies
        )
    
    @staticmethod
    def _analyze_column(df: pd.DataFrame, col: str) -> ColumnSchema:
        """Analyze a single column and determine its role and type."""
        series = df[col]
        null_count = series.isnull().sum()
        null_percentage = (null_count / len(series) * 100) if len(series) > 0 else 0
        cardinality = series.nunique()
        is_unique = cardinality == len(series) - null_count
        has_duplicates = cardinality < len(series) - null_count
        sample_values = series.dropna().unique()[:5].tolist()
        
        # Try to infer type and role
        inferred_type, column_role = SchemaDiscovery._infer_type_and_role(
            series, col, cardinality, is_unique, null_count
        )
        
        # Get specific metadata based on type
        numeric_min = numeric_max = numeric_mean = None
        date_format = None
        
        if inferred_type in ['int', 'float']:
            numeric_series = pd.to_numeric(series, errors='coerce')
            numeric_min = float(numeric_series.min()) if not numeric_series.empty else None
            numeric_max = float(numeric_series.max()) if not numeric_series.empty else None
            numeric_mean = float(numeric_series.mean()) if not numeric_series.empty else None
        elif inferred_type == 'datetime':
            date_format = SchemaDiscovery._detect_date_format(series)
        
        return ColumnSchema(
            name=col,
            column_role=column_role,
            inferred_type=inferred_type,
            null_count=int(null_count),
            null_percentage=float(null_percentage),
            cardinality=int(cardinality),
            is_unique=bool(is_unique),
            has_duplicates=bool(has_duplicates),
            sample_values=sample_values,
            date_format=date_format,
            numeric_min=numeric_min,
            numeric_max=numeric_max,
            numeric_mean=numeric_mean
        )
    
    @staticmethod
    def _infer_type_and_role(
        series: pd.Series, 
        col_name: str, 
        cardinality: int, 
        is_unique: bool,
        null_count: int
    ) -> Tuple[str, ColumnRole]:
        """Infer the data type and role of a column."""
        
        # Remove nulls for type inference
        non_null_series = series.dropna()
        
        if len(non_null_series) == 0:
            return 'unknown', ColumnRole.TEXT
        
        # Check if temporal
        if SchemaDiscovery._is_temporal_column(non_null_series, col_name):
            return 'datetime', ColumnRole.TEMPORAL
        
        # Check if numeric
        if SchemaDiscovery._is_numeric_column(non_null_series):
            inferred_type = 'float' if any(isinstance(x, float) for x in non_null_series[:5]) else 'int'
            
            # Determine role: PK, FK, or just numeric
            if SchemaDiscovery._looks_like_primary_key(is_unique, null_count, cardinality, len(series)):
                return inferred_type, ColumnRole.PRIMARY_KEY
            elif SchemaDiscovery._looks_like_foreign_key(col_name, cardinality):
                return inferred_type, ColumnRole.FOREIGN_KEY
            elif SchemaDiscovery._looks_like_identifier(col_name):
                return inferred_type, ColumnRole.IDENTIFIER
            else:
                return inferred_type, ColumnRole.NUMERIC
        
        # Otherwise text
        inferred_type = 'string'
        if SchemaDiscovery._looks_like_primary_key(is_unique, null_count, cardinality, len(series)):
            return inferred_type, ColumnRole.PRIMARY_KEY
        elif SchemaDiscovery._looks_like_foreign_key(col_name, cardinality):
            return inferred_type, ColumnRole.FOREIGN_KEY
        elif SchemaDiscovery._looks_like_identifier(col_name):
            return inferred_type, ColumnRole.IDENTIFIER
        else:
            return inferred_type, ColumnRole.TEXT
    
    @staticmethod
    def _is_temporal_column(series: pd.Series, col_name: str) -> bool:
        """Check if column contains temporal data."""
        # First check naming
        if SchemaDiscovery.DATE_PATTERN.search(col_name):
            return True
        
        # Try parsing as datetime
        sample = series.head(10)
        for fmt in SchemaDiscovery.DATE_FORMATS:
            try:
                pd.to_datetime(sample, format=fmt)
                return True
            except (ValueError, TypeError):
                continue
        
        # Check if it's a datetime already
        if pd.api.types.is_datetime64_any_dtype(series):
            return True
        
        return False
    
    @staticmethod
    def _is_numeric_column(series: pd.Series) -> bool:
        """Check if column contains numeric data."""
        if pd.api.types.is_numeric_dtype(series):
            return True
        
        # Try converting string values to numeric
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            numeric_series = pd.to_numeric(series, errors='coerce')
            non_null_original = series.notna().sum()
            non_null_converted = numeric_series.notna().sum()
            # If >80% of non-null values convert to numeric, treat as numeric
            return non_null_converted / non_null_original > 0.8 if non_null_original > 0 else False
        
        return False
    
    @staticmethod
    def _looks_like_primary_key(
        is_unique: bool, 
        null_count: int, 
        cardinality: int,
        total_rows: int
    ) -> bool:
        """Heuristic: does this column look like a primary key?"""
        # PK characteristics: unique, no nulls, high cardinality
        threshold_cardinality = total_rows * 0.95
        return is_unique and null_count == 0 and cardinality >= threshold_cardinality
    
    @staticmethod
    def _looks_like_foreign_key(col_name: str, cardinality: int) -> bool:
        """Heuristic: does this column look like a foreign key?"""
        # FK naming patterns: ends with _id, and has duplicates (cardinality < rows)
        for pattern in SchemaDiscovery.FK_PATTERNS:
            if pattern.search(col_name):
                return True
        return False
    
    @staticmethod
    def _looks_like_identifier(col_name: str) -> bool:
        """Heuristic: does this column look like an identifier?"""
        return SchemaDiscovery.ID_PATTERN.search(col_name) is not None
    
    @staticmethod
    def _detect_date_format(series: pd.Series) -> Optional[str]:
        """Detect the date format of a column."""
        sample = series.dropna().head(10)
        for fmt in SchemaDiscovery.DATE_FORMATS:
            try:
                pd.to_datetime(sample, format=fmt)
                return fmt
            except (ValueError, TypeError):
                continue
        return None
    
    @staticmethod
    def _detect_numeric_anomalies(df: pd.DataFrame, col: str) -> Dict:
        """Detect anomalies in numeric columns."""
        numeric_series = pd.to_numeric(df[col], errors='coerce')
        anomalies = {
            'all_negative': (numeric_series < 0).all() if len(numeric_series) > 0 else False,
            'any_negative': (numeric_series < 0).any() if len(numeric_series) > 0 else False,
            'all_zero': (numeric_series == 0).all() if len(numeric_series) > 0 else False,
            'outliers_detected': False,
            'outlier_count': 0
        }
        
        # Detect outliers using IQR method
        if len(numeric_series) > 10:
            Q1 = numeric_series.quantile(0.25)
            Q3 = numeric_series.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outlier_count = ((numeric_series < lower_bound) | (numeric_series > upper_bound)).sum()
            anomalies['outliers_detected'] = outlier_count > 0
            anomalies['outlier_count'] = int(outlier_count)
        
        return anomalies
    
    @staticmethod
    def print_schema_report(dataset_schema: DatasetSchema) -> str:
        """Generate a human-readable schema report."""
        report = [
            f"\n{'='*80}",
            f"SCHEMA REPORT: {dataset_schema.dataset_name}",
            f"{'='*80}",
            f"Rows: {dataset_schema.row_count}",
            f"Columns: {len(dataset_schema.column_schemas)}",
            f"",
            f"PRIMARY KEY CANDIDATES: {dataset_schema.primary_key_candidates or 'None detected'}",
            f"FOREIGN KEY CANDIDATES: {dataset_schema.foreign_key_candidates or 'None detected'}",
            f"TEMPORAL COLUMNS: {dataset_schema.temporal_columns or 'None detected'}",
            f"NUMERIC COLUMNS: {dataset_schema.numeric_columns or 'None detected'}",
            f"",
            f"COLUMN DETAILS:",
            f"{'-'*80}",
        ]
        
        for col_name, schema in dataset_schema.column_schemas.items():
            report.append(
                f"{col_name:30} | Role: {schema.column_role.value:15} | "
                f"Type: {schema.inferred_type:10} | Nulls: {schema.null_count:5} | "
                f"Cardinality: {schema.cardinality:6}"
            )
        
        if dataset_schema.contains_anomalies:
            report.append(f"\nANOMALIES DETECTED:")
            for col, anomalies in dataset_schema.anomaly_summary.items():
                if any(anomalies.values()):
                    report.append(f"  {col}: {anomalies}")
        
        report.append(f"{'='*80}\n")
        return "\n".join(report)
