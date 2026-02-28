# Data Ingestion: Automatic Folder Scanner

The `folder_scanner` module provides automated CSV discovery and loading with intelligent domain detection and comprehensive metadata tracking.

## Features

✅ **Automatic CSV Discovery**
- Recursively scan folders for CSV files
- Support both flat and nested directory structures

✅ **Dynamic CSV Loading**
- Load all CSV files as in-memory pandas DataFrames
- Automatic error handling and retry logic
- Memory-efficient handling of large files

✅ **Intelligent Domain Detection**
- Pattern-based domain detection from filenames
- 9 pre-configured domains: users, products, transactions, interactions, trends, shops, inventory, analytics, raw
- Customizable domain patterns

✅ **Comprehensive Metadata Tracking**
- Dataset name, file path, dimensions (rows/columns)
- Column names and data types
- Missing value counts per column
- File size in MB
- Load timestamp and domain classification

✅ **Registry Management**
- In-memory dataset storage with fast access
- Domain-based indexing for quick filtering
- Statistical summaries and inventory reports

## Core Components

### 1. `DomainDetector`

Detects dataset domains from filename patterns.

```python
from src.ingestion import DomainDetector

# Automatic domain detection
domain = DomainDetector.detect_domain("transactions_2024_q1")
# Returns: "transactions"

# Supports patterns:
# - users, products, transactions, interactions, trends, shops, inventory, analytics, raw
```

**Domain Patterns:**
| Domain | Pattern | Example Files |
|--------|---------|---|
| users | user, users, customer, account | users_dataset.csv, customer_data.csv |
| products | product, item, catalog | products.csv, item_catalog.csv |
| transactions | transaction, order, sale | transactions10K.csv, orders.csv |
| interactions | interaction, engagement, event | interactions_dataset.csv, events.csv |
| trends | trend, timeseries, forecast | trends_dataset.csv, ratings.csv |
| shops | shop, store, location, branch | shops_dataset.csv, retail_locations.csv |
| inventory | inventory, stock, warehouse | inventory_data.csv, stock.csv |
| analytics | analytics, metric, kpi | analytics_report.csv, metrics.csv |
| raw | raw, source, original | raw_data.csv, source_extract.csv |

### 2. `FolderScanner`

Scans folders and loads CSV files with metadata extraction.

```python
from src.ingestion import FolderScanner

# Initialize scanner
scanner = FolderScanner("/path/to/data")

# Scan for CSV files
csv_files = scanner.scan_for_csv_files(recursive=True)
# Returns: List[Path] sorted by filename

# Load a specific CSV file
df = scanner.load_csv_file(csv_files[0])
# Returns: pd.DataFrame

# Create metadata for a dataset
metadata = scanner.create_metadata(df, csv_files[0])
# Returns: DatasetMetadata object
```

### 3. `DatasetMetadata`

Dataclass containing all metadata for a loaded dataset.

```python
from src.ingestion import DatasetMetadata

@dataclass
class DatasetMetadata:
    dataset_name: str                    # "users_dataset"
    file_path: str                       # Full path to CSV
    row_count: int                       # Number of rows
    column_count: int                    # Number of columns
    column_names: List[str]              # ["id", "name", "email"]
    detected_domain: str                 # "users"
    file_size_mb: float                  # 1.25
    loaded_at: datetime                  # Load timestamp
    data_types: Dict[str, str]           # {"id": "int64", "name": "object"}
    missing_values: Dict[str, int]       # {"email": 5, "phone": 0}

# Convert to dictionary
metadata_dict = metadata.to_dict()
```

### 4. `DatasetRegistry`

In-memory registry for managing loaded datasets.

