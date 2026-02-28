"""Data validation module for quality checks and integrity validation.

This module provides:
- Primary key duplicate detection
- Foreign key relationship validation
- Missing value analysis
- Anomaly detection (negative prices, outliers, etc.)
- Comprehensive validation reports
"""

import logging
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    
    severity: ValidationSeverity
    category: str
    description: str
    dataset_name: str
    column_name: Optional[str] = None
    row_count: Optional[int] = None
    sample_values: Optional[List[Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert issue to dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "description": self.description,
            "dataset_name": self.dataset_name,
            "column_name": self.column_name,
            "row_count": self.row_count,
            "sample_values": self.sample_values,
            "details": self.details
        }


@dataclass
class ValidationReport:
    """Comprehensive validation report."""
    
    validation_timestamp: datetime
    total_datasets: int
    total_rows: int
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    dataset_stats: Dict[str, Dict] = field(default_factory=dict)
    
    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue to the report."""
        self.issues.append(issue)
        
        # Update summary counts
        severity_key = f"{issue.severity.value.lower()}_count"
        self.summary[severity_key] = self.summary.get(severity_key, 0) + 1
        
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get all issues of a specific severity."""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_issues_by_dataset(self, dataset_name: str) -> List[ValidationIssue]:
        """Get all issues for a specific dataset."""
        return [issue for issue in self.issues if issue.dataset_name == dataset_name]
    
    def has_critical_issues(self) -> bool:
        """Check if report contains critical issues."""
        return any(issue.severity == ValidationSeverity.CRITICAL for issue in self.issues)
    
    def to_dict(self) -> Dict:
        """Convert report to dictionary."""
        return {
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "total_datasets": self.total_datasets,
            "total_rows": self.total_rows,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "dataset_stats": self.dataset_stats
        }


class DataValidator:
    """Validates data quality and integrity across datasets."""

    PRIMARY_KEYS = {
        "users_dataset": ["user_id"],
        "shops_dataset": ["shop_id"],
        "transactions10K": ["transaction_id"],
        "synthetic_outerwear_sri_lanka_with_shop_ids": ["product_id"],
        "interactions_dataset": ["interaction_id"],
        "trends_dataset": ["trend_id"],
        "user_preferences_dataset": ["preference_id"],
    }

    FOREIGN_KEY_RELATIONSHIPS = [
        # (child_dataset, child_fk, parent_dataset, parent_pk)
        ("transactions10K", "user_id", "users_dataset", "user_id"),
        (
            "transactions10K",
            "product_id",
            "synthetic_outerwear_sri_lanka_with_shop_ids",
            "product_id",
        ),
    ]
    
    def __init__(self, metadata_catalog: Optional[Any] = None):
        """Initialize data validator."""
        self.report = None
        self.primary_keys = self.PRIMARY_KEYS.copy()
        self.foreign_key_relationships = list(self.FOREIGN_KEY_RELATIONSHIPS)
        self.metadata_catalog = metadata_catalog
        logger.info("Initialized DataValidator")
    
    def validate_registry(
        self,
        registry,
        check_primary_keys: bool = True,
        check_foreign_keys: bool = True,
        check_missing_values: bool = True,
        check_anomalies: bool = True
    ) -> ValidationReport:
        """Validate all datasets in a registry.
        
        Args:
            registry: DatasetRegistry to validate
            check_primary_keys: Detect duplicate primary keys
            check_foreign_keys: Validate foreign key relationships
            check_missing_values: Log missing values
            check_anomalies: Detect data anomalies
            
        Returns:
            ValidationReport with all findings
        """
        logger.info("Starting comprehensive data validation")
        
        # Initialize report
        total_rows = sum(len(registry.get_dataset(name)) for name in registry.list_datasets())
        self.report = ValidationReport(
            validation_timestamp=datetime.now(),
            total_datasets=len(registry.list_datasets()),
            total_rows=total_rows
        )
        
        # Run validation checks
        for dataset_name in registry.list_datasets():
            df = registry.get_dataset(dataset_name)
            metadata = registry.get_metadata(dataset_name)
            
            logger.info(f"Validating dataset: {dataset_name}")
            
            # Store dataset statistics
            self.report.dataset_stats[dataset_name] = {
                "rows": len(df),
                "columns": len(df.columns),
                "domain": metadata.detected_domain if metadata else "unknown",
                "missing_cells": df.isnull().sum().sum()
            }
            
            # Primary key checks
            if check_primary_keys:
                self._check_primary_keys(df, dataset_name)
            
            # Missing value checks
            if check_missing_values:
                self._check_missing_values(df, dataset_name)
            
            # Anomaly checks
            if check_anomalies:
                self._check_anomalies(df, dataset_name, metadata)
        
        # Foreign key checks (requires multiple datasets)
        if check_foreign_keys:
            self._check_foreign_keys(registry)
        
        # Generate summary
        self._generate_summary()
        self._update_metadata_catalog_after_validation(registry)
        
        logger.info(f"Validation complete: {len(self.report.issues)} issues found")
        return self.report

    def _update_metadata_catalog_after_validation(self, registry) -> None:
        """Update MetadataCatalog with validation results per dataset."""
        if self.metadata_catalog is None:
            return

        validation_timestamp = datetime.now().isoformat()

        for dataset_name in registry.list_datasets():
            asset = self.metadata_catalog.get_asset(dataset_name)
            if asset is None:
                logger.info(f"Skipping metadata update for '{dataset_name}': asset not found")
                continue

            dataset_issues = self.report.get_issues_by_dataset(dataset_name)
            critical_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.CRITICAL])
            error_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.ERROR])
            warning_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.WARNING])
            info_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.INFO])

            failed = critical_count > 0 or error_count > 0
            validation_status = "Failed" if failed else "Passed"

            penalty = (critical_count * 30) + (error_count * 15) + (warning_count * 5) + (info_count * 1)
            quality_score = float(max(0.0, min(100.0, 100.0 - penalty)))

            metadata = asset.metadata
            metadata.quality_score = quality_score
            metadata.updated_at = datetime.now()
            metadata.properties = {
                **metadata.properties,
                "validation_status": validation_status,
                "validation_timestamp": validation_timestamp,
                "last_updated": metadata.updated_at.isoformat(),
            }

            self.metadata_catalog.update_asset_metadata(dataset_name, metadata)

            logger.info(
                "event=metadata_catalog.validation_updated "
                f"dataset_name={dataset_name} validation_status={validation_status} "
                f"quality_score={quality_score:.2f} validation_timestamp={validation_timestamp}"
            )
    
    def _check_primary_keys(self, df: pd.DataFrame, dataset_name: str):
        """Check for duplicate primary keys."""
        pk_columns = self._identify_primary_key_columns(dataset_name)

        if not pk_columns:
            logger.info(f"No configured primary key for dataset: {dataset_name}")
            return
        
        for col in pk_columns:
            if col not in df.columns:
                continue
                
            # Primary key must not be null
            null_count = int(df[col].isna().sum())
            if null_count > 0:
                self.report.add_issue(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="Primary Key Integrity",
                    description=f"Found {null_count} null values in primary key column",
                    dataset_name=dataset_name,
                    column_name=col,
                    row_count=null_count,
                    details={"total_nulls": null_count},
                ))

            # Check for duplicate non-null keys
            non_null_keys = df[col].dropna()
            duplicates = non_null_keys.duplicated()
            duplicate_count = int(duplicates.sum())
            
            if duplicate_count > 0:
                duplicate_values = non_null_keys[non_null_keys.duplicated(keep=False)].unique()
                
                self.report.add_issue(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="Primary Key Integrity",
                    description=f"Found {duplicate_count} duplicate values in primary key column",
                    dataset_name=dataset_name,
                    column_name=col,
                    row_count=duplicate_count,
                    sample_values=duplicate_values[:5].tolist(),
                    details={
                        "total_duplicates": duplicate_count,
                        "unique_duplicate_values": len(duplicate_values)
                    }
                ))
                logger.warning(f"{dataset_name}.{col}: Found {duplicate_count} duplicates")
            else:
                logger.debug(f"{dataset_name}.{col}: No duplicates found (OK)")
    
    def _check_missing_values(self, df: pd.DataFrame, dataset_name: str):
        """Check for missing values in dataset."""
        missing_counts = df.isnull().sum()
        missing_columns = missing_counts[missing_counts > 0]
        
        if len(missing_columns) > 0:
            total_missing = missing_counts.sum()
            total_cells = len(df) * len(df.columns)
            missing_percentage = (total_missing / total_cells) * 100
            
            # Determine severity based on percentage
            if missing_percentage > 20:
                severity = ValidationSeverity.ERROR
            elif missing_percentage > 10:
                severity = ValidationSeverity.WARNING
            else:
                severity = ValidationSeverity.INFO
            
            for col, count in missing_columns.items():
                col_percentage = (count / len(df)) * 100
                
                self.report.add_issue(ValidationIssue(
                    severity=severity if col_percentage > 10 else ValidationSeverity.INFO,
                    category="Missing Values",
                    description=f"Column has {count} missing values ({col_percentage:.1f}%)",
                    dataset_name=dataset_name,
                    column_name=col,
                    row_count=int(count),
                    details={
                        "percentage": round(col_percentage, 2),
                        "total_rows": len(df)
                    }
                ))
            
            logger.info(f"{dataset_name}: {len(missing_columns)} columns with missing values")
    
    def _check_anomalies(self, df: pd.DataFrame, dataset_name: str, metadata):
        """Check for data anomalies."""
        # Check for negative prices/amounts
        self._check_negative_values(df, dataset_name)
        
        # Check for suspicious patterns
        self._check_suspicious_patterns(df, dataset_name)
        
        # Check for outliers in numeric columns
        self._check_outliers(df, dataset_name)
    
    def _check_negative_values(self, df: pd.DataFrame, dataset_name: str):
        """Check for negative values in columns that should be positive."""
        # Columns that should not be negative
        positive_patterns = [
            'price', 'cost', 'amount', 'quantity', 'count', 'total',
            'age', 'revenue', 'salary', 'balance', 'stock'
        ]
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Check if column matches positive patterns
            if any(pattern in col_lower for pattern in positive_patterns):
                if pd.api.types.is_numeric_dtype(df[col]):
                    negative_count = (df[col] < 0).sum()
                    
                    if negative_count > 0:
                        negative_values = df[df[col] < 0][col].head(5)
                        
                        self.report.add_issue(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            category="Data Anomaly",
                            description=f"Found {negative_count} negative values in column that should be positive",
                            dataset_name=dataset_name,
                            column_name=col,
                            row_count=int(negative_count),
                            sample_values=negative_values.tolist(),
                            details={
                                "min_value": float(df[col].min()),
                                "mean_value": float(df[col].mean())
                            }
                        ))
                        logger.warning(f"{dataset_name}.{col}: Found {negative_count} negative values")
    
    def _check_suspicious_patterns(self, df: pd.DataFrame, dataset_name: str):
        """Check for suspicious patterns in data."""
        # Check for too many identical values (potential data quality issue)
        for col in df.columns:
            if len(df) > 10:  # Only check if sufficient data
                value_counts = df[col].value_counts()
                
                if len(value_counts) > 0:
                    most_common_count = value_counts.iloc[0]
                    most_common_percentage = (most_common_count / len(df)) * 100
                    
                    # If one value appears in >80% of rows, it might be suspicious
                    if most_common_percentage > 80 and len(value_counts) > 1:
                        self.report.add_issue(ValidationIssue(
                            severity=ValidationSeverity.INFO,
                            category="Data Pattern",
                            description=f"One value appears in {most_common_percentage:.1f}% of rows",
                            dataset_name=dataset_name,
                            column_name=col,
                            details={
                                "most_common_value": str(value_counts.index[0]),
                                "occurrence_count": int(most_common_count),
                                "percentage": round(most_common_percentage, 2)
                            }
                        ))
    
    def _check_outliers(self, df: pd.DataFrame, dataset_name: str):
        """Check for statistical outliers in numeric columns."""
        numeric_cols = df.select_dtypes(include=['int64', 'float64', 'Int64']).columns
        
        for col in numeric_cols:
            if df[col].notna().sum() > 0:  # Has non-null values
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                
                # Define outlier bounds
                lower_bound = Q1 - 3 * IQR
                upper_bound = Q3 + 3 * IQR
                
                outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
                outlier_count = len(outliers)
                
                if outlier_count > 0:
                    outlier_percentage = (outlier_count / len(df)) * 100
                    
                    # Only report if significant
                    if outlier_percentage > 5:
                        sample_outliers = outliers[col].head(5)
                        
                        self.report.add_issue(ValidationIssue(
                            severity=ValidationSeverity.INFO,
                            category="Statistical Outlier",
                            description=f"Found {outlier_count} outliers ({outlier_percentage:.1f}%)",
                            dataset_name=dataset_name,
                            column_name=col,
                            row_count=outlier_count,
                            sample_values=sample_outliers.tolist(),
                            details={
                                "lower_bound": float(lower_bound),
                                "upper_bound": float(upper_bound),
                                "percentage": round(outlier_percentage, 2)
                            }
                        ))
    
    def _check_foreign_keys(self, registry):
        """Validate foreign key relationships between datasets."""
        logger.info("Checking foreign key relationships")

        datasets = {
            name: registry.get_dataset(name)
            for name in registry.list_datasets()
        }

        for child_name, child_fk, parent_name, parent_pk in self.foreign_key_relationships:
            if child_name not in datasets:
                logger.info(f"Skipping FK check: child dataset not found: {child_name}")
                continue
            if parent_name not in datasets:
                logger.info(f"Skipping FK check: parent dataset not found: {parent_name}")
                continue

            child_df = datasets[child_name]
            parent_df = datasets[parent_name]

            if child_fk not in child_df.columns:
                logger.info(f"Skipping FK check: {child_name}.{child_fk} not found")
                continue
            if parent_pk not in parent_df.columns:
                logger.info(f"Skipping FK check: {parent_name}.{parent_pk} not found")
                continue

            self._validate_foreign_key_relationship(
                child_df, child_name, child_fk,
                parent_df, parent_name, parent_pk
            )
    
    def _validate_foreign_key_relationship(
        self,
        child_df: pd.DataFrame,
        child_name: str,
        child_fk: str,
        parent_df: pd.DataFrame,
        parent_name: str,
        parent_pk: str
    ):
        """Validate a specific foreign key relationship."""
        # Get non-null foreign key values
        child_fk_values = child_df[child_fk].dropna().unique()
        parent_pk_values = parent_df[parent_pk].dropna().unique()
        
        # Find orphaned records (FK values not in parent)
        orphaned = set(child_fk_values) - set(parent_pk_values)
        
        if len(orphaned) > 0:
            orphaned_count = child_df[child_df[child_fk].isin(orphaned)].shape[0]
            
            self.report.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="Foreign Key Violation",
                description=f"Found {orphaned_count} orphaned records (FK not in parent table)",
                dataset_name=child_name,
                column_name=child_fk,
                row_count=orphaned_count,
                sample_values=list(orphaned)[:5],
                details={
                    "parent_dataset": parent_name,
                    "parent_column": parent_pk,
                    "unique_orphaned_values": len(orphaned),
                    "total_orphaned_rows": orphaned_count
                }
            ))
            logger.warning(
                f"FK violation: {child_name}.{child_fk} -> {parent_name}.{parent_pk}: "
                f"{orphaned_count} orphaned records"
            )
        else:
            logger.debug(
                f"FK valid: {child_name}.{child_fk} -> {parent_name}.{parent_pk}"
            )
    
    def _identify_primary_key_columns(self, dataset_name: str) -> List[str]:
        """Return configured primary key columns for the dataset."""
        return self.primary_keys.get(dataset_name, [])
    
    def _generate_summary(self):
        """Generate validation summary statistics."""
        # Count issues by severity
        self.report.summary["total_issues"] = len(self.report.issues)
        self.report.summary["critical_count"] = len(self.report.get_issues_by_severity(ValidationSeverity.CRITICAL))
        self.report.summary["error_count"] = len(self.report.get_issues_by_severity(ValidationSeverity.ERROR))
        self.report.summary["warning_count"] = len(self.report.get_issues_by_severity(ValidationSeverity.WARNING))
        self.report.summary["info_count"] = len(self.report.get_issues_by_severity(ValidationSeverity.INFO))
        
        # Count issues by category
        category_counts = {}
        for issue in self.report.issues:
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        self.report.summary["by_category"] = category_counts
    
    def print_report(self, report: Optional[ValidationReport] = None, show_all: bool = False):
        """Print validation report in a readable format.
        
        Args:
            report: ValidationReport to print (uses last generated if None)
            show_all: Show all issues (default: only errors and warnings)
        """
        if report is None:
            report = self.report
        
        if report is None:
            print("No validation report available")
            return
        
        print("\n" + "=" * 80)
        print("DATA VALIDATION REPORT")
        print("=" * 80)
        print(f"Timestamp: {report.validation_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Datasets Validated: {report.total_datasets}")
        print(f"Total Rows: {report.total_rows:,}")
        
        print("\n" + "-" * 80)
        print("SUMMARY")
        print("-" * 80)
        print(f"Total Issues: {report.summary.get('total_issues', 0)}")
        print(f"  Critical: {report.summary.get('critical_count', 0)}")
        print(f"  Errors:   {report.summary.get('error_count', 0)}")
        print(f"  Warnings: {report.summary.get('warning_count', 0)}")
        print(f"  Info:     {report.summary.get('info_count', 0)}")
        
        # Show category breakdown
        if "by_category" in report.summary:
            print("\nIssues by Category:")
            for category, count in sorted(report.summary["by_category"].items()):
                print(f"  • {category}: {count}")
        
        # Show issues
        print("\n" + "-" * 80)
        print("ISSUES")
        print("-" * 80)
        
        # Filter issues based on show_all flag
        if show_all:
            issues_to_show = report.issues
        else:
            issues_to_show = [
                i for i in report.issues 
                if i.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR, ValidationSeverity.WARNING]
            ]
        
        if not issues_to_show:
            print("\n✓ No issues found!" if show_all else "\n✓ No critical issues, errors, or warnings!")
        else:
            # Group by severity
            for severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR, 
                           ValidationSeverity.WARNING, ValidationSeverity.INFO]:
                severity_issues = [i for i in issues_to_show if i.severity == severity]
                
                if severity_issues:
                    print(f"\n{severity.value}S ({len(severity_issues)}):")
                    print("-" * 80)
                    
                    for issue in severity_issues:
                        print(f"\n  [{issue.category}] {issue.dataset_name}", end="")
                        if issue.column_name:
                            print(f".{issue.column_name}", end="")
                        print()
                        print(f"  {issue.description}")
                        
                        if issue.sample_values:
                            print(f"  Sample values: {issue.sample_values}")
                        
                        if issue.details:
                            for key, value in issue.details.items():
                                if key not in ['percentage', 'total_rows']:
                                    print(f"  {key}: {value}")
        
        print("\n" + "=" * 80)
        
        # Show dataset statistics
        if report.dataset_stats:
            print("\nDATASET STATISTICS")
            print("-" * 80)
            print(f"{'Dataset':<30} {'Rows':<10} {'Cols':<8} {'Missing':<10} {'Domain':<15}")
            print("-" * 80)
            
            for dataset_name, stats in sorted(report.dataset_stats.items()):
                print(
                    f"{dataset_name:<30} {stats['rows']:<10,} {stats['columns']:<8} "
                    f"{stats['missing_cells']:<10,} {stats['domain']:<15}"
                )
            
            print("=" * 80)
