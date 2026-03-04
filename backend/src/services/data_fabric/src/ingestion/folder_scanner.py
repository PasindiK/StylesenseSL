"""Automatic folder scanning and CSV file ingestion.

This module provides functionality to:
- Scan folders for CSV files
- Automatically load CSV files as DataFrames
- Register dataset metadata
- Track dataset inventory
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging
import pandas as pd
import re

from .preprocessing import DataPreprocessor
from .validation import DataValidator, ValidationReport
from src.integration.virtual_integration import VirtualIntegrationLayer
from src.metadata.catalog import (
    MetadataCatalog,
    DataAsset,
    DatasetMetadata as CatalogDatasetMetadata,
)
from src.metadata.registry import MetadataRegistry

logger = logging.getLogger(__name__)


@dataclass
class DatasetMetadata:
    """Metadata for an automatically loaded dataset."""

    dataset_name: str
    file_path: str
    file_type: str  # csv, excel, json, parquet, tsv
    row_count: int
    column_count: int
    column_names: List[str]
    detected_domain: str
    file_size_mb: float
    loaded_at: datetime
    data_types: Dict[str, str] = field(default_factory=dict)
    missing_values: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert metadata to dictionary."""
        return {
            "dataset_name": self.dataset_name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "column_names": self.column_names,
            "detected_domain": self.detected_domain,
            "file_size_mb": self.file_size_mb,
            "loaded_at": self.loaded_at.isoformat(),
            "data_types": self.data_types,
            "missing_values": self.missing_values,
        }


class DomainDetector:
    """Detect dataset domain using hybrid approach: column names + filename patterns."""

    # Column-based domain signatures (primary detection method)
    COLUMN_SIGNATURES = {
        "users": {
            "required": ["user_id", "email", "name"],
            "optional": ["username", "password", "account", "customer_id", "registration_date"],
        },
        "products": {
            "required": ["product_id", "name", "price"],
            "optional": ["category", "description", "brand", "sku", "stock"],
        },
        "transactions": {
            "required": ["transaction_id", "amount"],
            "optional": ["user_id", "product_id", "quantity", "date", "payment_method", "order_id"],
        },
        "sales": {
            "required": ["sale_id", "amount"],
            "optional": ["customer_id", "product_id", "date", "revenue", "discount"],
        },
        "interactions": {
            "required": ["user_id"],
            "optional": ["event_type", "timestamp", "session_id", "action", "engagement", "click"],
        },
        "trends": {
            "required": ["date", "value"],
            "optional": ["trend", "forecast", "metric", "rating", "score", "timeseries"],
        },
        "shops": {
            "required": ["shop_id", "name"],
            "optional": ["location", "address", "city", "region", "store_id", "branch"],
        },
        "inventory": {
            "required": ["product_id", "quantity"],
            "optional": ["stock", "warehouse", "sku", "available", "reserved"],
        },
        "analytics": {
            "required": ["metric"],
            "optional": ["value", "kpi", "performance", "report", "score"],
        },
    }

    # Filename patterns (fallback detection method)
    FILENAME_PATTERNS = {
        "users": r"(user|users|customer|customers|account|accounts)",
        "products": r"(product|products|item|items|catalog)",
        "transactions": r"(transaction|transactions|order|orders)",
        "sales": r"(sale|sales|revenue)",
        "interactions": r"(interaction|interactions|engagement|click|view|event|events)",
        "trends": r"(trend|trends|timeseries|time_series|forecast|rating|review)",
        "shops": r"(shop|shops|store|stores|location|branch|retail)",
        "inventory": r"(inventory|stock|warehouse|supply)",
        "analytics": r"(analytics|metric|metrics|kpi|performance|report)",
        "raw": r"(raw|source|original|extract)",
    }

    @classmethod
    def detect_domain(cls, df: pd.DataFrame, filename: str) -> str:
        """Detect domain using hybrid approach: columns first, then filename.

        Args:
            df: Loaded DataFrame with columns to analyze
            filename: CSV filename (without extension) as fallback

        Returns:
            Detected domain name, or 'unknown' if no match
        """
        # Step 1: Try column-based detection (primary method)
        domain_from_columns = cls._detect_from_columns(df)
        if domain_from_columns:
            logger.info(
                f"Detected domain '{domain_from_columns}' for file '{filename}' "
                f"using column analysis"
            )
            return domain_from_columns

        # Step 2: Fallback to filename pattern matching
        domain_from_filename = cls._detect_from_filename(filename)
        if domain_from_filename != "unknown":
            logger.info(
                f"Detected domain '{domain_from_filename}' for file '{filename}' "
                f"using filename pattern"
            )
            return domain_from_filename

        logger.warning(
            f"Could not detect domain for file '{filename}' using either method, "
            f"using 'unknown'"
        )
        return "unknown"

    @classmethod
    def _detect_from_columns(cls, df: pd.DataFrame) -> Optional[str]:
        """Detect domain by analyzing DataFrame column names.

        Args:
            df: DataFrame to analyze

        Returns:
            Domain name or None if no match found
        """
        if df.empty or len(df.columns) == 0:
            return None

        # Normalize column names (lowercase, strip whitespace)
        columns_normalized = {col.lower().strip().replace(" ", "_") for col in df.columns}

        best_match = None
        best_score = 0

        for domain, signature in cls.COLUMN_SIGNATURES.items():
            # Check required columns
            required_cols = {col.lower() for col in signature["required"]}
            required_matches = len(required_cols.intersection(columns_normalized))

            # Must have at least one required column match
            if required_matches == 0:
                continue

            # Check optional columns
            optional_cols = {col.lower() for col in signature["optional"]}
            optional_matches = len(optional_cols.intersection(columns_normalized))

            # Calculate score: weighted by required columns
            score = (required_matches * 3) + optional_matches

            if score > best_score:
                best_score = score
                best_match = domain

        # Require minimum score threshold
        if best_score >= 3:  # At least 1 required match or 3 optional matches
            return best_match

        return None

    @classmethod
    def _detect_from_filename(cls, filename: str) -> str:
        """Detect domain from filename using pattern matching.

        Args:
            filename: CSV filename (without extension)

        Returns:
            Detected domain name, or 'unknown' if no match
        """
        filename_lower = filename.lower()

        # Check against all filename patterns
        for domain, pattern in cls.FILENAME_PATTERNS.items():
            if re.search(pattern, filename_lower):
                return domain

        return "unknown"


