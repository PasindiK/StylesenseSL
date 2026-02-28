"""Quick example: Load your data with automatic preprocessing.

This script shows how to use the ingestion layer with preprocessing enabled.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion import AutoDataLoader

# Path to your raw data folder
DATA_FOLDER = project_root.parent / "raw-data copy"

print("\n" + "=" * 80)
print("INGESTION WITH PREPROCESSING - Quick Example")
print("=" * 80)

# Option 1: Load with ALL preprocessing enabled (default)
print("\n1. Loading with full preprocessing (default)...")
print("-" * 80)
loader = AutoDataLoader(str(DATA_FOLDER))
registry = loader.load_all_datasets(enable_preprocessing=True)

print(f"\n✓ Loaded {len(registry.list_datasets())} datasets with preprocessing")

# Show sample dataset with preprocessed columns
if registry.list_datasets():
    dataset_name = registry.list_datasets()[0]
    df = registry.get_dataset(dataset_name)
    metadata = registry.get_metadata(dataset_name)
    
    print(f"\nSample: {dataset_name} ({metadata.detected_domain})")
    print(f"  Columns: {df.columns.tolist()[:5]}...")  # First 5
    print(f"  Dtypes: {dict(list(df.dtypes.to_dict().items())[:3])}...")  # First 3

# Option 2: Load WITHOUT preprocessing
print("\n2. Loading without preprocessing...")
print("-" * 80)
loader_no_prep = AutoDataLoader(str(DATA_FOLDER))
registry_no_prep = loader_no_prep.load_all_datasets(enable_preprocessing=False)

if registry_no_prep.list_datasets():
    dataset_name = registry_no_prep.list_datasets()[0]
    df_raw = registry_no_prep.get_dataset(dataset_name)
    
    print(f"\nSample: {dataset_name} (no preprocessing)")
    print(f"  Columns: {df_raw.columns.tolist()[:5]}...")

# Option 3: Selective preprocessing
print("\n3. Loading with selective preprocessing...")
print("-" * 80)
loader_selective = AutoDataLoader(str(DATA_FOLDER))
registry_selective = loader_selective.load_all_datasets(
    enable_preprocessing=True,
    normalize_columns=True,   # snake_case column names
    normalize_dates=False,    # Keep original date formats
    normalize_numeric=False   # Keep original types
)

print(f"✓ Loaded {len(registry_selective.list_datasets())} datasets with column normalization only")

# Show full inventory
print("\n4. Data Inventory")
print("-" * 80)
loader.print_inventory()

print("\n" + "=" * 80)
print("USAGE EXAMPLES")
print("=" * 80)
print("""
# Standard usage (with preprocessing):
from src.ingestion import AutoDataLoader

loader = AutoDataLoader("./raw-data copy/raw-data copy")
registry = loader.load_all_datasets()  # preprocessing enabled by default

# Get a specific dataset:
df = registry.get_dataset("users_dataset")

# Without preprocessing:
registry = loader.load_all_datasets(enable_preprocessing=False)

# Selective preprocessing:
registry = loader.load_all_datasets(
    enable_preprocessing=True,
    normalize_columns=True,   # Convert to snake_case
    normalize_dates=True,      # Convert to ISO format
    normalize_numeric=True     # Convert string numbers to numeric
)
""")
print("=" * 80)
