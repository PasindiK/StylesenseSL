"""Data ingestion automation script.

Usage:
    python scripts/data_ingestion.py --source csv --path data/raw_data.csv
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.logging_config import setup_logging, get_logger
from src.ingestion import CSVExtractor, DatabaseExtractor, APIExtractor

logger = get_logger(__name__)


def ingest_csv(filepath: str) -> None:
    """Ingest data from CSV file.

    Args:
        filepath: Path to CSV file
    """
    logger.info(f"Starting CSV ingestion from {filepath}")
    try:
        extractor = CSVExtractor()
        df = extractor.extract(filepath)
        logger.info(f"Successfully ingested {len(df)} rows from {filepath}")
        print(f"Ingested {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        logger.error(f"Failed to ingest from CSV: {e}")
        raise


def ingest_database(connection_string: str, table_name: str) -> None:
    """Ingest data from database.

    Args:
        connection_string: Database connection string
        table_name: Table name to ingest
    """
    logger.info(f"Starting database ingestion from {table_name}")
    try:
        extractor = DatabaseExtractor(connection_string)
        df = extractor.extract(table_name)
        logger.info(f"Successfully ingested {len(df)} rows from {table_name}")
        print(f"Ingested {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        logger.error(f"Failed to ingest from database: {e}")
        raise


def ingest_api(api_url: str) -> None:
    """Ingest data from API.

    Args:
        api_url: API endpoint URL
    """
    logger.info(f"Starting API ingestion from {api_url}")
    try:
        extractor = APIExtractor()
        df = extractor.extract(api_url)
        logger.info(f"Successfully ingested {len(df)} rows from {api_url}")
        print(f"Ingested {len(df)} rows, {len(df.columns)} columns")
    except Exception as e:
        logger.error(f"Failed to ingest from API: {e}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Data Fabric Data Ingestion Script")
    parser.add_argument(
        "--source",
        choices=["csv", "database", "api"],
        required=True,
        help="Data source type",
    )
    parser.add_argument("--path", help="Path to CSV file")
    parser.add_argument("--connection", help="Database connection string")
    parser.add_argument("--table", help="Database table name")
    parser.add_argument("--url", help="API endpoint URL")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    # Setup logging
    setup_logging()
    logging.getLogger().setLevel(args.log_level)

    logger.info("Data ingestion script started")

    try:
        if args.source == "csv":
            if not args.path:
                logger.error("--path required for CSV source")
                sys.exit(1)
            ingest_csv(args.path)

        elif args.source == "database":
            if not args.connection or not args.table:
                logger.error("--connection and --table required for database source")
                sys.exit(1)
            ingest_database(args.connection, args.table)

        elif args.source == "api":
            if not args.url:
                logger.error("--url required for API source")
                sys.exit(1)
            ingest_api(args.url)

        logger.info("Data ingestion completed successfully")

    except Exception as e:
        logger.error(f"Data ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
