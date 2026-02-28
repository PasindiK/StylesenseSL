"""Ingestion layer for Data Fabric.

Handles data extraction from multiple sources including:
- CSV files
- Databases (SQL)
- APIs
- Cloud storage
"""

from .connectors import SourceConnector, PostgreSQLConnector, S3Connector
from .extractors import DataExtractor, CSVExtractor, APIExtractor
from .sources import DataSource, SourceRegistry
from .folder_scanner import (
    AutoDataLoader,
    DatasetRegistry,
    DatasetMetadata,
    DomainDetector,
    FolderScanner,
)
from .preprocessing import DataPreprocessor
from .validation import (
    DataValidator,
    ValidationReport,
    ValidationIssue,
    ValidationSeverity,
)
from .schema_discovery import SchemaDiscovery, ColumnSchema, DatasetSchema, ColumnRole
from .relationship_discovery import RelationshipDiscovery, Relationship
from .dynamic_validator import DynamicDataValidator
from .data_cleaner import DataCleaner, CleaningReport
from .data_pipeline import DataPipeline

__all__ = [
    "SourceConnector",
    "PostgreSQLConnector",
    "S3Connector",
    "DataExtractor",
    "CSVExtractor",
    "APIExtractor",
    "DataSource",
    "SourceRegistry",
    "AutoDataLoader",
    "DatasetRegistry",
    "DatasetMetadata",
    "DomainDetector",
    "FolderScanner",
    "DataPreprocessor",
    "DataValidator",
    "ValidationReport",
    "ValidationIssue",
    "ValidationSeverity",
    # Dynamic pipeline components
    "SchemaDiscovery",
    "ColumnSchema",
    "DatasetSchema",
    "ColumnRole",
    "RelationshipDiscovery",
    "Relationship",
    "DynamicDataValidator",
    "DataCleaner",
    "CleaningReport",
    "DataPipeline",
]
