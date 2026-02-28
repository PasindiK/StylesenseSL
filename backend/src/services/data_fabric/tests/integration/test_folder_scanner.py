"""Integration tests for folder scanner module."""

import tempfile
import os
from pathlib import Path
import pandas as pd
import pytest

from src.ingestion import (
    AutoDataLoader,
    DatasetRegistry,
    DomainDetector,
    FolderScanner,
    DatasetMetadata,
)


@pytest.fixture
def temp_csv_folder():
    """Create temporary folder with sample CSV files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample CSV files with domain-specific names
        datasets = {
            "users_dataset.csv": pd.DataFrame(
                {
                    "user_id": [1, 2, 3],
                    "name": ["Alice", "Bob", "Charlie"],
                    "email": ["a@test.com", "b@test.com", "c@test.com"],
                }
            ),
            "products_catalog.csv": pd.DataFrame(
                {
                    "product_id": [101, 102, 103],
                    "name": ["Widget", "Gadget", "Tool"],
                    "price": [10.99, 20.50, 15.75],
                }
            ),
            "transactions_data.csv": pd.DataFrame(
                {
                    "transaction_id": [1001, 1002, 1003],
                    "user_id": [1, 2, 3],
                    "amount": [100.00, 50.00, 75.50],
                }
            ),
            "raw_events.csv": pd.DataFrame(
                {"event_id": [1, 2, 3], "event_type": ["click", "view", "purchase"]}
            ),
        }

        # Write CSV files
        for filename, df in datasets.items():
            path = os.path.join(tmpdir, filename)
            df.to_csv(path, index=False)

        yield tmpdir


class TestDomainDetector:
    """Tests for domain detection."""

    def test_detect_users_domain_from_columns(self):
        """Test detection of users domain from column names."""
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "email": ["a@test.com", "b@test.com", "c@test.com"],
            "name": ["Alice", "Bob", "Charlie"]
        })
        domain = DomainDetector.detect_domain(df, "data_file")
        assert domain == "users"

    def test_detect_products_domain_from_columns(self):
        """Test detection of products domain from column names."""
        df = pd.DataFrame({
            "product_id": [101, 102],
            "name": ["Widget", "Gadget"],
            "price": [10.99, 20.50]
        })
        domain = DomainDetector.detect_domain(df, "data_file")
        assert domain == "products"

    def test_detect_transactions_domain_from_columns(self):
        """Test detection of transactions domain from column names."""
        df = pd.DataFrame({
            "transaction_id": [1001, 1002],
            "amount": [100.00, 50.00],
            "user_id": [1, 2]
        })
        domain = DomainDetector.detect_domain(df, "data_file")
        assert domain == "transactions"

    def test_detect_from_filename_fallback(self):
        """Test detection falls back to filename when columns don't match."""
        df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})
        domain = DomainDetector.detect_domain(df, "users_dataset")
        assert domain == "users"

    def test_detect_unknown_domain(self):
        """Test detection of unknown domain."""
        df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})
        domain = DomainDetector.detect_domain(df, "mysterious_file")
        assert domain == "unknown"

    def test_case_insensitive_column_detection(self):
        """Test that column detection is case insensitive."""
        df = pd.DataFrame({
            "USER_ID": [1, 2],
            "EMAIL": ["a@test.com", "b@test.com"],
            "NAME": ["Alice", "Bob"]
        })
        domain = DomainDetector.detect_domain(df, "data_file")
        assert domain == "users"


class TestFolderScanner:
    """Tests for folder scanning and file loading."""

    def test_scan_csv_files(self, temp_csv_folder):
        """Test scanning for CSV files."""
        scanner = FolderScanner(temp_csv_folder)
        csv_files = scanner.scan_for_csv_files()

        assert len(csv_files) == 4
        filenames = [f.name for f in csv_files]
        assert "users_dataset.csv" in filenames

    def test_load_csv_file(self, temp_csv_folder):
        """Test loading a CSV file."""
        scanner = FolderScanner(temp_csv_folder)
        csv_files = scanner.scan_for_csv_files()
        df = scanner.load_csv_file(csv_files[0])

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_create_metadata(self, temp_csv_folder):
        """Test metadata creation."""
        scanner = FolderScanner(temp_csv_folder)
        csv_files = scanner.scan_for_csv_files()

        df = scanner.load_csv_file(csv_files[0])
        metadata = scanner.create_metadata(df, csv_files[0])

        assert isinstance(metadata, DatasetMetadata)
        assert metadata.dataset_name is not None
        assert metadata.file_type == "csv"
        assert metadata.row_count > 0
        assert metadata.column_count > 0
        assert len(metadata.column_names) > 0
        assert metadata.detected_domain is not None

    def test_scan_data_files(self, temp_csv_folder):
        """Test scanning for all data files."""
        scanner = FolderScanner(temp_csv_folder)
        data_files = scanner.scan_for_data_files()

        assert len(data_files) >= 4  # At least the CSV files
        
    def test_detect_file_type(self, temp_csv_folder):
        """Test file type detection."""
        scanner = FolderScanner(temp_csv_folder)
        
        from pathlib import Path
        assert scanner.detect_file_type(Path("test.csv")) == "csv"
        assert scanner.detect_file_type(Path("test.xlsx")) == "excel"
        assert scanner.detect_file_type(Path("test.json")) == "json"
        assert scanner.detect_file_type(Path("test.parquet")) == "parquet"
        assert scanner.detect_file_type(Path("test.tsv")) == "tsv"
        assert scanner.detect_file_type(Path("test.unknown")) is None


