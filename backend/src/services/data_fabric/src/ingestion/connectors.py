"""Data source connectors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SourceConnector(ABC):
    """Abstract base class for data source connectors."""

    def __init__(self, connection_string: str, credentials: Optional[Dict[str, Any]] = None):
        """Initialize connector.

        Args:
            connection_string: Connection string or path
            credentials: Connection credentials
        """
        self.connection_string = connection_string
        self.credentials = credentials or {}
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if connection is valid."""
        pass


class PostgreSQLConnector(SourceConnector):
    """PostgreSQL database connector."""

    def __init__(self, connection_string: str):
        """Initialize PostgreSQL connector."""
        super().__init__(connection_string)
        self.connection = None

    def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            import psycopg2

            self.connection = psycopg2.connect(self.connection_string)
            self.is_connected = True
            logger.info("Connected to PostgreSQL database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False

    def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self.connection:
            self.connection.close()
            self.is_connected = False
            logger.info("Disconnected from PostgreSQL")

    def test_connection(self) -> bool:
        """Test PostgreSQL connection."""
        if not self.is_connected:
            return self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def execute_query(self, query: str) -> list:
        """Execute a SQL query."""
        if not self.is_connected:
            raise RuntimeError("Not connected to database")
        cursor = self.connection.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        return result


class S3Connector(SourceConnector):
    """AWS S3 connector."""

    def __init__(
        self, bucket: str, region: str, access_key: str, secret_key: str
    ):
        """Initialize S3 connector."""
        super().__init__(bucket)
        self.bucket = bucket
        self.region = region
        self.client = None
        self.credentials = {"access_key": access_key, "secret_key": secret_key}

    def connect(self) -> bool:
        """Connect to S3."""
        try:
            import boto3

            self.client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.credentials["access_key"],
                aws_secret_access_key=self.credentials["secret_key"],
            )
            self.is_connected = True
            logger.info(f"Connected to S3 bucket: {self.bucket}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to S3: {e}")
            return False

    def disconnect(self) -> None:
        """Close S3 connection."""
        self.is_connected = False
        logger.info("Disconnected from S3")

    def test_connection(self) -> bool:
        """Test S3 connection."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.error(f"S3 connection test failed: {e}")
            return False

    def list_objects(self, prefix: str = "") -> list:
        """List objects in S3 bucket."""
        if not self.is_connected:
            raise RuntimeError("Not connected to S3")
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            return response.get("Contents", [])
        except Exception as e:
            logger.error(f"Failed to list S3 objects: {e}")
            return []

    def get_object(self, key: str) -> Optional[bytes]:
        """Get object from S3."""
        if not self.is_connected:
            raise RuntimeError("Not connected to S3")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            logger.error(f"Failed to get S3 object: {e}")
            return None
