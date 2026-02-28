"""
Dynamic data validation module.

Validates datasets based on discovered schema. Works with any dataset
without hardcoding column names or relationships.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging


class ValidationSeverity(Enum):
    """Severity level of validation issues."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class IssueCategory(Enum):
    """Category of validation issues."""
    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    MISSING_VALUE = "missing_value"
    ANOMALY = "anomaly"
    TYPE_MISMATCH = "type_mismatch"


@dataclass
class ValidationIssue:
    """A single validation issue found in the data."""
    dataset: str
    column: str
    issue_type: IssueCategory
    severity: ValidationSeverity
    count: int
    message: str
    affected_rows: Optional[List[int]] = None


@dataclass
class ValidationReport:
    """Complete validation report for a dataset or collection of datasets."""
    issues: List[ValidationIssue]
    dataset_summaries: Dict[str, Dict]  # Summary stats per dataset
    
    def to_dict(self) -> Dict:
        """Convert report to dictionary format."""
        issue_counts = {}
        for issue in self.issues:
            key = f"{issue.issue_type.value}_{issue.severity.value}"
            issue_counts[key] = issue_counts.get(key, 0) + issue.count
        
        return {
            "total_issues": len(self.issues),
            "total_problematic_rows": sum(i.count for i in self.issues),
            "issue_breakdown": issue_counts,
            "dataset_count": len(self.dataset_summaries),
            "issues": [
                {
                    "dataset": i.dataset,
                    "column": i.column,
                    "issue_type": i.issue_type.value,
                    "severity": i.severity.value,
                    "count": i.count,
                    "message": i.message
                }
                for i in self.issues
            ]
        }


