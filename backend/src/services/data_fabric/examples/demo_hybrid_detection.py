#!/usr/bin/env python3
"""Demonstration of hybrid domain detection (column-based + filename fallback).

This script shows:
1. Primary detection: Analyzing column names for domain signatures
2. Fallback detection: Using filename patterns when columns don't match
3. Comparison: Side-by-side results from both methods
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import DomainDetector


def demonstrate_column_based_detection():
    """Show how column-based detection works."""
    print("\n" + "=" * 80)
    print("🔍 COLUMN-BASED DETECTION (Primary Method)")
    print("=" * 80)

    test_cases = [
        {
            "name": "Users Dataset",
            "df": pd.DataFrame({
                "user_id": [1, 2, 3],
                "email": ["alice@test.com", "bob@test.com", "charlie@test.com"],
                "name": ["Alice", "Bob", "Charlie"],
                "registration_date": ["2024-01-01", "2024-01-02", "2024-01-03"]
            }),
            "filename": "mystery_file_001"
        },
        {
            "name": "Products Dataset",
            "df": pd.DataFrame({
                "product_id": [101, 102, 103],
                "name": ["Widget", "Gadget", "Tool"],
                "price": [10.99, 20.50, 15.75],
                "category": ["A", "B", "C"]
            }),
            "filename": "data_export"
        },
        {
            "name": "Transactions Dataset",
            "df": pd.DataFrame({
                "transaction_id": [1001, 1002, 1003],
                "amount": [100.00, 50.00, 75.50],
                "user_id": [1, 2, 3],
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"]
            }),
            "filename": "sales_report"
        },
        {
            "name": "Inventory Dataset",
            "df": pd.DataFrame({
                "product_id": [101, 102, 103],
                "quantity": [50, 25, 100],
                "warehouse": ["A", "B", "A"],
                "sku": ["SKU001", "SKU002", "SKU003"]
            }),
            "filename": "stock_data"
        },
    ]

    for test in test_cases:
        domain = DomainDetector.detect_domain(test["df"], test["filename"])
        columns = ", ".join(test["df"].columns.tolist())
        
        print(f"\n📋 {test['name']}")
        print(f"   Filename: {test['filename']}")
        print(f"   Columns: {columns}")
        print(f"   ✅ Detected Domain: '{domain.upper()}'")


def demonstrate_filename_fallback():
    """Show how filename fallback detection works."""
    print("\n\n" + "=" * 80)
    print("📂 FILENAME FALLBACK DETECTION (Secondary Method)")
    print("=" * 80)

    # Generic DataFrame with no recognizable columns
    generic_df = pd.DataFrame({
        "col_a": [1, 2, 3],
        "col_b": [4, 5, 6],
        "col_c": [7, 8, 9]
    })

    test_filenames = [
        "users_dataset",
        "products_catalog",
        "transactions_2024",
        "shop_locations",
        "inventory_report",
        "customer_interactions",
        "sales_trends",
        "analytics_dashboard",
        "mysterious_data"
    ]

    print("\nUsing generic DataFrame with columns: col_a, col_b, col_c")
    print("Domain will be detected from filename only:\n")

    for filename in test_filenames:
        domain = DomainDetector.detect_domain(generic_df, filename)
        print(f"   📄 {filename:<30} → {domain.upper()}")


def demonstrate_hybrid_approach():
    """Show the hybrid approach in action."""
    print("\n\n" + "=" * 80)
    print("🔄 HYBRID APPROACH: Column Detection + Filename Fallback")
    print("=" * 80)

    scenarios = [
        {
            "title": "Scenario 1: Columns match perfectly → Use column detection",
            "df": pd.DataFrame({
                "user_id": [1, 2],
                "email": ["a@test.com", "b@test.com"],
                "name": ["Alice", "Bob"]
            }),
            "filename": "random_data_export_2024"
        },
        {
            "title": "Scenario 2: Columns don't match → Fallback to filename",
            "df": pd.DataFrame({
                "field1": [1, 2],
                "field2": ["x", "y"],
                "field3": [100, 200]
            }),
            "filename": "products_catalog_v2"
        },
        {
            "title": "Scenario 3: Neither match → Unknown domain",
            "df": pd.DataFrame({
                "random_col": [1, 2],
                "another_col": ["a", "b"]
            }),
            "filename": "mystery_file_xyz"
        },
        {
            "title": "Scenario 4: Case-insensitive column matching",
            "df": pd.DataFrame({
                "TRANSACTION_ID": [1001, 1002],
                "AMOUNT": [100.0, 200.0],
                "USER_ID": [1, 2]
            }),
            "filename": "unknown_export"
        },
    ]

    for scenario in scenarios:
        print(f"\n{scenario['title']}")
        print(f"   Columns: {', '.join(scenario['df'].columns)}")
        print(f"   Filename: {scenario['filename']}")
        
        domain = DomainDetector.detect_domain(scenario["df"], scenario["filename"])
        print(f"   ✅ Result: '{domain.upper()}'")


def show_domain_signatures():
    """Display all available domain signatures."""
    print("\n\n" + "=" * 80)
    print("📚 AVAILABLE DOMAIN SIGNATURES")
    print("=" * 80)

    print("\n🔹 Column-Based Signatures:\n")
    for domain, signature in DomainDetector.COLUMN_SIGNATURES.items():
        required = ", ".join(signature["required"])
        optional = ", ".join(signature["optional"][:5])  # Show first 5
        print(f"   {domain.upper()}")
        print(f"      Required: {required}")
        print(f"      Optional: {optional}...")
        print()


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 80)
    print("🚀 HYBRID DOMAIN DETECTION DEMONSTRATION")
    print("=" * 80)

    # Show all demonstrations
    demonstrate_column_based_detection()
    demonstrate_filename_fallback()
    demonstrate_hybrid_approach()
    show_domain_signatures()

    print("\n" + "=" * 80)
    print("✅ Demo Complete!")
    print("\n💡 Key Takeaways:")
    print("   1. Column-based detection is MORE ACCURATE (primary method)")
    print("   2. Filename matching is FALLBACK when columns don't match")
    print("   3. Both methods work case-insensitively")
    print("   4. Returns 'unknown' if neither method finds a match")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
