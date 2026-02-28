"""Demo: Data validation with comprehensive quality checks.

This script demonstrates:
1. Primary key duplicate detection
2. Foreign key relationship validation
3. Missing value analysis
4. Anomaly detection (negative prices, outliers)
5. Comprehensive validation reports
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import AutoDataLoader, DataValidator, ValidationSeverity

# Path to your raw data folder
DATA_FOLDER = project_root.parent / "raw-data copy"

print("\n" + "=" * 80)
print("DATA VALIDATION DEMO")
print("=" * 80)

# Step 1: Load the data with preprocessing
print("\n1. Loading datasets...")
print("-" * 80)
loader = AutoDataLoader(str(DATA_FOLDER))
registry = loader.load_all_datasets(enable_preprocessing=True)

print(f"✓ Loaded {len(registry.list_datasets())} datasets")
loader.print_inventory()

# Step 2: Initialize validator and run validation
print("\n2. Running comprehensive validation...")
print("-" * 80)
validator = DataValidator()

# Run all validation checks
report = validator.validate_registry(
    registry,
    check_primary_keys=True,      # Detect duplicate primary keys
    check_foreign_keys=True,      # Validate relationships
    check_missing_values=True,    # Log missing values
    check_anomalies=True          # Detect anomalies
)

# Step 3: Print detailed report
print("\n3. Validation Results")
print("-" * 80)
validator.print_report(report, show_all=False)  # Show errors and warnings only

# Step 4: Analyze specific issues
print("\n4. Issue Analysis")
print("-" * 80)

# Critical issues
critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
if critical_issues:
    print(f"\n⚠️  CRITICAL ISSUES ({len(critical_issues)}):")
    for issue in critical_issues:
        print(f"  • {issue.dataset_name}: {issue.description}")
else:
    print("\n✓ No critical issues found")

# Errors
errors = report.get_issues_by_severity(ValidationSeverity.ERROR)
if errors:
    print(f"\n❌ ERRORS ({len(errors)}):")
    for issue in errors[:5]:  # Show first 5
        print(f"  • {issue.dataset_name}", end="")
        if issue.column_name:
            print(f".{issue.column_name}", end="")
        print(f": {issue.description}")
    if len(errors) > 5:
        print(f"  ... and {len(errors) - 5} more errors")
else:
    print("\n✓ No errors found")

# Warnings
warnings = report.get_issues_by_severity(ValidationSeverity.WARNING)
if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for issue in warnings[:5]:  # Show first 5
        print(f"  • {issue.dataset_name}", end="")
        if issue.column_name:
            print(f".{issue.column_name}", end="")
        print(f": {issue.description}")
    if len(warnings) > 5:
        print(f"  ... and {len(warnings) - 5} more warnings")
else:
    print("\n✓ No warnings found")

# Step 5: Dataset-specific analysis
print("\n5. Dataset-Specific Issues")
print("-" * 80)

for dataset_name in sorted(registry.list_datasets()):
    dataset_issues = report.get_issues_by_dataset(dataset_name)
    
    if dataset_issues:
        errors_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.ERROR])
        warnings_count = len([i for i in dataset_issues if i.severity == ValidationSeverity.WARNING])
        
        print(f"\n{dataset_name}:")
        print(f"  Issues: {len(dataset_issues)} (Errors: {errors_count}, Warnings: {warnings_count})")
        
        # Show top issues
        for issue in dataset_issues[:3]:
            print(f"  • [{issue.severity.value}] {issue.category}: {issue.description}")

# Step 6: Show specific validation categories
print("\n6. Validation Category Breakdown")
print("-" * 80)

category_counts = report.summary.get("by_category", {})
for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {category:<30} {count:>3} issue(s)")

# Step 7: Export report (optional)
print("\n7. Report Export")
print("-" * 80)

# Convert report to dictionary (can be saved as JSON)
report_dict = report.to_dict()
print(f"✓ Report contains {len(report_dict['issues'])} issues")
print(f"✓ Validated {report_dict['total_datasets']} datasets with {report_dict['total_rows']:,} total rows")

# Step 8: Recommendations
print("\n8. Recommendations")
print("-" * 80)

if report.has_critical_issues():
    print("⚠️  CRITICAL: Address critical issues immediately before using this data!")
elif len(errors) > 0:
    print("⚠️  Action needed: Fix data quality errors to ensure data integrity")
elif len(warnings) > 0:
    print("ℹ️  Consider reviewing warnings to improve data quality")
else:
    print("✓ Data quality is good! No critical issues found.")

# Show specific recommendations based on issues found
recommendations = []

# Check for FK violations
fk_issues = [i for i in report.issues if i.category == "Foreign Key Violation"]
if fk_issues:
    recommendations.append("• Clean up orphaned records or update foreign key references")

# Check for duplicate PKs
pk_issues = [i for i in report.issues if i.category == "Primary Key Integrity"]
if pk_issues:
    recommendations.append("• Remove or merge duplicate primary key values")

# Check for negative values
negative_issues = [i for i in report.issues if i.category == "Data Anomaly" and "negative" in i.description.lower()]
if negative_issues:
    recommendations.append("• Investigate and correct negative values in price/amount columns")

# Check for missing values
missing_issues = [i for i in report.issues if i.category == "Missing Values" and i.severity == ValidationSeverity.ERROR]
if missing_issues:
    recommendations.append("• Fill critical missing values or remove incomplete records")

if recommendations:
    print("\nSpecific Recommendations:")
    for rec in recommendations:
        print(f"  {rec}")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)

# Step 9: Usage examples
print("\n9. Programmatic Usage Examples")
print("-" * 80)
print("""
# Basic validation:
from src.ingestion import AutoDataLoader, DataValidator

loader = AutoDataLoader("./data")
registry = loader.load_all_datasets()
validator = DataValidator()
report = validator.validate_registry(registry)
validator.print_report()

# Check for specific issues:
critical_issues = report.get_issues_by_severity(ValidationSeverity.CRITICAL)
dataset_issues = report.get_issues_by_dataset("transactions10K")

# Selective validation:
report = validator.validate_registry(
    registry,
    check_primary_keys=True,
    check_foreign_keys=True,
    check_missing_values=False,  # Skip missing value checks
    check_anomalies=False         # Skip anomaly detection
)

# Export report as JSON:
import json
with open("validation_report.json", "w") as f:
    json.dump(report.to_dict(), f, indent=2)
""")

print("=" * 80)
