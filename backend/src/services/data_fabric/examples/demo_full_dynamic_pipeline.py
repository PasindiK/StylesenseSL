"""
Complete dynamic data pipeline demonstration.

Shows the full workflow:
1. Load any CSV data
2. Auto-discover schema (column roles, types)
3. Auto-discover relationships (FKs)
4. Preprocess (normalize columns, dates, types)
5. Validate BEFORE cleaning
6. Clean (remove duplicates, orphans, nulls)
7. Validate AFTER cleaning
8. Export cleaned data

Works with ANY dataset - no hardcoding!
"""

import sys
import os
from pathlib import Path
import logging

# Set UTF-8 encoding for output
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.data_pipeline import DataPipeline


def main():
    """Run complete dynamic data pipeline."""
    
    print("\n" + "="*100)
    print("FULLY DYNAMIC DATA PIPELINE DEMONSTRATION")
    print("="*100)
    print("\nThis pipeline works with ANY CSV data - no hardcoding!")
    print("It automatically discovers schema, relationships, and applies cleaning.\n")
    
    # Use the raw data folder
    data_folder = r"c:\Users\Molex Technologies\OneDrive - Sri Lanka Institute of Information Technology\Research\Data Fabric\raw-data copy"
    output_folder = r"c:\Users\Molex Technologies\OneDrive - Sri Lanka Institute of Information Technology\Research\Data Fabric\data-fabric\processed-data"
    
    try:
        # ========== PHASE 1: INITIALIZATION ==========
        print("\n" + "-"*100)
        print("PHASE 1: INITIALIZING PIPELINE")
        print("-"*100)
        
        pipeline = DataPipeline(data_folder)
        print(f"[OK] Pipeline initialized for folder: {data_folder}\n")
        
        # ========== PHASE 2: LOAD DATA ==========
        print("-"*100)
        print("PHASE 2: LOADING DATA")
        print("-"*100)
        
        datasets = pipeline.load_all_datasets()
        print(f"[OK] Loaded {len(datasets)} datasets\n")
        
        # ========== PHASE 3: SCHEMA DISCOVERY ==========
        print("-"*100)
        print("PHASE 3: AUTO-DISCOVERING SCHEMA")
        print("-"*100)
        
        schemas = pipeline.discover_schema()
        print(f"[OK] Discovered schema for {len(schemas)} datasets\n")
        print(pipeline.print_schema_summary())
        
        # ========== PHASE 4: RELATIONSHIP DISCOVERY ==========
        print("-"*100)
        print("PHASE 4: AUTO-DISCOVERING RELATIONSHIPS")
        print("-"*100)
        
        relationships = pipeline.discover_relationships()
        print(f"[OK] Discovered {len(pipeline.foreign_keys)} foreign key relationships\n")
        print(pipeline.print_relationships_summary())
        
        # ========== PHASE 5: PREPROCESSING ==========
        print("-"*100)
        print("PHASE 5: PREPROCESSING DATA")
        print("-"*100)
        
        pipeline.preprocess_all(
            normalize_columns=True,
            normalize_dates=True,
            normalize_numeric=True
        )
        print(f"[OK] Preprocessed {len(pipeline.preprocessed_datasets)} datasets\n")
        print("  Actions applied:")
        print("  - Column names normalized to snake_case")
        print("  - Date columns normalized to ISO format")
        print("  - Numeric strings converted to numeric types\n")
        
        # ========== PHASE 6: VALIDATION BEFORE CLEANING ==========
        print("-"*100)
        print("PHASE 6: VALIDATION BEFORE CLEANING")
        print("-"*100)
        
        validation_before = pipeline.validate_before_cleaning()
        print(f"[OK] Validation complete. Found {len(validation_before.issues)} issues.\n")
        print(DynamicDataValidator.print_validation_report(validation_before))
        
        # ========== PHASE 7: CLEANING ==========
        print("-"*100)
        print("PHASE 7: CLEANING DATA")
        print("-"*100)
        
        pipeline.clean_all(drop_orphans=True, fill_missing=False)
        print(f"[OK] Cleaned {len(pipeline.cleaned_datasets)} datasets\n")
        print(pipeline.print_cleaning_summary())
        
        # ========== PHASE 8: VALIDATION AFTER CLEANING ==========
        print("-"*100)
        print("PHASE 8: VALIDATION AFTER CLEANING")
        print("-"*100)
        
        validation_after = pipeline.validate_after_cleaning()
        print(f"[OK] Validation complete. Found {len(validation_after.issues)} issues.\n")
        print(DynamicDataValidator.print_validation_report(validation_after))
        
        # ========== PHASE 9: COMPARISON ==========
        print("-"*100)
        print("PHASE 9: BEFORE vs AFTER COMPARISON")
        print("-"*100)
        
        before_count = len(validation_before.issues)
        after_count = len(validation_after.issues)
        improvement = before_count - after_count
        
        print(f"\nIssues before cleaning: {before_count}")
        print(f"Issues after cleaning:  {after_count}")
        print(f"Issues resolved:        {improvement} ({improvement/before_count*100:.1f}% reduction)\n")
        
        # ========== PHASE 10: EXPORT ==========
        print("-"*100)
        print("PHASE 10: EXPORTING CLEANED DATA")
        print("-"*100)
        
        exported = pipeline.export_cleaned_datasets(output_folder)
        print(f"[OK] Exported {len(exported)} cleaned datasets to: {output_folder}\n")
        for dataset_name, filepath in exported.items():
            rows = len(pipeline.cleaned_datasets[dataset_name])
            print(f"  - {dataset_name}_cleaned.csv ({rows} rows)")
        
        # ========== FINAL SUMMARY ==========
        print("\n" + "="*100)
        print("PIPELINE EXECUTION COMPLETE")
        print("="*100)
        print(pipeline.print_pipeline_summary())
        
        print("\n[SUCCESS] Data pipeline executed completely!")
        print(f"[OK] Cleaned data ready at: {output_folder}")
        print("[OK] You can now connect cleaned data to Power BI for analysis.\n")
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    # Import validator printer for use in main
    from src.ingestion.dynamic_validator import DynamicDataValidator
    
    exit(main())
