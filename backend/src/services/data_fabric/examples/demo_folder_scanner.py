#!/usr/bin/env python3
"""Example script demonstrating AutoDataLoader usage with your raw data.

This script shows how to:
1. Initialize the AutoDataLoader with your raw_data folder
2. Automatically scan and load all CSV files
3. Access datasets and their metadata
4. Query datasets by domain
5. Generate inventory reports
"""

import sys
from pathlib import Path

# Add the project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import AutoDataLoader


def main():
    """Demonstrate AutoDataLoader functionality."""
    
    # Path to raw_data folder (one level above data-fabric project)
    raw_data_path = Path(__file__).parent.parent.parent / "raw-data copy" 
    
    if not raw_data_path.exists():
        print(f"Error: Raw data folder not found at {raw_data_path}")
        print("Please check the path and ensure raw data files exist.")
        return
    
    print(f"\nStarting data ingestion from: {raw_data_path}")
    print("=" * 80)
    
    # Initialize AutoDataLoader
    loader = AutoDataLoader(str(raw_data_path))
    
    # Load all CSV files automatically
    print("\n📂 Scanning folder for CSV files...")
    registry = loader.load_all_datasets(recursive=False)
    
    # Print inventory summary
    print("\n📊 Generated Inventory Summary:")
    loader.print_inventory()
    
    # Get detailed statistics
    stats = registry.get_statistics()
    print("\n📈 Detailed Statistics:")
    print(f"   • Total datasets loaded: {stats['total_datasets']}")
    print(f"   • Total rows in all datasets: {stats['total_rows']:,}")
    print(f"   • Total storage size: {stats['total_size_mb']:.2f} MB")
    
    # Show datasets by domain
    print("\n🏷️  Datasets by Domain:")
    for domain, count in sorted(stats['datasets_by_domain'].items()):
        datasets = registry.get_datasets_by_domain(domain)
        print(f"\n   {domain.upper()} ({count} dataset(s)):")
        for dataset_name in sorted(datasets.keys()):
            metadata = registry.get_metadata(dataset_name)
            print(
                f"      • {dataset_name}: {metadata.row_count:,} rows, "
                f"{metadata.column_count} columns"
            )
    
    # Example: Access specific datasets
    print("\n" + "=" * 80)
    print("\n🔍 Example: Accessing Datasets Programmatically")
    
    for dataset_name in registry.list_datasets()[:2]:  # Show first 2
        df = registry.get_dataset(dataset_name)
        metadata = registry.get_metadata(dataset_name)
        
        print(f"\n📋 Dataset: {dataset_name}")
        print(f"   Domain: {metadata.detected_domain}")
        print(f"   Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        print(f"   Columns: {', '.join(df.columns.tolist())}")
        print(f"   Memory size: {metadata.file_size_mb:.2f} MB")
        
        # Show missing values
        if metadata.missing_values:
            missing = {k: v for k, v in metadata.missing_values.items() if v > 0}
            if missing:
                print(f"   Missing values: {missing}")
        
        # Show preview
        print(f"\n   Preview (first 3 rows):")
        preview = df.head(3).to_string(index=False).replace("\n", "\n   ")
        print(f"   {preview}")
    
    # Example: Query datasets by domain
    print("\n" + "=" * 80)
    print("\n🎯 Example: Query Datasets by Domain")
    
    # Get all transaction datasets if any exist
    transaction_datasets = registry.get_datasets_by_domain("transactions")
    if transaction_datasets:
        print(f"\nFound {len(transaction_datasets)} transaction dataset(s):")
        for name, df in transaction_datasets.items():
            print(f"   • {name}: {len(df):,} transactions")
    
    # Get all user datasets if any exist
    user_datasets = registry.get_datasets_by_domain("users")
    if user_datasets:
        print(f"Found {len(user_datasets)} user dataset(s):")
        for name, df in user_datasets.items():
            print(f"   • {name}: {len(df):,} users")
    
    print("\n" + "=" * 80)
    print("\n✅ Data ingestion complete! All datasets are now available in memory.")
    print("\n💡 Next steps:")
    print("   1. Use registry.get_dataset(name) to access specific datasets")
    print("   2. Use registry.get_datasets_by_domain(domain) to filter by domain")
    print("   3. Access metadata with registry.get_metadata(name)")
    print("   4. Pass registry to preprocessing or validation modules")


if __name__ == "__main__":
    main()
