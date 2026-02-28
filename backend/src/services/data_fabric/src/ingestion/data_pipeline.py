"""
Unified dynamic data pipeline.

Orchestrates the complete data workflow:
1. Load datasets from folder
2. Discover schema and relationships
3. Preprocess data (normalize columns, dates, types)
4. Validate data quality
5. Clean data (remove duplicates, orphans, nulls)
6. Export cleaned datasets

Fully dynamic - works with ANY CSV data without hardcoding.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from .schema_discovery import SchemaDiscovery, DatasetSchema
from .relationship_discovery import RelationshipDiscovery, Relationship
from .preprocessing import DataPreprocessor
from .dynamic_validator import DynamicDataValidator, ValidationReport
from .data_cleaner import DataCleaner, CleaningReport


class DataPipeline:
    """
    Complete data pipeline orchestrator.
    
    Workflow:
        load_all_datasets() -> discover_schema() -> discover_relationships()
        -> preprocess_all() -> validate_all() -> clean_all() -> export_cleaned()
    """
    
    def __init__(self, data_folder: str):
        """
        Initialize pipeline with data folder.
        
        Args:
            data_folder: Path to folder containing CSV files
        """
        self.data_folder = Path(data_folder)
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self.raw_datasets: Dict[str, pd.DataFrame] = {}
        self.preprocessed_datasets: Dict[str, pd.DataFrame] = {}
        self.cleaned_datasets: Dict[str, pd.DataFrame] = {}
        
        # Discovery results
        self.schemas: Dict[str, DatasetSchema] = {}
        self.relationships: List[Relationship] = []
        
        # Extracted configuration from discovery
        self.primary_keys: Dict[str, List[str]] = {}
        self.foreign_keys: List[Tuple[str, str, str, str]] = []
        self.numeric_anomalies: Dict[str, List[str]] = {}
        
        # Reports
        self.validation_reports: Dict[str, ValidationReport] = {
            "before_cleaning": None,
            "after_cleaning": None
        }
        self.cleaning_reports: Dict[str, CleaningReport] = {}
    
    # ========== STEP 1: LOAD ==========
    def load_all_datasets(self) -> Dict[str, pd.DataFrame]:
        """Load all CSV files from data folder."""
        self.logger.info(f"Loading datasets from {self.data_folder}")
        csv_files = list(self.data_folder.glob("*.csv"))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {self.data_folder}")
        
        for csv_file in csv_files:
            dataset_name = csv_file.stem
            try:
                df = pd.read_csv(csv_file)
                self.raw_datasets[dataset_name] = df
                self.logger.info(f"Loaded {dataset_name}: {len(df)} rows × {len(df.columns)} columns")
            except Exception as e:
                self.logger.error(f"Failed to load {csv_file}: {e}")
        
        return self.raw_datasets
    
    # ========== STEP 2: DISCOVERY ==========
    def discover_schema(self) -> Dict[str, DatasetSchema]:
        """Discover schema of all loaded datasets."""
        if not self.raw_datasets:
            raise ValueError("No datasets loaded. Call load_all_datasets() first.")
        
        self.logger.info("Discovering schema...")
        for dataset_name, df in self.raw_datasets.items():
            schema = SchemaDiscovery.analyze_dataframe(df, dataset_name)
            self.schemas[dataset_name] = schema
            self._extract_primary_keys(schema)
            self._extract_numeric_anomalies(schema)
        
        self.logger.info(f"Schema discovery complete. Found {len(self.schemas)} datasets.")
        return self.schemas
    
    def discover_relationships(self) -> List[Relationship]:
        """Discover foreign key relationships between datasets."""
        if not self.raw_datasets:
            raise ValueError("No datasets loaded. Call load_all_datasets() first.")
        
        self.logger.info("Discovering relationships...")
        self.relationships = RelationshipDiscovery.discover_relationships(
            self.raw_datasets,
            self.primary_keys
        )
        
        # Convert relationships to FK list format
        for rel in self.relationships:
            if rel.confidence >= 0.6:  # Only high-confidence relationships
                self.foreign_keys.append(
                    (rel.child_dataset, rel.child_column, rel.parent_dataset, rel.parent_column)
                )
        
        self.logger.info(f"Discovered {len(self.foreign_keys)} foreign key relationships.")
        return self.relationships
    
    def _extract_primary_keys(self, schema: DatasetSchema) -> None:
        """Extract primary keys from schema."""
        if schema.primary_key_candidates:
            self.primary_keys[schema.dataset_name] = schema.primary_key_candidates
    
    def _extract_numeric_anomalies(self, schema: DatasetSchema) -> None:
        """Extract numeric anomalies from schema."""
        for col, anomalies in schema.anomaly_summary.items():
            if any(v for v in anomalies.values() if v is not True and v is not False):
                # Has actual anomaly values
                anomaly_types = []
                if anomalies.get('all_negative') or anomalies.get('any_negative'):
                    anomaly_types.append('negative')
                if anomalies.get('outliers_detected'):
                    anomaly_types.append('outliers')
                if anomaly_types:
                    self.numeric_anomalies[f"{schema.dataset_name}.{col}"] = anomaly_types
    
    # ========== STEP 3: PREPROCESSING ==========
    def preprocess_all(
        self,
        normalize_columns: bool = True,
        normalize_dates: bool = True,
        normalize_numeric: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """Preprocess all datasets."""
        if not self.raw_datasets:
            raise ValueError("No datasets loaded. Call load_all_datasets() first.")
        
        self.logger.info("Preprocessing all datasets...")
        preprocessor = DataPreprocessor()
        
        for dataset_name, df in self.raw_datasets.items():
            df_preprocessed = preprocessor.preprocess(
                df,
                normalize_columns=normalize_columns,
                normalize_dates=normalize_dates,
                normalize_numeric=normalize_numeric
            )
            self.preprocessed_datasets[dataset_name] = df_preprocessed
        
        self.logger.info("Preprocessing complete.")
        return self.preprocessed_datasets
    
    # ========== STEP 4: VALIDATION (BEFORE CLEANING) ==========
    def validate_before_cleaning(self) -> ValidationReport:
        """Validate preprocessed datasets (before cleaning)."""
        if not self.preprocessed_datasets:
            raise ValueError("No preprocessed datasets. Call preprocess_all() first.")
        
        if not self.schemas:
            raise ValueError("No schema information. Call discover_schema() first.")
        
        self.logger.info("Running validation (before cleaning)...")
        validator = DynamicDataValidator()
        
        report = validator.validate_all_datasets(
            self.preprocessed_datasets,
            self.primary_keys,
            self.foreign_keys,
            self.numeric_anomalies
        )
        
        self.validation_reports["before_cleaning"] = report
        self.logger.info(f"Found {len(report.issues)} issues before cleaning.")
        return report
    
    # ========== STEP 5: CLEANING ==========
    def clean_all(
        self,
        drop_orphans: bool = True,
        fill_missing: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """Clean all datasets."""
        if not self.preprocessed_datasets:
            raise ValueError("No preprocessed datasets. Call preprocess_all() first.")
        
        self.logger.info("Cleaning all datasets...")
        cleaner = DataCleaner()
        
        self.cleaned_datasets, self.cleaning_reports = cleaner.clean_datasets(
            self.preprocessed_datasets,
            self.primary_keys,
            self.foreign_keys,
            drop_orphans=drop_orphans,
            fill_missing=fill_missing
        )
        
        self.logger.info("Cleaning complete.")
        return self.cleaned_datasets
    
    # ========== STEP 6: VALIDATION (AFTER CLEANING) ==========
    def validate_after_cleaning(self) -> ValidationReport:
        """Validate cleaned datasets (after cleaning)."""
        if not self.cleaned_datasets:
            raise ValueError("No cleaned datasets. Call clean_all() first.")
        
        self.logger.info("Running validation (after cleaning)...")
        validator = DynamicDataValidator()
        
        report = validator.validate_all_datasets(
            self.cleaned_datasets,
            self.primary_keys,
            self.foreign_keys,
            self.numeric_anomalies
        )
        
        self.validation_reports["after_cleaning"] = report
        self.logger.info(f"Found {len(report.issues)} issues after cleaning.")
        return report
    
    # ========== STEP 7: EXPORT ==========
    def export_cleaned_datasets(self, output_folder: str) -> Dict[str, str]:
        """Export cleaned datasets to CSV files."""
        if not self.cleaned_datasets:
            raise ValueError("No cleaned datasets. Call clean_all() first.")
        
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Exporting cleaned datasets to {output_path}")
        exported_files = {}
        
        for dataset_name, df in self.cleaned_datasets.items():
            output_file = output_path / f"{dataset_name}_cleaned.csv"
            df.to_csv(output_file, index=False)
            exported_files[dataset_name] = str(output_file)
            self.logger.info(f"Exported {dataset_name}: {len(df)} rows × {len(df.columns)} columns")
        
        return exported_files
    
    # ========== REPORTING ==========
    def print_schema_summary(self) -> str:
        """Print schema discovery summary."""
        output = [f"\n{'='*100}", "SCHEMA DISCOVERY SUMMARY", f"{'='*100}"]
        for schema in self.schemas.values():
            output.append(SchemaDiscovery.print_schema_report(schema))
        return "\n".join(output)
    
    def print_relationships_summary(self) -> str:
        """Print discovered relationships summary."""
        return RelationshipDiscovery.print_relationships_report(self.relationships)
    
    def print_validation_summary(self) -> str:
        """Print before/after validation comparison."""
        output = [f"\n{'='*100}"]
        
        if self.validation_reports["before_cleaning"]:
            output.append("VALIDATION REPORT - BEFORE CLEANING")
            output.append(DynamicDataValidator.print_validation_report(
                self.validation_reports["before_cleaning"]
            ))
        
        if self.validation_reports["after_cleaning"]:
            output.append("VALIDATION REPORT - AFTER CLEANING")
            output.append(DynamicDataValidator.print_validation_report(
                self.validation_reports["after_cleaning"]
            ))
        
        output.append(f"{'='*100}\n")
        return "\n".join(output)
    
    def print_cleaning_summary(self) -> str:
        """Print cleaning actions summary."""
        output = [f"\n{'='*100}", "CLEANING ACTIONS SUMMARY", f"{'='*100}"]
        
        for report in self.cleaning_reports.values():
            output.append(report.summary())
        
        output.append(f"{'='*100}\n")
        return "\n".join(output)
    
    def print_pipeline_summary(self) -> str:
        """Print complete pipeline summary."""
        output = [f"\n{'='*100}", "DATA PIPELINE EXECUTION SUMMARY", f"{'='*100}"]
        
        output.append(f"\n1. DATASETS LOADED: {len(self.raw_datasets)}")
        for name, df in self.raw_datasets.items():
            output.append(f"   • {name}: {len(df)} rows")
        
        output.append(f"\n2. SCHEMA DISCOVERED: {len(self.schemas)} datasets")
        output.append(f"   Primary keys identified: {len(self.primary_keys)}")
        output.append(f"   Relationships discovered: {len(self.foreign_keys)}")
        
        output.append(f"\n3. PREPROCESSING: {len(self.preprocessed_datasets)} datasets")
        
        if self.validation_reports["before_cleaning"]:
            output.append(f"\n4. VALIDATION (BEFORE): {len(self.validation_reports['before_cleaning'].issues)} issues")
        
        if self.cleaning_reports:
            total_removed = sum(r.rows_removed for r in self.cleaning_reports.values())
            output.append(f"\n5. CLEANING: Removed {total_removed} rows")
        
        if self.validation_reports["after_cleaning"]:
            output.append(f"\n6. VALIDATION (AFTER): {len(self.validation_reports['after_cleaning'].issues)} issues")
        
        output.append(f"\n7. EXPORT: {len(self.cleaned_datasets)} datasets cleaned and ready")
        
        output.append(f"{'='*100}\n")
        return "\n".join(output)
    
    # ========== CONVENIENCE METHODS ==========
    def run_full_pipeline(
        self,
        output_folder: Optional[str] = None
    ) -> Tuple[Dict[str, pd.DataFrame], ValidationReport, ValidationReport]:
        """
        Run complete pipeline: load -> discover -> preprocess -> validate -> clean -> validate.
        
        Args:
            output_folder: Optional folder to export cleaned datasets
            
        Returns:
            (cleaned_datasets, validation_before, validation_after)
        """
        # Load and discover
        self.load_all_datasets()
        self.discover_schema()
        self.discover_relationships()
        
        # Preprocess
        self.preprocess_all()
        
        # Validate before cleaning
        self.validate_before_cleaning()
        
        # Clean
        self.clean_all()
        
        # Validate after cleaning
        self.validate_after_cleaning()
        
        # Export if requested
        if output_folder:
            self.export_cleaned_datasets(output_folder)
        
        return (
            self.cleaned_datasets,
            self.validation_reports["before_cleaning"],
            self.validation_reports["after_cleaning"]
        )
