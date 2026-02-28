#!/usr/bin/env python3
"""Demonstration of multi-format data loading (CSV, Excel, JSON, Parquet, TSV).

This script shows:
1. Support for 5+ file formats
2. Automatic format detection
3. Unified DataFrame loading
4. File type tracking in metadata
"""

import sys
from pathlib import Path
import pandas as pd
import tempfile
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import AutoDataLoader, FolderScanner


def create_sample_data_files(temp_dir: str):
    """Create sample data files in multiple formats."""
    
    # Sample dataset
    users_data = pd.DataFrame({
        "user_id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "email": ["alice@test.com", "bob@test.com", "charlie@test.com", "diana@test.com", "eve@test.com"],
        "age": [25, 30, 35, 28, 32]
    })
    
    products_data = pd.DataFrame({
        "product_id": [101, 102, 103, 104],
        "name": ["Widget", "Gadget", "Tool", "Device"],
        "price": [19.99, 29.99, 39.99, 49.99],
        "category": ["A", "B", "A", "C"]
    })
    
    transactions_data = pd.DataFrame({
        "transaction_id": [1001, 1002, 1003],
        "user_id": [1, 2, 3],
        "product_id": [101, 102, 103],
        "amount": [19.99, 29.99, 39.99],
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"]
    })
    
    print("Creating sample data files in multiple formats...")
    
    # Create files in different formats
    files_created = []
    
    # 1. CSV format
    csv_path = os.path.join(temp_dir, "users_data.csv")
    users_data.to_csv(csv_path, index=False)
    files_created.append(("users_data.csv", "csv", len(users_data)))
    print(f"  ✓ Created: users_data.csv")
    
    # 2. Excel format (.xlsx)
    try:
        xlsx_path = os.path.join(temp_dir, "products_catalog.xlsx")
        products_data.to_excel(xlsx_path, index=False, engine="openpyxl")
        files_created.append(("products_catalog.xlsx", "excel", len(products_data)))
        print(f"  ✓ Created: products_catalog.xlsx")
    except ImportError:
        print(f"  ⚠ Skipped: products_catalog.xlsx (openpyxl not installed)")
    
    # 3. JSON format
    json_path = os.path.join(temp_dir, "transactions_log.json")
    transactions_data.to_json(json_path, orient="records", indent=2)
    files_created.append(("transactions_log.json", "json", len(transactions_data)))
    print(f"  ✓ Created: transactions_log.json")
    
    # 4. Parquet format
    try:
        parquet_path = os.path.join(temp_dir, "analytics_data.parquet")
        users_data.to_parquet(parquet_path, index=False)
        files_created.append(("analytics_data.parquet", "parquet", len(users_data)))
        print(f"  ✓ Created: analytics_data.parquet")
    except ImportError:
        print(f"  ⚠ Skipped: analytics_data.parquet (pyarrow not installed)")
    
    # 5. TSV format (.tsv)
    tsv_path = os.path.join(temp_dir, "inventory_report.tsv")
    products_data.to_csv(tsv_path, sep="\t", index=False)
    files_created.append(("inventory_report.tsv", "tsv", len(products_data)))
    print(f"  ✓ Created: inventory_report.tsv")
    
    print(f"\\nTotal files created: {len(files_created)}\\n")
    return files_created


def demonstrate_multi_format_loading():
    """Demonstrate loading multiple file formats."""
    
    print("=" * 80)
    print("MULTI-FORMAT DATA LOADING DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Create temporary directory with sample files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create sample files
        files_created = create_sample_data_files(temp_dir)
        
        print("=" * 80)
        print("SCANNING AND LOADING FILES")
        print("=" * 80)
        print()
        
        # Initialize AutoDataLoader
        loader = AutoDataLoader(temp_dir)
        
        # Load all formats
        print("Loading all supported formats...")
        registry = loader.load_all_datasets()
        
        print()
        print("=" * 80)
        print("INVENTORY SUMMARY")
        print("=" * 80)
        
        # Print inventory
        loader.print_inventory()
        
        print()
        print("=" * 80)
        print("FILE FORMAT DETAILS")
        print("=" * 80)
        print()
        
        # Show details for each file type
        for dataset_name in sorted(registry.list_datasets()):
            metadata = registry.get_metadata(dataset_name)
            df = registry.get_dataset(dataset_name)
            
            print(f"📄 {dataset_name}")
            print(f"   Format: {metadata.file_type.upper()}")
            print(f"   Domain: {metadata.detected_domain}")
            print(f"   Shape: {metadata.row_count} rows × {metadata.column_count} columns")
            print(f"   Columns: {', '.join(metadata.column_names)}")
            print(f"   Size: {metadata.file_size_mb:.3f} MB")
            print()
        
        print("=" * 80)
        print("FORMAT-SPECIFIC LOADING TEST")
        print("=" * 80)
        print()
        
        # Test loading specific format types
        print("Testing format-specific loading...")
        
        # Load only CSV files
        loader_csv = AutoDataLoader(temp_dir)
        registry_csv = loader_csv.load_all_datasets(file_types=["csv"])
        print(f"  ✓ CSV only: {len(registry_csv.list_datasets())} dataset(s)")
        
        # Load only Excel files
        loader_excel = AutoDataLoader(temp_dir)
        registry_excel = loader_excel.load_all_datasets(file_types=["excel"])
        print(f"  ✓ Excel only: {len(registry_excel.list_datasets())} dataset(s)")
        
        # Load only JSON files
        loader_json = AutoDataLoader(temp_dir)
        registry_json = loader_json.load_all_datasets(file_types=["json"])
        print(f"  ✓ JSON only: {len(registry_json.list_datasets())} dataset(s)")
        
        print()
        print("=" * 80)
        print("SUPPORTED FORMATS")
        print("=" * 80)
        print()
        
        scanner = FolderScanner(temp_dir)
        print("Supported file formats:")
        for extension, format_name in sorted(scanner.SUPPORTED_FORMATS.items()):
            print(f"  • {extension:<10} → {format_name}")
        
        print()
        print("=" * 80)
        print("✅ DEMONSTRATION COMPLETE")
        print("=" * 80)
        print()
        print("💡 Key Features:")
        print("   1. Supports 5+ file formats (CSV, Excel, JSON, Parquet, TSV)")
        print("   2. Automatic format detection from file extension")
        print("   3. Unified loading interface via AutoDataLoader")
        print("   4. File type tracking in metadata")
        print("   5. Optional filtering by format type")
        print("   6. Hybrid domain detection works across all formats")
        print()


def demonstrate_format_detection():
    """Show format detection capabilities."""
    print("=" * 80)
    print("FORMAT DETECTION TEST")
    print("=" * 80)
    print()
    
    scanner = FolderScanner(".")
    
    test_files = [
        "users.csv",
        "products.xlsx",
        "data.xls",
        "events.json",
        "analytics.parquet",
        "report.tsv",
        "data.txt",
        "unknown.abc"
    ]
    
    print("Testing file type detection:")
    for filename in test_files:
        file_type = scanner.detect_file_type(Path(filename))
        status = "✓" if file_type else "✗"
        type_str = file_type if file_type else "unsupported"
        print(f"  {status} {filename:<25} → {type_str}")
    print()


def main():
    """Run all demonstrations."""
    demonstrate_multi_format_loading()
    demonstrate_format_detection()


if __name__ == "__main__":
    main()