class DynamicDataValidator:
    """
    Validate any dataset based on discovered schema.
    
    Checks:
    - Primary key integrity (nulls, duplicates)
    - Foreign key relationships (orphans, type mismatches)
    - Missing values in critical columns
    - Numeric anomalies (negative prices, outliers)
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_all_datasets(
        self,
        datasets: Dict[str, pd.DataFrame],
        primary_keys: Dict[str, List[str]],
        foreign_keys: List[Tuple[str, str, str, str]],
        numeric_anomalies: Optional[Dict[str, List[str]]] = None,
        critical_nullable: Optional[List[str]] = None
    ) -> ValidationReport:
        """
        Validate all datasets based on discovered schema.
        
        Args:
            datasets: Dict of {dataset_name: DataFrame}
            primary_keys: Dict of {dataset_name: [pk_columns]}
            foreign_keys: List of (child_dataset, child_col, parent_dataset, parent_col)
            numeric_anomalies: Dict of {dataset.column: ['negative', 'outliers']}
            critical_nullable: List of {dataset.column} that should not be null
            
        Returns:
            ValidationReport with all issues found
        """
        issues = []
        dataset_summaries = {}
        
        # Validate each dataset
        for dataset_name, df in datasets.items():
            dataset_issues = []
            
            # Check primary keys
            if dataset_name in primary_keys:
                pk_issues = self._validate_primary_keys(df, dataset_name, primary_keys[dataset_name])
                dataset_issues.extend(pk_issues)
            
            # Check missing values
            missing_issues = self._validate_missing_values(df, dataset_name, critical_nullable)
            dataset_issues.extend(missing_issues)
            
            # Check numeric anomalies
            anomaly_issues = self._validate_numeric_anomalies(df, dataset_name, numeric_anomalies)
            dataset_issues.extend(anomaly_issues)
            
            issues.extend(dataset_issues)
            
            # Generate summary
            dataset_summaries[dataset_name] = {
                "rows": len(df),
                "columns": len(df.columns),
                "issues_count": len(dataset_issues),
                "critical_issues": sum(1 for i in dataset_issues if i.severity == ValidationSeverity.CRITICAL),
                "error_issues": sum(1 for i in dataset_issues if i.severity == ValidationSeverity.ERROR)
            }
        
        # Validate foreign keys
        fk_issues = self._validate_foreign_keys(datasets, foreign_keys)
        issues.extend(fk_issues)
        
        return ValidationReport(issues=issues, dataset_summaries=dataset_summaries)
    
    def _validate_primary_keys(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        pk_columns: List[str]
    ) -> List[ValidationIssue]:
        """Check primary key integrity."""
        issues = []
        
        # Check for nulls
        null_mask = df[pk_columns].isnull().any(axis=1)
        null_count = null_mask.sum()
        if null_count > 0:
            issues.append(ValidationIssue(
                dataset=dataset_name,
                column=",".join(pk_columns),
                issue_type=IssueCategory.PRIMARY_KEY,
                severity=ValidationSeverity.CRITICAL,
                count=int(null_count),
                message=f"Primary key has {null_count} null values",
                affected_rows=df[null_mask].index.tolist()[:10]  # First 10
            ))
        
        # Check for duplicates
        duplicate_mask = df.duplicated(subset=pk_columns, keep=False)
        duplicate_count = duplicate_mask.sum()
        if duplicate_count > 0:
            issues.append(ValidationIssue(
                dataset=dataset_name,
                column=",".join(pk_columns),
                issue_type=IssueCategory.PRIMARY_KEY,
                severity=ValidationSeverity.CRITICAL,
                count=int(duplicate_count),
                message=f"Primary key has {duplicate_count} duplicate values",
                affected_rows=df[duplicate_mask].index.tolist()[:10]  # First 10
            ))
        
        return issues
    
    def _validate_foreign_keys(
        self,
        datasets: Dict[str, pd.DataFrame],
        foreign_keys: List[Tuple[str, str, str, str]]
    ) -> List[ValidationIssue]:
        """Check foreign key relationships."""
        issues = []
        
        for child_dataset, child_col, parent_dataset, parent_col in foreign_keys:
            if child_dataset not in datasets or parent_dataset not in datasets:
                continue
            
            child_df = datasets[child_dataset]
            parent_df = datasets[parent_dataset]
            
            if child_col not in child_df.columns or parent_col not in parent_df.columns:
                continue
            
            # Get valid parent values
            valid_parent_values = set(parent_df[parent_col].dropna().unique())
            
            # Find orphaned child values
            orphan_mask = ~(child_df[child_col].isin(valid_parent_values)) & child_df[child_col].notna()
            orphan_count = orphan_mask.sum()
            
            if orphan_count > 0:
                issues.append(ValidationIssue(
                    dataset=child_dataset,
                    column=child_col,
                    issue_type=IssueCategory.FOREIGN_KEY,
                    severity=ValidationSeverity.ERROR,
                    count=int(orphan_count),
                    message=f"Foreign key {child_col} has {orphan_count} orphaned values "
                           f"(not found in {parent_dataset}.{parent_col})",
                    affected_rows=child_df[orphan_mask].index.tolist()[:10]  # First 10
                ))
        
        return issues
    
    def _validate_missing_values(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        critical_nullable: Optional[List[str]] = None
    ) -> List[ValidationIssue]:
        """Check for missing values in critical columns."""
        issues = []
        critical_nullable = critical_nullable or []
        
        for col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count == 0:
                continue
            
            # Determine severity
            if f"{dataset_name}.{col}" in critical_nullable:
                severity = ValidationSeverity.ERROR
            else:
                severity = ValidationSeverity.WARNING
            
            issues.append(ValidationIssue(
                dataset=dataset_name,
                column=col,
                issue_type=IssueCategory.MISSING_VALUE,
                severity=severity,
                count=int(null_count),
                message=f"Column {col} has {null_count} missing values ({null_count/len(df)*100:.1f}%)",
                affected_rows=df[df[col].isnull()].index.tolist()[:10]  # First 10
            ))
        
        return issues
    
    def _validate_numeric_anomalies(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        numeric_anomalies: Optional[Dict[str, List[str]]] = None
    ) -> List[ValidationIssue]:
        """Check for anomalies in numeric columns."""
        issues = []
        numeric_anomalies = numeric_anomalies or {}
        
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue
            
            anomaly_types = numeric_anomalies.get(f"{dataset_name}.{col}", [])
            if not anomaly_types:
                continue
            
            if 'negative' in anomaly_types:
                negative_mask = df[col] < 0
                negative_count = negative_mask.sum()
                if negative_count > 0:
                    issues.append(ValidationIssue(
                        dataset=dataset_name,
                        column=col,
                        issue_type=IssueCategory.ANOMALY,
                        severity=ValidationSeverity.WARNING,
                        count=int(negative_count),
                        message=f"Column {col} has {negative_count} negative values",
                        affected_rows=df[negative_mask].index.tolist()[:10]  # First 10
                    ))
            
            if 'outliers' in anomaly_types:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                outlier_mask = (df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)
                outlier_count = outlier_mask.sum()
                if outlier_count > 0:
                    issues.append(ValidationIssue(
                        dataset=dataset_name,
                        column=col,
                        issue_type=IssueCategory.ANOMALY,
                        severity=ValidationSeverity.INFO,
                        count=int(outlier_count),
                        message=f"Column {col} has {outlier_count} potential outliers",
                        affected_rows=df[outlier_mask].index.tolist()[:10]  # First 10
                    ))
        
        return issues
    
    @staticmethod
    def print_validation_report(report: ValidationReport) -> str:
        """Generate human-readable validation report."""
        output = [
            f"\n{'='*100}",
            f"VALIDATION REPORT",
            f"{'='*100}",
            f"Datasets validated: {len(report.dataset_summaries)}",
            f"Total issues found: {len(report.issues)}",
            f"",
            f"DATASET SUMMARY:",
            f"{'-'*100}",
        ]
        
        for dataset_name, summary in report.dataset_summaries.items():
            output.append(
                f"{dataset_name:<40} Rows: {summary['rows']:>8} | "
                f"Issues: {summary['issues_count']:>3} | "
                f"Critical: {summary['critical_issues']:>2} | Error: {summary['error_issues']:>2}"
            )
        
        if report.issues:
            output.extend([
                f"",
                f"ISSUES DETAILED:",
                f"{'-'*100}",
            ])
            
            # Group by severity
            for severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR, 
                           ValidationSeverity.WARNING, ValidationSeverity.INFO]:
                severity_issues = [i for i in report.issues if i.severity == severity]
                if severity_issues:
                    output.append(f"\n{severity.value} ({len(severity_issues)}):")
                    for issue in severity_issues:
                        output.append(
                            f"  • {issue.dataset}.{issue.column} ({issue.issue_type.value}): "
                            f"{issue.message}"
                        )
        
        output.append(f"{'='*100}\n")
        return "\n".join(output)
