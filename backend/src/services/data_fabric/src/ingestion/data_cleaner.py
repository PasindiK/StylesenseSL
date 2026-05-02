"""
Dynamic data cleaning module.

Auto-cleans datasets based on discovered schema:
- Removes null primary keys
- Removes duplicate primary keys
- Removes foreign key orphans
- Handles missing values in critical columns

Works on any dataset without hardcoding.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum


class CleaningAction(Enum):
    """Types of cleaning actions performed."""
    DROPPED_NULL_PK = "dropped_null_pk"
    DROPPED_DUPLICATE_PK = "dropped_duplicate_pk"
    REGENERATED_PK = "regenerated_pk"
    REMOVED_FK_ORPHAN = "removed_fk_orphan"
    FILLED_MISSING_VALUE = "filled_missing_value"


@dataclass
class CleaningReport:
    """Report of cleaning actions taken on a dataset."""
    dataset_name: str
    initial_rows: int
    final_rows: int
    rows_removed: int
    actions: List[CleaningAction]
    action_counts: Dict[str, int]
    details: List[str]
    
    def summary(self) -> str:
        """Generate summary of cleaning report."""
        summary = [
            f"\n{self.dataset_name}:",
            f"  Rows: {self.initial_rows} -> {self.final_rows} (removed {self.rows_removed})",
        ]
        for action, count in self.action_counts.items():
            if count > 0:
                summary.append(f"  - {action}: {count}")
        return "\n".join(summary)


class DataCleaner:
    """
    Auto-clean datasets based on discovered schema.
    
    Cleans in the following order:
    1. Remove null primary keys (can't identify records)
    2. Remove duplicate primary keys (keep first occurrence)
    3. Remove foreign key orphans (child without parent)
    4. Fill missing values in non-critical columns
    """
    
    def __init__(self):
        self.cleaning_reports: Dict[str, CleaningReport] = {}
    
    def clean_datasets(
        self,
        datasets: Dict[str, pd.DataFrame],
        primary_keys: Dict[str, List[str]],
        foreign_keys: List[Tuple[str, str, str, str]],
        pk_strategy: str = "drop",
        drop_orphans: bool = True,
        fill_missing: bool = False
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, CleaningReport]]:
        """
        Clean all datasets based on schema.
        
        Args:
            datasets: Dict of {dataset_name: DataFrame}
            primary_keys: Dict of {dataset_name: [pk_columns]}
            foreign_keys: List of (child_dataset, child_col, parent_dataset, parent_col)
            pk_strategy: "drop" (remove invalid PK rows) or "regenerate" (single-PK only)
            drop_orphans: Whether to remove FK orphans
            fill_missing: Whether to fill missing values
            
        Returns:
            (cleaned_datasets, cleaning_reports)
        """
        self.cleaning_reports = {}
        cleaned_datasets = {}
        
        # Step 1: Clean primary keys (nulls and duplicates)
        for dataset_name, df in datasets.items():
            pk_cols = primary_keys.get(dataset_name, [])
            if pk_cols:
                if pk_strategy == "regenerate":
                    df = self._regenerate_primary_keys(df, dataset_name, pk_cols)
                else:
                    df = self._clean_primary_keys(df, dataset_name, pk_cols)
            cleaned_datasets[dataset_name] = df
        
        # Step 2: Remove foreign key orphans
        if drop_orphans:
            for child_dataset, child_col, parent_dataset, parent_col in foreign_keys:
                if child_dataset in cleaned_datasets and parent_dataset in cleaned_datasets:
                    child_df = cleaned_datasets[child_dataset]
                    parent_df = cleaned_datasets[parent_dataset]
                    child_df = self._remove_fk_orphans(
                        child_df, child_dataset, child_col,
                        parent_df, parent_col
                    )
                    cleaned_datasets[child_dataset] = child_df
        
        # Step 3: Optional - fill missing values
        if fill_missing:
            for dataset_name, df in cleaned_datasets.items():
                df = self._fill_missing_values(df, dataset_name)
                cleaned_datasets[dataset_name] = df
        
        return cleaned_datasets, self.cleaning_reports

    def _regenerate_primary_keys(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        pk_columns: List[str],
    ) -> pd.DataFrame:
        """Regenerate primary key values for single-column PK datasets.

        This keeps all rows and assigns a deterministic 1..N sequence.
        """
        if len(pk_columns) != 1:
            return self._clean_primary_keys(df, dataset_name, pk_columns)

        pk_col = pk_columns[0]
        if pk_col not in df.columns:
            return df

        initial_rows = len(df)
        regenerated_count = int(
            df[pk_col].isna().sum()
            + df[pk_col].dropna().duplicated(keep='first').sum()
        )

        if initial_rows == 0 or regenerated_count == 0:
            return df

        df = df.copy()
        df[pk_col] = pd.Series(range(1, initial_rows + 1), index=df.index, dtype="Int64")

        self.cleaning_reports[dataset_name] = CleaningReport(
            dataset_name=dataset_name,
            initial_rows=initial_rows,
            final_rows=initial_rows,
            rows_removed=0,
            actions=[],
            action_counts={CleaningAction.REGENERATED_PK.value: regenerated_count},
            details=[
                f"Regenerated primary key column '{pk_col}' for {initial_rows} rows"
            ],
        )
        return df
    
    def _clean_primary_keys(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        pk_columns: List[str]
    ) -> pd.DataFrame:
        """Remove null and duplicate primary keys."""
        initial_rows = len(df)
        action_counts = {}
        details = []
        
        # Remove null primary keys
        null_mask = df[pk_columns].isnull().any(axis=1)
        null_count = null_mask.sum()
        if null_count > 0:
            df = df[~null_mask]
            action_counts[CleaningAction.DROPPED_NULL_PK.value] = null_count
            details.append(f"Dropped {null_count} rows with null primary keys")
        
        # Remove duplicate primary keys (keep first)
        duplicate_mask = df.duplicated(subset=pk_columns, keep='first')
        duplicate_count = duplicate_mask.sum()
        if duplicate_count > 0:
            df = df[~duplicate_mask]
            action_counts[CleaningAction.DROPPED_DUPLICATE_PK.value] = duplicate_count
            details.append(f"Dropped {duplicate_count} rows with duplicate primary keys (kept first occurrence)")
        
        # Record cleaning action
        final_rows = len(df)
        rows_removed = initial_rows - final_rows
        
        if rows_removed > 0:
            self.cleaning_reports[dataset_name] = CleaningReport(
                dataset_name=dataset_name,
                initial_rows=initial_rows,
                final_rows=final_rows,
                rows_removed=rows_removed,
                actions=[],
                action_counts=action_counts,
                details=details
            )
        
        return df
    
    def _remove_fk_orphans(
        self,
        child_df: pd.DataFrame,
        child_dataset: str,
        child_col: str,
        parent_df: pd.DataFrame,
        parent_col: str
    ) -> pd.DataFrame:
        """Remove rows from child that don't have matching parent."""
        initial_rows = len(child_df)
        
        # Get valid parent values (non-null)
        valid_parent_values = set(parent_df[parent_col].dropna().unique())
        
        # Find orphaned rows (child values not in parent)
        if child_col in child_df.columns:
            orphan_mask = ~(child_df[child_col].isin(valid_parent_values)) & child_df[child_col].notna()
            orphan_count = orphan_mask.sum()
            
            if orphan_count > 0:
                child_df = child_df[~orphan_mask]
                final_rows = len(child_df)
                
                # Update or create report
                if child_dataset not in self.cleaning_reports:
                    self.cleaning_reports[child_dataset] = CleaningReport(
                        dataset_name=child_dataset,
                        initial_rows=initial_rows,
                        final_rows=final_rows,
                        rows_removed=initial_rows - final_rows,
                        actions=[],
                        action_counts={CleaningAction.REMOVED_FK_ORPHAN.value: orphan_count},
                        details=[f"Removed {orphan_count} orphaned rows (FK {child_col})"]
                    )
                else:
                    report = self.cleaning_reports[child_dataset]
                    report.final_rows = final_rows
                    report.rows_removed = initial_rows - final_rows
                    if CleaningAction.REMOVED_FK_ORPHAN.value not in report.action_counts:
                        report.action_counts[CleaningAction.REMOVED_FK_ORPHAN.value] = 0
                    report.action_counts[CleaningAction.REMOVED_FK_ORPHAN.value] += orphan_count
                    report.details.append(f"Removed {orphan_count} orphaned rows (FK {child_col})")
        
        return child_df
    
    def _fill_missing_values(
        self,
        df: pd.DataFrame,
        dataset_name: str
    ) -> pd.DataFrame:
        """Fill missing values using appropriate strategies."""
        action_counts = {}
        details = []
        
        for col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count == 0:
                continue
            
            # Strategy: fill numeric with median, categorical with mode
            if pd.api.types.is_numeric_dtype(df[col]):
                fill_value = df[col].median()
                df[col].fillna(fill_value, inplace=True)
                action_counts[CleaningAction.FILLED_MISSING_VALUE.value] = \
                    action_counts.get(CleaningAction.FILLED_MISSING_VALUE.value, 0) + null_count
                details.append(f"Filled {null_count} missing values in {col} with median: {fill_value}")
            elif df[col].dtype == 'object':
                fill_value = df[col].mode()[0] if len(df[col].mode()) > 0 else 'Unknown'
                df[col].fillna(fill_value, inplace=True)
                action_counts[CleaningAction.FILLED_MISSING_VALUE.value] = \
                    action_counts.get(CleaningAction.FILLED_MISSING_VALUE.value, 0) + null_count
                details.append(f"Filled {null_count} missing values in {col} with mode: {fill_value}")
        
        if details:
            self.cleaning_reports[dataset_name] = CleaningReport(
                dataset_name=dataset_name,
                initial_rows=len(df),
                final_rows=len(df),
                rows_removed=0,
                actions=[],
                action_counts=action_counts,
                details=details
            )
        
        return df
    
    def print_cleaning_summary(self) -> str:
        """Generate summary of all cleaning reports."""
        if not self.cleaning_reports:
            return "No cleaning reports generated."
        
        summary = [
            f"\n{'='*80}",
            f"DATA CLEANING SUMMARY",
            f"{'='*80}",
        ]
        
        total_rows_removed = 0
        for report in self.cleaning_reports.values():
            summary.append(report.summary())
            total_rows_removed += report.rows_removed
        
        summary.extend([
            f"\nTOTAL ROWS REMOVED: {total_rows_removed}",
            f"{'='*80}\n"
        ])
        
        return "\n".join(summary)
