"""Metadata synchronization script.

Usage:
    python scripts/metadata_sync.py --catalog-path metadata/catalog.json
"""

import argparse
import logging
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.logging_config import setup_logging, get_logger
from src.metadata import MetadataCatalog, DataAsset, DatasetMetadata
from datetime import datetime

logger = get_logger(__name__)


def sync_metadata(catalog_path: str) -> None:
    """Synchronize metadata catalog.

    Args:
        catalog_path: Path to metadata catalog
    """
    logger.info(f"Synchronizing metadata catalog: {catalog_path}")

    catalog = MetadataCatalog()

    # Example: Register some assets
    metadata = DatasetMetadata(
        name="Sample Dataset",
        description="A sample dataset for testing",
        owner="admin",
        source_system="CSV",
        schema={"col1": "string", "col2": "int"},
        row_count=1000,
        column_count=2,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=["sample", "test"],
    )

    asset = DataAsset(
        asset_id="asset_001",
        name="Sample Dataset",
        asset_type="table",
        location="/data/sample.csv",
        metadata=metadata,
    )

    catalog.register_asset(asset)
    logger.info(f"Registered asset: {asset.asset_id}")

    # Get statistics
    stats = catalog.get_statistics()
    logger.info(f"Catalog statistics: {stats}")

    print("\n" + "=" * 50)
    print("METADATA CATALOG STATISTICS")
    print("=" * 50)
    for key, value in stats.items():
        print(f"{key}: {value}")

    logger.info("Metadata synchronization completed")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Data Fabric Metadata Sync")
    parser.add_argument("--catalog-path", required=True, help="Path to catalog file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    setup_logging()
    logging.getLogger().setLevel(args.log_level)

    logger.info("Metadata sync script started")

    try:
        sync_metadata(args.catalog_path)
        logger.info("Metadata sync completed successfully")
    except Exception as e:
        logger.error(f"Metadata sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
