"""Unit tests for ingestion layer."""

import pytest
from src.ingestion import CSVExtractor, DataSource, SourceRegistry, SourceType
from tests.fixtures.sample_data import get_sample_csv_data
import tempfile
import pandas as pd


class TestCSVExtractor:
    """Tests for CSV extractor."""

    def test_extract_csv(self, tmp_path):
        """Test CSV extraction."""
        # Create temporary CSV file
        df = get_sample_csv_data()
        csv_file = tmp_path / "test.csv"
        df.to_csv(csv_file, index=False)

        # Extract
        extractor = CSVExtractor()
        result = extractor.extract(str(csv_file))

        assert len(result) == len(df)
        assert list(result.columns) == list(df.columns)

    def test_batch_extraction(self, tmp_path):
        """Test batch CSV extraction."""
        df = get_sample_csv_data()
        csv_file = tmp_path / "test.csv"
        df.to_csv(csv_file, index=False)

        extractor = CSVExtractor()
        batches = extractor.extract_batch(str(csv_file), batch_size=25)

        assert len(batches) == 4
        assert len(batches[0]) == 25


class TestSourceRegistry:
    """Tests for source registry."""

    def test_register_source(self):
        """Test source registration."""
        registry = SourceRegistry()
        source = DataSource(
            id="test_source",
            name="Test Source",
            source_type=SourceType.CSV,
            connection_string="/path/to/data.csv",
        )

        registry.register(source)
        retrieved = registry.get("test_source")

        assert retrieved is not None
        assert retrieved.id == "test_source"

    def test_list_sources(self):
        """Test listing sources."""
        registry = SourceRegistry()
        sources = [
            DataSource(
                id=f"source_{i}",
                name=f"Source {i}",
                source_type=SourceType.CSV,
                connection_string=f"/path/{i}.csv",
            )
            for i in range(3)
        ]

        for source in sources:
            registry.register(source)

        listed = registry.list_sources()
        assert len(listed) == 3