class FolderScanner:
    """Scan folders for data files (CSV, Excel, JSON, Parquet, TSV) and register metadata."""

    # Supported file formats
    SUPPORTED_FORMATS = {
        ".csv": "csv",
        ".xlsx": "excel",
        ".xls": "excel",
        ".json": "json",
        ".parquet": "parquet",
        ".tsv": "tsv",
        ".txt": "tsv",  # Assume .txt files are tab-separated
    }

    def __init__(self, folder_path: str):
        """Initialize folder scanner.

        Args:
            folder_path: Path to folder containing data files
        """
        self.folder_path = Path(folder_path)
        if not self.folder_path.exists():
            raise ValueError(f"Folder not found: {folder_path}")

        if not self.folder_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")

        logger.info(f"Initialized FolderScanner for: {folder_path}")

    def scan_for_data_files(self, recursive: bool = False) -> List[Path]:
        """Scan folder for all supported data files.

        Args:
            recursive: If True, scan subdirectories recursively

        Returns:
            List of data file paths
        """
        data_files = []
        
        for extension in self.SUPPORTED_FORMATS.keys():
            if recursive:
                files = list(self.folder_path.rglob(f"*{extension}"))
            else:
                files = list(self.folder_path.glob(f"*{extension}"))
            data_files.extend(files)
        
        data_files = sorted(data_files)
        
        # Count by type for logging
        type_counts = {}
        for file in data_files:
            file_type = self.SUPPORTED_FORMATS.get(file.suffix.lower())
            type_counts[file_type] = type_counts.get(file_type, 0) + 1
        
        scan_type = "recursive" if recursive else "flat"
        logger.info(
            f"Found {len(data_files)} data files ({scan_type} scan): "
            f"{', '.join(f'{count} {ftype}' for ftype, count in sorted(type_counts.items()))}"
        )
        
        return data_files

    def scan_for_csv_files(self, recursive: bool = False) -> List[Path]:
        """Scan folder for CSV files only (backward compatibility).

        Args:
            recursive: If True, scan subdirectories recursively

        Returns:
            List of CSV file paths
        """
        if recursive:
            csv_files = list(self.folder_path.rglob("*.csv"))
        else:
            csv_files = list(self.folder_path.glob("*.csv"))
        
        logger.info(f"Found {len(csv_files)} CSV files")
        return sorted(csv_files)

    def get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in megabytes.

        Args:
            file_path: Path to file

        Returns:
            File size in MB
        """
        size_bytes = file_path.stat().st_size
        return size_bytes / (1024 * 1024)

    def detect_file_type(self, file_path: Path) -> Optional[str]:
        """Detect file type from extension.

        Args:
            file_path: Path to file

        Returns:
            File type string or None if unsupported
        """
        return self.SUPPORTED_FORMATS.get(file_path.suffix.lower())

    def load_data_file(
        self,
        file_path: Path,
        enable_preprocessing: bool = True,
        normalize_columns: bool = True,
        normalize_dates: bool = True,
        normalize_numeric: bool = True,
        dataset_name: Optional[str] = None,
        metadata_catalog: Optional[MetadataCatalog] = None,
        metadata_registry: Optional[MetadataRegistry] = None,
        producer_pipeline: str = "ingestion.auto_data_loader",
    ) -> Optional[pd.DataFrame]:
        """Load a data file as DataFrame (supports multiple formats).

        Args:
            file_path: Path to data file
            enable_preprocessing: Apply automatic preprocessing transformations
            normalize_columns: Convert column names to snake_case
            normalize_dates: Convert date columns to ISO format
            normalize_numeric: Convert numeric columns to proper types
            dataset_name: Dataset name for metadata synchronization
            metadata_catalog: Optional MetadataCatalog for preprocessing notifications
            metadata_registry: Optional MetadataRegistry for version history
            producer_pipeline: Pipeline identifier

        Returns:
            Loaded DataFrame or None if loading fails
        """
        file_type = self.detect_file_type(file_path)
        
        if not file_type:
            logger.error(f"Unsupported file type: {file_path.suffix}")
            return None

        try:
            # Load based on file type
            if file_type == "csv":
                df = pd.read_csv(file_path)
            elif file_type == "excel":
                df = pd.read_excel(file_path, engine="openpyxl")
            elif file_type == "json":
                df = pd.read_json(file_path)
            elif file_type == "parquet":
                df = pd.read_parquet(file_path)
            elif file_type == "tsv":
                df = pd.read_csv(file_path, sep="\t")
            else:
                logger.error(f"Handler not implemented for type: {file_type}")
                return None

            logger.info(
                f"Loaded {file_path.name} ({file_type}): "
                f"{len(df)} rows, {len(df.columns)} columns"
            )

            # Apply preprocessing if enabled
            if enable_preprocessing:
                df = DataPreprocessor.preprocess(
                    df,
                    normalize_columns=normalize_columns,
                    normalize_dates=normalize_dates,
                    normalize_numeric=normalize_numeric,
                    dataset_name=dataset_name or file_path.stem,
                    metadata_catalog=metadata_catalog,
                    metadata_registry=metadata_registry,
                    producer_pipeline=producer_pipeline,
                )

            return df
            
        except Exception as e:
            logger.error(f"Failed to load {file_path.name}: {e}")
            return None

    def load_csv_file(self, file_path: Path) -> Optional[pd.DataFrame]:
        """Load a CSV file as DataFrame (backward compatibility).

        Args:
            file_path: Path to CSV file

        Returns:
            Loaded DataFrame or None if loading fails
        """
        return self.load_data_file(file_path)

    def create_metadata(
        self, dataframe: pd.DataFrame, file_path: Path
    ) -> DatasetMetadata:
        """Create metadata for a dataset.

        Args:
            dataframe: Loaded DataFrame
            file_path: Path to source file

        Returns:
            DatasetMetadata object
        """
        dataset_name = file_path.stem  # Filename without extension
        file_type = self.detect_file_type(file_path) or "unknown"
        domain = DomainDetector.detect_domain(dataframe, dataset_name)

        # Calculate missing values
        missing_values = dataframe.isnull().sum().to_dict()

        # Get data types
        data_types = dataframe.dtypes.astype(str).to_dict()

        metadata = DatasetMetadata(
            dataset_name=dataset_name,
            file_path=str(file_path),
            file_type=file_type,
            row_count=len(dataframe),
            column_count=len(dataframe.columns),
            column_names=dataframe.columns.tolist(),
            detected_domain=domain,
            file_size_mb=self.get_file_size_mb(file_path),
            loaded_at=datetime.now(),
            data_types=data_types,
            missing_values={k: int(v) for k, v in missing_values.items()},
        )

        return metadata


class DatasetRegistry:
    """Registry for managing loaded datasets in memory."""

    def __init__(self):
        """Initialize dataset registry."""
        self.datasets: Dict[str, pd.DataFrame] = {}
        self.metadata: Dict[str, DatasetMetadata] = {}
        self.domain_index: Dict[str, List[str]] = {}  # domain -> dataset names

        logger.info("Initialized DatasetRegistry")

    def register_dataset(
        self,
        dataset_name: str,
        dataframe: pd.DataFrame,
        metadata: DatasetMetadata,
    ) -> bool:
        """Register a dataset in the registry.

        Args:
            dataset_name: Name of the dataset
            dataframe: DataFrame object
            metadata: Dataset metadata

        Returns:
            True if successfully registered
        """
        if dataset_name in self.datasets:
            logger.warning(f"Dataset '{dataset_name}' already registered, overwriting")

        self.datasets[dataset_name] = dataframe
        self.metadata[dataset_name] = metadata

        # Index by domain
        domain = metadata.detected_domain
        if domain not in self.domain_index:
            self.domain_index[domain] = []
        if dataset_name not in self.domain_index[domain]:
            self.domain_index[domain].append(dataset_name)

        logger.info(
            f"Registered dataset: {dataset_name} (domain: {domain}, "
            f"{metadata.row_count} rows, {metadata.column_count} columns)"
        )
        return True

    def get_dataset(self, dataset_name: str) -> Optional[pd.DataFrame]:
        """Get a dataset by name.

        Args:
            dataset_name: Name of the dataset

        Returns:
            DataFrame or None if not found
        """
        return self.datasets.get(dataset_name)

    def get_metadata(self, dataset_name: str) -> Optional[DatasetMetadata]:
        """Get metadata for a dataset.

        Args:
            dataset_name: Name of the dataset

        Returns:
            DatasetMetadata or None if not found
        """
        return self.metadata.get(dataset_name)

    def get_datasets_by_domain(self, domain: str) -> Dict[str, pd.DataFrame]:
        """Get all datasets in a specific domain.

        Args:
            domain: Domain name

        Returns:
            Dictionary of dataset_name -> DataFrame
        """
        dataset_names = self.domain_index.get(domain, [])
        return {name: self.datasets[name] for name in dataset_names if name in self.datasets}

    def list_datasets(self, domain: Optional[str] = None) -> List[str]:
        """List all loaded dataset names.

        Args:
            domain: Optional filter by domain

        Returns:
            List of dataset names
        """
        if domain:
            return self.domain_index.get(domain, [])
        return sorted(list(self.datasets.keys()))

    def get_all_metadata(self) -> Dict[str, DatasetMetadata]:
        """Get metadata for all datasets.

        Returns:
            Dictionary of dataset_name -> DatasetMetadata
        """
        return self.metadata.copy()

    def get_statistics(self) -> Dict:
        """Get registry statistics.

        Returns:
            Dictionary with statistics
        """
        total_rows = sum(len(df) for df in self.datasets.values())
        total_size_mb = sum(meta.file_size_mb for meta in self.metadata.values())

        return {
            "total_datasets": len(self.datasets),
            "datasets_by_domain": {
                domain: len(names) for domain, names in self.domain_index.items()
            },
            "total_rows": total_rows,
            "total_size_mb": round(total_size_mb, 2),
            "dataset_names": self.list_datasets(),
        }

    def remove_dataset(self, dataset_name: str) -> bool:
        """Remove a dataset from registry.

        Args:
            dataset_name: Name of dataset to remove

        Returns:
            True if successfully removed
        """
        if dataset_name not in self.datasets:
            logger.warning(f"Dataset '{dataset_name}' not found")
            return False

        # Remove from datasets and metadata
        del self.datasets[dataset_name]
        metadata = self.metadata.pop(dataset_name)

        # Remove from domain index
        domain = metadata.detected_domain
        if domain in self.domain_index:
            self.domain_index[domain] = [
                name for name in self.domain_index[domain] if name != dataset_name
            ]

        logger.info(f"Removed dataset: {dataset_name}")
        return True

    def clear(self) -> None:
        """Clear all datasets from registry."""
        count = len(self.datasets)
        self.datasets.clear()
        self.metadata.clear()
        self.domain_index.clear()
        logger.info(f"Cleared registry ({count} datasets removed)")


class AutoDataLoader:
    """Automatically scan and load all data files (CSV, Excel, JSON, Parquet, TSV) from a folder."""

    def __init__(self, folder_path: str):
        """Initialize auto data loader.

        Args:
            folder_path: Path to folder containing CSV files
        """
        self.folder_path = folder_path
        self.scanner = FolderScanner(folder_path)
        self.registry = DatasetRegistry()
        self.metadata_catalog = MetadataCatalog()
        self.metadata_registry = MetadataRegistry()
        self.last_validation_report: Optional[ValidationReport] = None
        self.last_relationship_inferences: List[Any] = []

        logger.info(f"Initialized AutoDataLoader for: {folder_path}")

    def _log_structured(self, event: str, **fields) -> None:
        """Emit structured log events for ingestion operations."""
        payload = " ".join([f"{k}={v}" for k, v in sorted(fields.items())])
        logger.info(f"event={event} {payload}")

    def _upsert_metadata_catalog(
        self,
        dataset_name: str,
        metadata: DatasetMetadata,
        producer_pipeline: str = "ingestion.auto_data_loader",
    ) -> None:
        """Register or update dataset metadata in MetadataCatalog."""
        asset_id = dataset_name
        now = datetime.now()

        existing_asset = self.metadata_catalog.get_asset(asset_id)
        created_at = existing_asset.metadata.created_at if existing_asset else now

        catalog_metadata = CatalogDatasetMetadata(
            name=dataset_name,
            description=f"Auto-ingested dataset: {dataset_name}",
            owner="ingestion",
            source_system=metadata.file_type,
            schema=metadata.data_types,
            row_count=metadata.row_count,
            column_count=metadata.column_count,
            created_at=created_at,
            updated_at=now,
            tags=[metadata.detected_domain],
            properties={
                "domain": metadata.detected_domain,
                "producer_pipeline": producer_pipeline,
                "file_path": metadata.file_path,
                "loaded_at": metadata.loaded_at.isoformat(),
                "last_updated": now.isoformat(),
            },
        )

        if existing_asset:
            self.metadata_catalog.update_asset_metadata(asset_id, catalog_metadata)
            self._log_structured(
                "metadata_catalog.asset_updated",
                dataset_name=dataset_name,
                asset_id=asset_id,
                row_count=metadata.row_count,
                domain=metadata.detected_domain,
                producer_pipeline=producer_pipeline,
                last_updated=catalog_metadata.updated_at.isoformat(),
            )
            return

        asset = DataAsset(
            asset_id=asset_id,
            name=dataset_name,
            asset_type="table",
            location=metadata.file_path,
            metadata=catalog_metadata,
        )

        self.metadata_catalog.register_asset(asset)
        self._log_structured(
            "metadata_catalog.asset_registered",
            dataset_name=dataset_name,
            asset_id=asset_id,
            row_count=metadata.row_count,
            domain=metadata.detected_domain,
            producer_pipeline=producer_pipeline,
            last_updated=catalog_metadata.updated_at.isoformat(),
        )

    def load_all_datasets(
        self,
        recursive: bool = False,
        file_types: Optional[List[str]] = None,
        enable_preprocessing: bool = True,
        normalize_columns: bool = True,
        normalize_dates: bool = True,
        normalize_numeric: bool = True,
        enable_validation: bool = True,
        check_primary_keys: bool = True,
        check_foreign_keys: bool = True,
        check_missing_values: bool = True,
        check_anomalies: bool = True,
        enable_relationship_inference: bool = True,
    ) -> DatasetRegistry:
        """Automatically scan and load all supported data files.

        Args:
            recursive: If True, scan subdirectories recursively
            file_types: Optional list of file types to load (e.g., ['csv', 'excel'])
                       If None, loads all supported formats
            enable_preprocessing: Apply automatic preprocessing transformations
            normalize_columns: Convert column names to snake_case
            normalize_dates: Convert date columns to ISO format
            normalize_numeric: Convert numeric columns to proper types
            enable_validation: Run validation automatically after loading
            check_primary_keys: Enable primary key checks in validation
            check_foreign_keys: Enable foreign key checks in validation
            check_missing_values: Enable missing value checks in validation
            check_anomalies: Enable anomaly checks in validation
            enable_relationship_inference: Run relationship inference and metadata
                registration after validation

        Returns:
            Populated DatasetRegistry
        """
        logger.info(f"Starting automatic data loading from: {self.folder_path}")
        if enable_preprocessing:
            logger.info("Preprocessing enabled: columns → snake_case, dates → ISO, numerics → typed")

        data_files = self.scanner.scan_for_data_files(recursive=recursive)

        # Filter by file types if specified
        if file_types:
            data_files = [
                f for f in data_files 
                if self.scanner.detect_file_type(f) in file_types
            ]
            logger.info(f"Filtered to {len(data_files)} files matching types: {file_types}")

        if not data_files:
            logger.warning(f"No data files found in {self.folder_path}")
            return self.registry

        successful_loads = 0
        failed_loads = 0

        for file_path in data_files:
            # Load data file with preprocessing
            df = self.scanner.load_data_file(
                file_path,
                enable_preprocessing=enable_preprocessing,
                normalize_columns=normalize_columns,
                normalize_dates=normalize_dates,
                normalize_numeric=normalize_numeric,
                dataset_name=file_path.stem,
                metadata_catalog=self.metadata_catalog,
                metadata_registry=self.metadata_registry,
                producer_pipeline="ingestion.auto_data_loader",
            )

            if df is None:
                failed_loads += 1
                continue

            # Create metadata
            metadata = self.scanner.create_metadata(df, file_path)

            # Register in registry
            dataset_name = file_path.stem
            self.registry.register_dataset(dataset_name, df, metadata)
            self._upsert_metadata_catalog(
                dataset_name=dataset_name,
                metadata=metadata,
                producer_pipeline="ingestion.auto_data_loader",
            )
            successful_loads += 1

        logger.info(
            f"Data loading complete: {successful_loads} loaded, {failed_loads} failed"
        )

        if enable_validation and successful_loads > 0:
            logger.info("Starting automatic validation after ingestion")
            validator = DataValidator(metadata_catalog=self.metadata_catalog)
            self.last_validation_report = validator.validate_registry(
                self.registry,
                check_primary_keys=check_primary_keys,
                check_foreign_keys=check_foreign_keys,
                check_missing_values=check_missing_values,
                check_anomalies=check_anomalies,
            )
            logger.info(
                "Automatic validation complete: "
                f"issues={len(self.last_validation_report.issues)} "
                f"datasets={self.last_validation_report.total_datasets}"
            )

        if enable_relationship_inference and successful_loads >= 2:
            logger.info("Starting automatic relationship inference after validation")
            integration_layer = VirtualIntegrationLayer(metadata_catalog=self.metadata_catalog)
            self.last_relationship_inferences = integration_layer.infer_relationships(
                datasets=self.registry.datasets,
                register_results=True,
            )
            strong_count = sum(
                1
                for rel in self.last_relationship_inferences
                if getattr(rel, "decision", "") == "strong"
            )
            probable_count = sum(
                1
                for rel in self.last_relationship_inferences
                if getattr(rel, "decision", "") == "probable"
            )
            logger.info(
                "Automatic relationship inference complete: "
                f"total={len(self.last_relationship_inferences)} "
                f"strong={strong_count} probable={probable_count}"
            )

        return self.registry

    def get_registry(self) -> DatasetRegistry:
        """Get the populated registry.

        Returns:
            DatasetRegistry
        """
        return self.registry

    def print_inventory(self) -> None:
        """Print a summary of loaded datasets."""
        stats = self.registry.get_statistics()

        print("\n" + "=" * 80)
        print("DATA INVENTORY SUMMARY")
        print("=" * 80)
        print(f"Total Datasets: {stats['total_datasets']}")
        print(f"Total Rows: {stats['total_rows']:,}")
        print(f"Total Size: {stats['total_size_mb']} MB")
        
        # Show file type breakdown
        file_type_counts = {}
        for dataset_name in self.registry.list_datasets():
            metadata = self.registry.get_metadata(dataset_name)
            if metadata:
                file_type = metadata.file_type
                file_type_counts[file_type] = file_type_counts.get(file_type, 0) + 1
        
        print(f"\nDatasets by File Type:")
        for file_type, count in sorted(file_type_counts.items()):
            print(f"  • {file_type}: {count} dataset(s)")

        print(f"\nDatasets by Domain:")
        for domain, count in sorted(stats["datasets_by_domain"].items()):
            print(f"  • {domain}: {count} dataset(s)")

        print(f"\nDetailed Dataset List:")
        print("-" * 80)
        print(f"{'Name':<25} {'Type':<8} {'Domain':<12} {'Rows':<10} {'Columns':<10}")
        print("-" * 80)

        for dataset_name in sorted(self.registry.list_datasets()):
            metadata = self.registry.get_metadata(dataset_name)
            if metadata:
                print(
                    f"{metadata.dataset_name:<25} {metadata.file_type:<8} "
                    f"{metadata.detected_domain:<12} {metadata.row_count:<10} "
                    f"{metadata.column_count:<10}"
                )

        print("=" * 80 + "\n")
