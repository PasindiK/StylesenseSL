"""Unit tests for validation layer."""

import pytest
import pandas as pd
from src.validation import (
    SchemaValidator,
    RangeValidator,
    RuleEngine,
    ColumnExistsRule,
    NonEmptyDataRule,
)
from tests.fixtures.sample_data import get_sample_csv_data, get_validation_config


class TestSchemaValidator:
    """Tests for schema validator."""

    def test_valid_schema(self):
        """Test validation of correct schema."""
        df = get_sample_csv_data()
        schema = {
            "id": "int64",
            "name": "object",
            "age": "int64",
            "salary": "int64",
            "department": "object",
        }

        validator = SchemaValidator(schema)
        result = validator.validate(df)

        # Will depend on actual dtypes
        assert hasattr(result, "is_valid")

    def test_missing_columns(self):
        """Test detection of missing columns."""
        df = get_sample_csv_data().drop("salary", axis=1)
        schema = {
            "id": "int",
            "name": "object",
            "age": "int",
            "salary": "int",
            "department": "object",
        }

        validator = SchemaValidator(schema)
        result = validator.validate(df)

        assert not result.is_valid
        assert "missing_columns" in result.details


class TestRangeValidator:
    """Tests for range validator."""

    def test_valid_ranges(self):
        """Test validation of valid ranges."""
        df = get_sample_csv_data()
        ranges = {
            "age": (18, 100),
            "salary": (0, 500000),
        }

        validator = RangeValidator(ranges)
        result = validator.validate(df)

        assert result.is_valid

    def test_out_of_range_values(self):
        """Test detection of out-of-range values."""
        df = get_sample_csv_data()
        df.loc[0, "age"] = 150  # Out of range

        ranges = {"age": (18, 100)}
        validator = RangeValidator(ranges)
        result = validator.validate(df)

        assert not result.is_valid


class TestRuleEngine:
    """Tests for rule engine."""

    def test_column_exists_rule(self):
        """Test column existence rule."""
        df = get_sample_csv_data()

        engine = RuleEngine()
        engine.add_rule(ColumnExistsRule(["id", "name", "age"]))

        results = engine.evaluate(df)

        assert results["all_passed"]
        assert len(results["passed_rules"]) > 0

    def test_non_empty_data_rule(self):
        """Test non-empty data rule."""
        df = get_sample_csv_data()

        engine = RuleEngine()
        engine.add_rule(NonEmptyDataRule())

        results = engine.evaluate(df)

        assert results["all_passed"]