class TestDatasetRegistry:
    """Tests for dataset registry."""

    def test_register_dataset(self, temp_csv_folder):
        """Test registering a dataset."""
        registry = DatasetRegistry()
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        metadata = DatasetMetadata(
            dataset_name="test_data",
            file_path="/test/path.csv",
            file_type="csv",
            row_count=2,
            column_count=2,
            column_names=["a", "b"],
            detected_domain="unknown",
            file_size_mb=0.001,
            loaded_at=__import__("datetime").datetime.now(),
        )

        result = registry.register_dataset("test_data", df, metadata)
        assert result is True
        assert "test_data" in registry.list_datasets()

    def test_get_dataset(self, temp_csv_folder):
        """Test retrieving a dataset."""
        registry = DatasetRegistry()
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        metadata = DatasetMetadata(
            dataset_name="test_data",
            file_path="/test/path.csv",
            file_type="csv",
            row_count=2,
            column_count=2,
            column_names=["a", "b"],
            detected_domain="unknown",
            file_size_mb=0.001,
            loaded_at=__import__("datetime").datetime.now(),
        )

        registry.register_dataset("test_data", df, metadata)
        retrieved = registry.get_dataset("test_data")

        assert retrieved is not None
        assert len(retrieved) == 2

    def test_get_datasets_by_domain(self, temp_csv_folder):
        """Test retrieving datasets by domain."""
        registry = DatasetRegistry()

        # Register two user datasets and one product dataset
        for i in range(2):
            df = pd.DataFrame({"col": [1, 2]})
            metadata = DatasetMetadata(
                dataset_name=f"users_{i}",
                file_path=f"/test/users_{i}.csv",
                file_type="csv",
                row_count=2,
                column_count=1,
                column_names=["col"],
                detected_domain="users",
                file_size_mb=0.001,
                loaded_at=__import__("datetime").datetime.now(),
            )
            registry.register_dataset(f"users_{i}", df, metadata)

        df = pd.DataFrame({"col": [1, 2]})
        metadata = DatasetMetadata(
            dataset_name="products_0",
            file_path="/test/products_0.csv",
            file_type="csv",
            row_count=2,
            column_count=1,
            column_names=["col"],
            detected_domain="products",
            file_size_mb=0.001,
            loaded_at=__import__("datetime").datetime.now(),
        )
        registry.register_dataset("products_0", df, metadata)

        users_datasets = registry.get_datasets_by_domain("users")
        assert len(users_datasets) == 2

        products_datasets = registry.get_datasets_by_domain("products")
        assert len(products_datasets) == 1

    def test_remove_dataset(self, temp_csv_folder):
        """Test removing a dataset."""
        registry = DatasetRegistry()
        df = pd.DataFrame({"a": [1, 2]})

        metadata = DatasetMetadata(
            dataset_name="test_data",
            file_path="/test/path.csv",
            file_type="csv",
            row_count=2,
            column_count=1,
            column_names=["a"],
            detected_domain="unknown",
            file_size_mb=0.001,
            loaded_at=__import__("datetime").datetime.now(),
        )

        registry.register_dataset("test_data", df, metadata)
        assert "test_data" in registry.list_datasets()

        result = registry.remove_dataset("test_data")
        assert result is True
        assert "test_data" not in registry.list_datasets()

    def test_get_statistics(self, temp_csv_folder):
        """Test getting registry statistics."""
        registry = DatasetRegistry()
        df = pd.DataFrame({"a": [1, 2, 3]})

        metadata = DatasetMetadata(
            dataset_name="test_data",
            file_path="/test/path.csv",
            file_type="csv",
            row_count=3,
            column_count=1,
            column_names=["a"],
            detected_domain="test",
            file_size_mb=0.001,
            loaded_at=__import__("datetime").datetime.now(),
        )

        registry.register_dataset("test_data", df, metadata)
        stats = registry.get_statistics()

        assert stats["total_datasets"] == 1
        assert stats["total_rows"] == 3
        assert "test" in stats["datasets_by_domain"]


class TestAutoDataLoader:
    """Tests for automatic data loading."""

    def test_load_all_datasets(self, temp_csv_folder):
        """Test loading all datasets from folder."""
        loader = AutoDataLoader(temp_csv_folder)
        registry = loader.load_all_datasets()

        assert registry is not None
        assert len(registry.list_datasets()) == 4

    def test_dataset_inventory_summary(self, temp_csv_folder):
        """Test that inventory summary can be generated."""
        loader = AutoDataLoader(temp_csv_folder)
        registry = loader.load_all_datasets()

        # Should not raise an exception
        loader.print_inventory()

        # Verify statistics
        stats = registry.get_statistics()
        assert stats["total_datasets"] == 4
        assert stats["total_rows"] > 0

    def test_domain_based_loading(self, temp_csv_folder):
        """Test that datasets are correctly categorized by domain."""
        loader = AutoDataLoader(temp_csv_folder)
        registry = loader.load_all_datasets()

        # Check that domains are detected
        users = registry.get_datasets_by_domain("users")
        products = registry.get_datasets_by_domain("products")
        transactions = registry.get_datasets_by_domain("transactions")

        assert len(users) > 0
        assert len(products) > 0
        assert len(transactions) > 0

    def test_metadata_extraction(self, temp_csv_folder):
        """Test that metadata is properly extracted."""
        loader = AutoDataLoader(temp_csv_folder)
        registry = loader.load_all_datasets()

        all_metadata = registry.get_all_metadata()
        assert len(all_metadata) == 4

        for dataset_name, metadata in all_metadata.items():
            assert metadata.dataset_name is not None
            assert metadata.row_count > 0
            assert metadata.column_count > 0
            assert len(metadata.column_names) > 0
            assert metadata.detected_domain is not None
            assert metadata.file_size_mb > 0