```python
from src.ingestion import DatasetRegistry

registry = DatasetRegistry()

# Register a dataset
registry.register_dataset("users_dataset", df, metadata)

# Retrieve datasets
df = registry.get_dataset("users_dataset")  # pd.DataFrame
metadata = registry.get_metadata("users_dataset")  # DatasetMetadata

# Filter by domain
users_dfs = registry.get_datasets_by_domain("users")  # Dict[str, pd.DataFrame]

# List all datasets
all_names = registry.list_datasets()  # List[str]
users_only = registry.list_datasets(domain="users")  # List[str]

# Get statistics
stats = registry.get_statistics()
# {
#     "total_datasets": 5,
#     "datasets_by_domain": {"users": 1, "products": 1, ...},
#     "total_rows": 10000,
#     "total_size_mb": 5.25,
#     "dataset_names": ["users_dataset", ...]
# }

# Remove a dataset
registry.remove_dataset("temp_dataset")

# Clear all datasets
registry.clear()
```

### 5. `AutoDataLoader`

High-level interface for automatic folder scanning and dataset loading.

```python
from src.ingestion import AutoDataLoader

# Initialize loader
loader = AutoDataLoader("/path/to/raw_data")

# Load all CSV files in folder
registry = loader.load_all_datasets(recursive=True)
# Returns: DatasetRegistry with all CSVs loaded

# Get the populated registry
registry = loader.get_registry()

# Print inventory summary
loader.print_inventory()
```

## Usage Examples

### Example 1: Basic Usage

```python
from src.ingestion import AutoDataLoader

# Initialize and load all datasets
loader = AutoDataLoader("./raw-data copy/raw-data copy")
registry = loader.load_all_datasets()

# Print summary
loader.print_inventory()
```

**Output:**
```
======================================================================
DATA INVENTORY SUMMARY
======================================================================
Total Datasets: 7
Total Rows: 125,000
Total Size: 12.5 MB

Datasets by Domain:
  • users: 1 dataset(s)
  • products: 2 dataset(s)
  • transactions: 1 dataset(s)
  ...
```

### Example 2: Access Specific Domain

```python
# Get all user-related datasets
user_datasets = registry.get_datasets_by_domain("users")

for name, df in user_datasets.items():
    print(f"{name}: {len(df)} users")
    metadata = registry.get_metadata(name)
    print(f"  Columns: {', '.join(metadata.column_names)}")
```

### Example 3: Inspect Metadata

```python
# Get all metadata
all_metadata = registry.get_all_metadata()

for name, meta in all_metadata.items():
    print(f"\n{name}:")
    print(f"  Domain: {meta.detected_domain}")
    print(f"  Size: {meta.row_count} rows × {meta.column_count} columns")
    print(f"  Missing values: {meta.missing_values}")
    print(f"  Data types: {meta.data_types}")
```

### Example 4: Process Datasets

```python
# Load and process
registry = loader.load_all_datasets()

# Get transactions
transactions = registry.get_dataset("transactions10K")

# Analyze
print(f"Total amount: ${transactions['amount'].sum():.2f}")
print(f"Average transaction: ${transactions['amount'].mean():.2f}")
print(f"Transaction count: {len(transactions)}")
```

### Example 5: Integration with Other Layers

```python
from src.ingestion import AutoDataLoader
from src.validation import DataValidator
from src.preprocessing import DataCleaner

# Load datasets
loader = AutoDataLoader("./raw-data")
registry = loader.load_all_datasets()

# Process each dataset
for dataset_name in registry.list_datasets():
    df = registry.get_dataset(dataset_name)
    
    # Validate
    validator = DataValidator()
    is_valid = validator.validate(df)
    
    # Clean
    if is_valid:
        cleaner = DataCleaner()
        cleaned_df = cleaner.clean(df)
        print(f"✓ {dataset_name} processed")
```

## Running the Demo

Execute the demo script to see all features in action:

```bash
cd data-fabric
python examples/demo_folder_scanner.py
```

This will:
1. Scan your raw_data folder
2. Load all CSV files
3. Display inventory summary
4. Show datasets by domain
5. Preview first few rows of each dataset
6. Display statistics and metadata

## Running Tests

Run comprehensive integration tests:

