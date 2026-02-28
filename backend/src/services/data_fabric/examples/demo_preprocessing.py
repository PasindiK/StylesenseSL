"""Demo: Dynamic preprocessing in the ingestion layer.

This script demonstrates:
1. Automatic column name normalization (snake_case)
2. Date column detection and ISO format conversion
3. Numeric column detection and type conversion
4. In-memory transformations (no file writes)
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime
import tempfile
import shutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import AutoDataLoader, DataPreprocessor


def create_sample_data(temp_dir: Path):
    """Create sample CSV with mixed formatting to demonstrate preprocessing."""
    
    # Sample 1: Users with mixed column naming styles
    users_data = {
        "UserID": [1, 2, 3, 4, 5],
        "First Name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "Email-Address": ["alice@example.com", "bob@example.com", "charlie@example.com", 
                         "diana@example.com", "eve@example.com"],
        "DateOfBirth": ["1990-05-15", "1985-08-22", "1992-11-03", "1988-03-17", "1995-07-29"],
        "RegistrationDate": ["2023-01-15", "2023-02-20", "2023-03-10", "2023-04-05", "2023-05-18"],
        "AccountBalance": ["1500.50", "2300.75", "150.00", "4500.25", "890.99"],
        "Age": ["33", "38", "31", "35", "28"],
    }
    users_df = pd.DataFrame(users_data)
    users_df.to_csv(temp_dir / "users_sample.csv", index=False)
    
    # Sample 2: Products with various column styles
    products_data = {
        "ProductID": [101, 102, 103, 104, 105],
        "Product Name": ["Laptop", "Mouse", "Keyboard", "Monitor", "Headphones"],
        "PriceUSD": ["999.99", "25.50", "75.00", "350.00", "120.50"],
        "StockQuantity": ["15", "150", "80", "25", "60"],
        "Category-Name": ["Electronics", "Accessories", "Accessories", "Electronics", "Accessories"],
        "LastUpdated": ["2024-01-15 10:30:00", "2024-01-20 14:45:00", "2024-01-18 09:15:00",
                       "2024-01-22 16:20:00", "2024-01-25 11:00:00"],
    }
    products_df = pd.DataFrame(products_data)
    products_df.to_csv(temp_dir / "products_sample.csv", index=False)
    
    # Sample 3: Transactions with date variations
    transactions_data = {
        "TransactionID": ["TRX001", "TRX002", "TRX003", "TRX004", "TRX005"],
        "User-ID": ["1", "2", "3", "1", "4"],
        "Product ID": ["101", "102", "103", "104", "105"],
        "Transaction Amount": ["999.99", "25.50", "75.00", "350.00", "120.50"],
        "TransactionDate": ["01/15/2024", "01/20/2024", "01/18/2024", "01/22/2024", "01/25/2024"],
        "QuantityPurchased": ["1", "3", "2", "1", "2"],
    }
    transactions_df = pd.DataFrame(transactions_data)
    transactions_df.to_csv(temp_dir / "transactions_sample.csv", index=False)
    
    print(f"✓ Created 3 sample CSV files in {temp_dir}")


def demo_preprocessing():
    """Demonstrate preprocessing capabilities."""
    
    print("\n" + "=" * 80)
    print("DYNAMIC PREPROCESSING DEMO")
    print("=" * 80)
    
    # Create temporary directory for sample data
    temp_dir = Path(tempfile.mkdtemp(prefix="preprocessing_demo_"))
    
    try:
        # Step 1: Create sample data
        print("\n1. Creating Sample Data")
        print("-" * 80)
        create_sample_data(temp_dir)
        
        # Step 2: Load WITHOUT preprocessing
        print("\n2. Loading Data WITHOUT Preprocessing")
        print("-" * 80)
        loader_raw = AutoDataLoader(str(temp_dir))
        registry_raw = loader_raw.load_all_datasets(enable_preprocessing=False)
        
        print("\nRaw column names (no preprocessing):")
        for dataset_name in sorted(registry_raw.list_datasets()):
            df = registry_raw.get_dataset(dataset_name)
            metadata = registry_raw.get_metadata(dataset_name)
            print(f"\n  {dataset_name} ({metadata.detected_domain}):")
            print(f"    Columns: {df.columns.tolist()}")
            print(f"    Dtypes: {df.dtypes.to_dict()}")
        
        # Step 3: Load WITH preprocessing
        print("\n3. Loading Data WITH Preprocessing (snake_case + dates + numeric)")
        print("-" * 80)
        loader_processed = AutoDataLoader(str(temp_dir))
        registry_processed = loader_processed.load_all_datasets(
            enable_preprocessing=True,
            normalize_columns=True,
            normalize_dates=True,
            normalize_numeric=True
        )
        
        print("\nProcessed column names (with preprocessing):")
        for dataset_name in sorted(registry_processed.list_datasets()):
            df = registry_processed.get_dataset(dataset_name)
            metadata = registry_processed.get_metadata(dataset_name)
            print(f"\n  {dataset_name} ({metadata.detected_domain}):")
            print(f"    Columns: {df.columns.tolist()}")
            print(f"    Dtypes: {df.dtypes.to_dict()}")
        
        # Step 4: Detailed comparison
        print("\n4. Detailed Comparison: Before vs After")
        print("-" * 80)
        
        for dataset_name in sorted(registry_raw.list_datasets()):
            df_raw = registry_raw.get_dataset(dataset_name)
            df_processed = registry_processed.get_dataset(dataset_name)
            
            print(f"\n  Dataset: {dataset_name}")
            print(f"  {'Before':<30} {'After':<30} {'Change':<20}")
            print(f"  {'-'*30} {'-'*30} {'-'*20}")
            
            for col_raw, col_processed in zip(df_raw.columns, df_processed.columns):
                change = "✓ Normalized" if col_raw != col_processed else "No change"
                print(f"  {col_raw:<30} {col_processed:<30} {change:<20}")
                
                # Show type changes
                type_raw = str(df_raw[col_raw].dtype)
                type_processed = str(df_processed[col_processed].dtype)
                if type_raw != type_processed:
                    print(f"    └─ Type: {type_raw} → {type_processed}")
        
        # Step 5: Show sample data transformations
        print("\n5. Sample Data Transformations")
        print("-" * 80)
        
        # Users dataset
        if "users_sample" in registry_processed.list_datasets():
            df_raw = registry_raw.get_dataset("users_sample")
            df_processed = registry_processed.get_dataset("users_sample")
            
            print("\n  Users Dataset - First 2 rows:")
            print("\n  BEFORE preprocessing:")
            print(df_raw.head(2).to_string())
            print("\n  AFTER preprocessing:")
            print(df_processed.head(2).to_string())
        
        # Step 6: Test standalone preprocessing
        print("\n6. Standalone Preprocessing Usage")
        print("-" * 80)
        
        test_data = {
            "User ID": [1, 2, 3],
            "First-Name": ["Alice", "Bob", "Charlie"],
            "Registration Date": ["2024-01-15", "2024-02-20", "2024-03-10"],
            "Account Balance": ["1500.50", "2300.75", "150.00"],
        }
        test_df = pd.DataFrame(test_data)
        
        print("\n  Original DataFrame:")
        print(f"  Columns: {test_df.columns.tolist()}")
        print(f"  Dtypes: {test_df.dtypes.to_dict()}")
        
        # Apply preprocessing
        processed_df = DataPreprocessor.preprocess(test_df)
        
        print("\n  After DataPreprocessor.preprocess():")
        print(f"  Columns: {processed_df.columns.tolist()}")
        print(f"  Dtypes: {processed_df.dtypes.to_dict()}")
        
        # Step 7: Test individual transformations
        print("\n7. Individual Transformation Examples")
        print("-" * 80)
        
        # Column name examples
        examples = [
            "UserID",
            "First Name",
            "Email-Address",
            "DateOfBirth",
            "product_name",
            "CamelCaseColumn",
            "snake_case_column",
        ]
        
        print("\n  Column Name Normalization:")
        for name in examples:
            normalized = DataPreprocessor.to_snake_case(name)
            print(f"    {name:<25} → {normalized}")
        
        # Step 8: Summary
        print("\n8. Preprocessing Summary")
        print("-" * 80)
        
        total_datasets = len(registry_processed.list_datasets())
        print(f"\n  ✓ Processed {total_datasets} datasets")
        print(f"  ✓ All column names normalized to snake_case")
        print(f"  ✓ Date columns converted to ISO format")
        print(f"  ✓ Numeric columns converted to proper types")
        print(f"  ✓ All transformations applied IN-MEMORY (no files written)")
        
        # Show inventory
        print("\n9. Final Inventory")
        print("-" * 80)
        loader_processed.print_inventory()
        
    finally:
        # Cleanup temporary directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"\n✓ Cleaned up temporary directory: {temp_dir}")
    
    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


def demo_preprocessing_options():
    """Demonstrate selective preprocessing options."""
    
    print("\n" + "=" * 80)
    print("SELECTIVE PREPROCESSING OPTIONS DEMO")
    print("=" * 80)
    
    temp_dir = Path(tempfile.mkdtemp(prefix="preprocessing_options_"))
    
    try:
        create_sample_data(temp_dir)
        
        # Test 1: Only column normalization
        print("\n1. Only Column Normalization (dates & numeric disabled)")
        print("-" * 80)
        loader = AutoDataLoader(str(temp_dir))
        registry = loader.load_all_datasets(
            enable_preprocessing=True,
            normalize_columns=True,
            normalize_dates=False,
            normalize_numeric=False
        )
        
        df = registry.get_dataset("users_sample")
        print(f"  Columns: {df.columns.tolist()}")
        print(f"  Dtypes (should be mostly object): {df.dtypes.to_dict()}")
        
        # Test 2: Only date normalization
        print("\n2. Only Date Normalization (columns & numeric disabled)")
        print("-" * 80)
        loader = AutoDataLoader(str(temp_dir))
        registry = loader.load_all_datasets(
            enable_preprocessing=True,
            normalize_columns=False,
            normalize_dates=True,
            normalize_numeric=False
        )
        
        df = registry.get_dataset("users_sample")
        print(f"  Original column names preserved: {df.columns.tolist()}")
        if "DateOfBirth" in df.columns:
            print(f"  DateOfBirth sample: {df['DateOfBirth'].head(2).tolist()}")
        
        # Test 3: Only numeric normalization
        print("\n3. Only Numeric Normalization (columns & dates disabled)")
        print("-" * 80)
        loader = AutoDataLoader(str(temp_dir))
        registry = loader.load_all_datasets(
            enable_preprocessing=True,
            normalize_columns=False,
            normalize_dates=False,
            normalize_numeric=True
        )
        
        df = registry.get_dataset("users_sample")
        print(f"  Original column names preserved: {df.columns.tolist()}")
        print(f"  Numeric types applied: {df.dtypes.to_dict()}")
        
        # Test 4: No preprocessing
        print("\n4. No Preprocessing (all disabled)")
        print("-" * 80)
        loader = AutoDataLoader(str(temp_dir))
        registry = loader.load_all_datasets(enable_preprocessing=False)
        
        df = registry.get_dataset("users_sample")
        print(f"  Raw columns: {df.columns.tolist()}")
        print(f"  Raw dtypes: {df.dtypes.to_dict()}")
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    print("\n🚀 Starting Preprocessing Demonstrations...\n")
    
    # Main demo
    demo_preprocessing()
    
    # Options demo
    demo_preprocessing_options()
    
    print("\n✨ All demonstrations completed successfully!")
