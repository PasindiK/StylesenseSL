"""Data extractors for various source types."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataExtractor(ABC):
    """Abstract base class for data extractors."""

    @abstractmethod
    def extract(
        self,
        source_location: str,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Extract data from source.

        Args:
            source_location: Source identifier or path
            query: Optional query for filtering
            **kwargs: Additional extraction parameters

        Returns:
            Extracted data as DataFrame
        """
        pass

    @abstractmethod
    def extract_batch(
        self,
        source_location: str,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> List[pd.DataFrame]:
        """Extract data in batches."""
        pass


class CSVExtractor(DataExtractor):
    """CSV file data extractor."""

    def extract(
        self,
        source_location: str,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Extract data from CSV file.

        Args:
            source_location: Path to CSV file
            query: Optional query for filtering (not used for CSV)
            **kwargs: Additional pandas read_csv parameters

        Returns:
            Extracted data as DataFrame
        """
        try:
            df = pd.read_csv(source_location, **kwargs)
            logger.info(f"Extracted {len(df)} rows from {source_location}")
            return df
        except Exception as e:
            logger.error(f"Failed to extract from CSV: {e}")
            raise

    def extract_batch(
        self,
        source_location: str,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> List[pd.DataFrame]:
        """Extract data from CSV in batches."""
        batches = []
        try:
            for chunk in pd.read_csv(source_location, chunksize=batch_size, **kwargs):
                batches.append(chunk)
            logger.info(f"Extracted {len(batches)} batches from {source_location}")
            return batches
        except Exception as e:
            logger.error(f"Failed to batch extract from CSV: {e}")
            raise


class ParquetExtractor(DataExtractor):
    """Parquet file data extractor."""

    def extract(
        self,
        source_location: str,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Extract data from Parquet file."""
        try:
            df = pd.read_parquet(source_location, **kwargs)
            logger.info(f"Extracted {len(df)} rows from {source_location}")
            return df
        except Exception as e:
            logger.error(f"Failed to extract from Parquet: {e}")
            raise

    def extract_batch(
        self,
        source_location: str,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> List[pd.DataFrame]:
        """Extract data from Parquet in batches."""
        df = self.extract(source_location, **kwargs)
        batches = [df[i : i + batch_size] for i in range(0, len(df), batch_size)]
        return batches


class APIExtractor(DataExtractor):
    """API data extractor."""

    def extract(
        self,
        source_location: str,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Extract data from API endpoint.

        Args:
            source_location: API endpoint URL
            query: Optional query parameters
            **kwargs: Additional request parameters

        Returns:
            Extracted data as DataFrame
        """
        try:
            import requests

            headers = kwargs.get("headers", {})
            params = query if isinstance(query, dict) else {}

            response = requests.get(source_location, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame([data])

            logger.info(f"Extracted {len(df)} rows from API: {source_location}")
            return df
        except Exception as e:
            logger.error(f"Failed to extract from API: {e}")
            raise

    def extract_batch(
        self,
        source_location: str,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> List[pd.DataFrame]:
        """Extract data from API in batches."""
        df = self.extract(source_location, **kwargs)
        batches = [df[i : i + batch_size] for i in range(0, len(df), batch_size)]
        return batches


class DatabaseExtractor(DataExtractor):
    """Database data extractor."""

    def __init__(self, connection_string: str):
        """Initialize with database connection."""
        self.connection_string = connection_string

    def extract(
        self,
        source_location: str,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Extract data from database.

        Args:
            source_location: Table name or database identifier
            query: SQL query to execute
            **kwargs: Additional pandas.read_sql parameters

        Returns:
            Extracted data as DataFrame
        """
        try:
            from sqlalchemy import create_engine

            engine = create_engine(self.connection_string)
            sql_query = query or f"SELECT * FROM {source_location}"

            df = pd.read_sql(sql_query, engine, **kwargs)
            logger.info(f"Extracted {len(df)} rows from database table: {source_location}")
            return df
        except Exception as e:
            logger.error(f"Failed to extract from database: {e}")
            raise

    def extract_batch(
        self,
        source_location: str,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> List[pd.DataFrame]:
        """Extract data from database in batches."""
        try:
            from sqlalchemy import create_engine

            engine = create_engine(self.connection_string)
            sql_query = f"SELECT * FROM {source_location}"

            batches = []
            for chunk in pd.read_sql(sql_query, engine, chunksize=batch_size, **kwargs):
                batches.append(chunk)

            logger.info(f"Extracted {len(batches)} batches from {source_location}")
            return batches
        except Exception as e:
            logger.error(f"Failed to batch extract from database: {e}")
            raise