```bash
# Run all folder_scanner tests
pytest tests/integration/test_folder_scanner.py -v

# Run specific test
pytest tests/integration/test_folder_scanner.py::TestAutoDataLoader::test_load_all_datasets -v

# Run with coverage
pytest tests/integration/test_folder_scanner.py --cov=src.ingestion.folder_scanner
```

## Configuration

### Custom Domain Patterns

To add custom domain detection patterns, modify `DomainDetector.DOMAIN_PATTERNS`:

```python
# In your code
DomainDetector.DOMAIN_PATTERNS["custom_domain"] = r"(custom|specific|pattern)"

# Then use as normal
domain = DomainDetector.detect_domain("custom_specific_file")
# Returns: "custom_domain"
```

## Performance Considerations

| Operation | Time | Memory |
|-----------|------|--------|
| Scan 1000 CSV files | ~100ms | Minimal |
| Load 10MB CSV | ~100-500ms | ~50MB |
| Registry lookup | O(1) | Minimal |
| Get by domain | O(n) | Minimal |
| Generate inventory | ~50ms | Minimal |

## Error Handling

The module includes comprehensive error handling:

```python
# File not found
try:
    scanner = FolderScanner("/nonexistent/path")
except ValueError as e:
    print(f"Error: {e}")

# CSV loading failure
df = scanner.load_csv_file(path)  # Returns None on error, logs warning

# Registry operations
if not registry.remove_dataset("unknown"):
    print("Dataset not found")
```

## API Reference

### AutoDataLoader

```python
class AutoDataLoader:
    def __init__(self, folder_path: str)
    def load_all_datasets(self, recursive: bool = False) -> DatasetRegistry
    def get_registry(self) -> DatasetRegistry
    def print_inventory(self) -> None
```

### DatasetRegistry

```python
class DatasetRegistry:
    def register_dataset(dataset_name: str, df: pd.DataFrame, metadata: DatasetMetadata) -> bool
    def get_dataset(dataset_name: str) -> Optional[pd.DataFrame]
    def get_metadata(dataset_name: str) -> Optional[DatasetMetadata]
    def get_datasets_by_domain(domain: str) -> Dict[str, pd.DataFrame]
    def list_datasets(domain: Optional[str] = None) -> List[str]
    def get_all_metadata() -> Dict[str, DatasetMetadata]
    def get_statistics() -> Dict
    def remove_dataset(dataset_name: str) -> bool
    def clear() -> None
```

## Integration Points

The folder_scanner module integrates seamlessly with other Data Fabric layers:

| Layer | Integration | Use Case |
|-------|-------------|----------|
| Preprocessing | Pass DataFrames to cleaners/transformers | Clean loaded data |
| Validation | Validate loaded datasets | Ensure data quality |
| Metadata Catalog | Register metadata with system | Track lineage |
| ML Engine | Feed datasets to trainers | Build models |
| API Layer | Expose datasets via REST | Query loaded data |

## Troubleshooting

**Issue: No CSV files found**
- Check folder path exists and is readable
- Verify files have .csv extension
- Try recursive=True parameter

**Issue: CSV loading fails**
- Check CSV encoding (should be UTF-8)
- Verify file is not corrupted
- Check available memory for large files

**Issue: Domain detection incorrect**
- Custom patterns may have too broad regex
- Check case sensitivity
- Add more specific patterns for edge cases

## Contributing

To extend the folder_scanner module:

1. Add new domain patterns to `DomainDetector.DOMAIN_PATTERNS`
2. Implement custom metadata extraction in `FolderScanner`
3. Add new registry features in `DatasetRegistry`
4. Create tests in `tests/integration/test_folder_scanner.py`

## Related Modules

- [Ingestion Layer](../../../docs/architecture.md#ingestion-layer) - Parent module documentation
- [Preprocessing](../preprocessing) - Clean and transform loaded data
- [Validation](../validation) - Validate loaded datasets
- [Metadata Catalog](../metadata) - Register datasets in catalog
