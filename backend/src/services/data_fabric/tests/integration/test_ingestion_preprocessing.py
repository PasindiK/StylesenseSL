"""Tests for ingestion layer data preprocessing."""

import pytest
import pandas as pd
from datetime import datetime
from src.ingestion.preprocessing import DataPreprocessor


class TestDataPreprocessor:
    """Test suite for DataPreprocessor."""

    def test_to_snake_case_camel_case(self):
        """Test CamelCase to snake_case conversion."""
        assert DataPreprocessor.to_snake_case("UserID") == "user_id"
        assert DataPreprocessor.to_snake_case("firstName") == "first_name"
        assert DataPreprocessor.to_snake_case("ProductName") == "product_name"

    def test_to_snake_case_spaces(self):
        """Test space-separated names to snake_case."""
        assert DataPreprocessor.to_snake_case("First Name") == "first_name"
        assert DataPreprocessor.to_snake_case("Email Address") == "email_address"
        assert DataPreprocessor.to_snake_case("Date Of Birth") == "date_of_birth"

    def test_to_snake_case_hyphens(self):
        """Test hyphen-separated names to snake_case."""
        assert DataPreprocessor.to_snake_case("Email-Address") == "email_address"
        assert DataPreprocessor.to_snake_case("User-ID") == "user_id"
        assert DataPreprocessor.to_snake_case("product-name") == "product_name"

    def test_to_snake_case_mixed(self):
        """Test mixed formatting to snake_case."""
        assert DataPreprocessor.to_snake_case("Product-ID") == "product_id"
        assert DataPreprocessor.to_snake_case("User Name 123") == "user_name_123"
        assert DataPreprocessor.to_snake_case("APIURL") == "apiurl"
        assert DataPreprocessor.to_snake_case("HTMLParser") == "html_parser"

    def test_to_snake_case_already_snake_case(self):
        """Test already snake_case names."""
        assert DataPreprocessor.to_snake_case("user_id") == "user_id"
        assert DataPreprocessor.to_snake_case("first_name") == "first_name"

    def test_normalize_column_names(self):
        """Test column name normalization."""
        df = pd.DataFrame({
            "UserID": [1, 2, 3],
            "First Name": ["Alice", "Bob", "Charlie"],
            "Email-Address": ["a@example.com", "b@example.com", "c@example.com"]
        })

        result = DataPreprocessor.normalize_column_names(df)

        assert "user_id" in result.columns
        assert "first_name" in result.columns
        assert "email_address" in result.columns
        assert len(result.columns) == 3

    def test_is_date_column(self):
        """Test date column detection."""
        assert DataPreprocessor.is_date_column("date") == True
        assert DataPreprocessor.is_date_column("created_at") == True
        assert DataPreprocessor.is_date_column("updated_time") == True
        assert DataPreprocessor.is_date_column("birth_date") == True
        assert DataPreprocessor.is_date_column("registration_date") == True
        assert DataPreprocessor.is_date_column("timestamp") == True
        
        assert DataPreprocessor.is_date_column("user_id") == False
        assert DataPreprocessor.is_date_column("name") == False
        assert DataPreprocessor.is_date_column("email") == False

    def test_is_numeric_column(self):
        """Test numeric column detection."""
        assert DataPreprocessor.is_numeric_column("price") == True
        assert DataPreprocessor.is_numeric_column("amount") == True
        assert DataPreprocessor.is_numeric_column("quantity") == True
        assert DataPreprocessor.is_numeric_column("user_id") == True
        assert DataPreprocessor.is_numeric_column("id") == True
        assert DataPreprocessor.is_numeric_column("count") == True
        assert DataPreprocessor.is_numeric_column("total") == True
        assert DataPreprocessor.is_numeric_column("age") == True
        
        assert DataPreprocessor.is_numeric_column("name") == False
        assert DataPreprocessor.is_numeric_column("email") == False
        assert DataPreprocessor.is_numeric_column("description") == False

    def test_normalize_date_column(self):
        """Test date column normalization."""
        dates = pd.Series(["2024-01-15", "2024-02-20", "2024-03-10"])
        result = DataPreprocessor.normalize_date_column(dates)
        
        # Should convert to ISO format
        assert result[0] == "2024-01-15"
        assert result[1] == "2024-02-20"
        assert result[2] == "2024-03-10"

    def test_normalize_date_column_various_formats(self):
        """Test date normalization with various input formats."""
        dates = pd.Series(["01/15/2024", "02-20-2024", "2024.03.10"])
        result = DataPreprocessor.normalize_date_column(dates)
        
        # Should handle different formats
        assert "2024" in result[0]
        assert "2024" in result[1]
        assert "2024" in result[2]

    def test_normalize_date_column_with_time(self):
        """Test date normalization with time component."""
        dates = pd.Series(["2024-01-15 10:30:00", "2024-02-20 14:45:00"])
        result = DataPreprocessor.normalize_date_column(dates)
        
        # Should preserve time in ISO format
        assert "2024-01-15" in result[0]
        assert "10:30:00" in result[0]

    def test_normalize_numeric_column(self):
        """Test numeric column conversion."""
        numbers = pd.Series(["100", "200.5", "300"])
        result = DataPreprocessor.normalize_numeric_column(numbers)
        
        assert result.dtype in [float, int, 'Int64', 'float64']
        assert result[0] == 100 or result[0] == 100.0
        assert result[1] == 200.5

    def test_normalize_numeric_column_integers(self):
        """Test integer conversion."""
        numbers = pd.Series(["1", "2", "3", "4", "5"])
        result = DataPreprocessor.normalize_numeric_column(numbers)
        
        # Should convert to integer type
        assert str(result.dtype).lower() in ['int64', 'int32', 'int']

    def test_normalize_numeric_column_with_nulls(self):
        """Test numeric conversion with null values."""
        numbers = pd.Series(["100", None, "200", "300", "400"])
        result = DataPreprocessor.normalize_numeric_column(numbers)
        
        assert pd.isna(result[1])
        assert result[0] == 100 or result[0] == 100.0
        assert result[2] == 200 or result[2] == 200.0

    def test_preprocess_full(self):
        """Test full preprocessing pipeline."""
        df = pd.DataFrame({
            "user_id": ["1", "2", "3"],
            "First Name": ["Alice", "Bob", "Charlie"],
            "RegistrationDate": ["2024-01-15", "2024-02-20", "2024-03-10"],
            "Account Balance": ["1500.50", "2300.75", "150.00"]
        })

        result = DataPreprocessor.preprocess(df)

        # Check column names normalized
        assert "user_id" in result.columns
        assert "first_name" in result.columns
        assert "registration_date" in result.columns
        assert "account_balance" in result.columns

        # Check numeric conversion (user_id matches _id$ pattern)
        assert result["user_id"].dtype in ['int64', 'Int64']
        assert result["account_balance"].dtype == float

    def test_preprocess_selective(self):
        """Test selective preprocessing."""
        df = pd.DataFrame({
            "UserID": ["1", "2", "3"],
            "First Name": ["Alice", "Bob", "Charlie"]
        })

        # Only normalize columns
        result = DataPreprocessor.preprocess(
            df,
            normalize_columns=True,
            normalize_dates=False,
            normalize_numeric=False
        )

        assert "user_id" in result.columns
        assert "first_name" in result.columns
        # Should still be string type
        assert result["user_id"].dtype == object

    def test_preprocess_no_changes(self):
        """Test preprocessing with all options disabled."""
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"]
        })

        result = DataPreprocessor.preprocess(
            df,
            normalize_columns=False,
            normalize_dates=False,
            normalize_numeric=False
        )

        # Should return unchanged (except as copy)
        assert list(result.columns) == list(df.columns)

    def test_get_preprocessing_summary(self):
        """Test preprocessing summary generation."""
        df_before = pd.DataFrame({
            "UserID": ["1", "2", "3"],
            "First Name": ["Alice", "Bob", "Charlie"]
        })

        df_after = DataPreprocessor.preprocess(df_before)

        summary = DataPreprocessor.get_preprocessing_summary(df_before, df_after)

        assert summary["total_columns"] == 2
        assert summary["total_rows"] == 3
        assert summary["columns_renamed"] == 2
        assert len(summary["column_renames"]) == 2

    def test_duplicate_column_handling(self):
        """Test handling of duplicate column names after normalization."""
        df = pd.DataFrame({
            "UserID": [1, 2, 3],
            "User_ID": [1, 2, 3],
            "user_id": [1, 2, 3]
        })

        result = DataPreprocessor.normalize_column_names(df)

        # Should have all columns with unique names
        assert len(result.columns) == 3
        assert len(set(result.columns)) == 3

    def test_empty_dataframe(self):
        """Test preprocessing with empty DataFrame."""
        df = pd.DataFrame()

        result = DataPreprocessor.preprocess(df)

        assert len(result) == 0
        assert len(result.columns) == 0

    def test_single_column(self):
        """Test preprocessing with single column."""
        df = pd.DataFrame({
            "user_id": ["1", "2", "3"]
        })

        result = DataPreprocessor.preprocess(df)

        assert "user_id" in result.columns
        assert result["user_id"].dtype in ['int64', 'Int64']

    def test_preserve_data_integrity(self):
        """Test that preprocessing doesn't lose data."""
        df = pd.DataFrame({
            "UserID": ["1", "2", "3"],
            "Name": ["Alice", "Bob", "Charlie"],
            "Price": ["100.50", "200.75", "300.00"]
        })

        result = DataPreprocessor.preprocess(df)

        # Same number of rows and columns
        assert len(result) == len(df)
        assert len(result.columns) == len(df.columns)

        # Data values preserved (in normalized columns)
        assert result["name"].tolist() == df["Name"].tolist()
