"""
Simple CSV → Parquet → Azure Blob uploader
No Kafka needed. Reads sample transaction data, batches into parquet, uploads to Azure.
Perfect for testing the full pipeline quickly.

Usage:
    python scripts/csv_to_azure_pipeline.py --file data/transactions_dataset.csv --batch-size 100
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path so we can import storage module
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_paths():
    """Ensure required directories exist"""
    Path('bronze/raw').mkdir(parents=True, exist_ok=True)
    logger.info("✓ Directories ready")


def read_csv_in_batches(csv_path: str, batch_size: int = 100):
    """
    Read CSV file and yield batches
    
    Args:
        csv_path: Path to CSV file
        batch_size: Records per batch
    
    Yields:
        (batch_id, DataFrame) tuples
    """
    try:
        df = pd.read_csv(csv_path)
        logger.info(f"✓ Loaded {len(df)} records from {csv_path}")
        
        for batch_id, i in enumerate(range(0, len(df), batch_size)):
            batch_df = df.iloc[i:i+batch_size].copy()
            
            # Add metadata
            batch_df['batch_id'] = batch_id
            batch_df['ingested_at'] = datetime.utcnow().isoformat()
            batch_df['source'] = 'csv_pipeline'
            
            yield batch_id, batch_df
    
    except Exception as e:
        logger.error(f"✗ Failed to read CSV: {e}")
        raise


def save_batch_locally(batch_df: pd.DataFrame, batch_id: int) -> Path:
    """
    Save batch to local parquet file
    
    Args:
        batch_df: DataFrame to save
        batch_id: Batch identifier
    
    Returns:
        Path to saved file
    """
    output_path = Path('bronze/raw') / f"batch_{batch_id:05d}_{datetime.utcnow().strftime('%Y%m%d')}.parquet"
    
    try:
        batch_df.to_parquet(output_path, index=False, compression='snappy')
        logger.info(f"✓ Batch {batch_id}: saved locally ({len(batch_df)} records) → {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"✗ Failed to save batch {batch_id}: {e}")
        raise


def upload_to_azure(local_path: Path, container: str, blob_name: str) -> bool:
    """
    Upload parquet to Azure Blob Storage
    
    Args:
        local_path: Local file path
        container: Azure container name
        blob_name: Blob name inside container
    
    Returns:
        True if successful
    """
    try:
        from storage.azure_blob import upload_file_to_azure_blob
        
        success = upload_file_to_azure_blob(str(local_path), container, blob_name)
        return success
    
    except Exception as e:
        logger.error(f"✗ Azure upload failed: {e}")
        return False


def run_pipeline(csv_path: str, batch_size: int = 100, azure_container: str = 'bronze'):
    """
    Run complete pipeline: CSV → Parquet → Azure Blob
    
    Args:
        csv_path: Path to input CSV
        batch_size: Records per batch
        azure_container: Azure container name
    """
    logger.info("\n" + "="*70)
    logger.info("CSV → PARQUET → AZURE BLOB PIPELINE".center(70))
    logger.info("="*70 + "\n")
    
    # Setup
    setup_paths()
    
    # Check Azure connection
    if not os.environ.get('AZURE_STORAGE_CONNECTION_STRING'):
        logger.warning("⚠ AZURE_STORAGE_CONNECTION_STRING not set — saving locally only")
        upload_enabled = False
    else:
        from storage.azure_blob import test_azure_blob_connection
        upload_enabled = test_azure_blob_connection()
    
    stats = {
        'batches_created': 0,
        'batches_saved_locally': 0,
        'batches_uploaded_azure': 0,
        'total_records': 0,
        'failed_batches': 0
    }
    
    # Process batches
    logger.info(f"Processing {csv_path} in batches of {batch_size}...\n")
    
    for batch_id, batch_df in read_csv_in_batches(csv_path, batch_size):
        stats['batches_created'] += 1
        stats['total_records'] += len(batch_df)
        
        try:
            # Save locally
            local_path = save_batch_locally(batch_df, batch_id)
            stats['batches_saved_locally'] += 1
            
            # Upload to Azure if enabled
            if upload_enabled:
                blob_name = f"raw/{local_path.name}"
                if upload_to_azure(local_path, azure_container, blob_name):
                    stats['batches_uploaded_azure'] += 1
                    logger.info(f"  ↳ Uploaded to Azure: {azure_container}/{blob_name}\n")
            
        except Exception as e:
            logger.error(f"✗ Batch {batch_id} failed: {e}")
            stats['failed_batches'] += 1
    
    # Summary
    logger.info("="*70)
    logger.info("PIPELINE SUMMARY".center(70))
    logger.info("="*70)
    logger.info(f"Total records processed:       {stats['total_records']:,}")
    logger.info(f"Batches created:               {stats['batches_created']}")
    logger.info(f"Batches saved locally:         {stats['batches_saved_locally']}")
    logger.info(f"Batches uploaded to Azure:     {stats['batches_uploaded_azure']}")
    logger.info(f"Failed batches:                {stats['failed_batches']}")
    logger.info("="*70)
    
    if stats['failed_batches'] == 0:
        logger.info("✓ PIPELINE COMPLETED SUCCESSFULLY")
    else:
        logger.warning(f"⚠ {stats['failed_batches']} batches failed")
    
    logger.info("="*70 + "\n")
    
    return stats


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='CSV → Parquet → Azure Blob pipeline'
    )
    parser.add_argument('--file', default='data/transactions_dataset.csv',
                       help='Input CSV file (default: data/transactions_dataset.csv)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Records per batch (default: 100)')
    parser.add_argument('--container', default='bronze',
                       help='Azure container name (default: bronze)')
    
    args = parser.parse_args()
    
    # Validate input file
    csv_path = Path(args.file)
    if not csv_path.exists():
        logger.error(f"✗ File not found: {args.file}")
        sys.exit(1)
    
    try:
        run_pipeline(str(csv_path), args.batch_size, args.container)
        sys.exit(0)
    except Exception as e:
        logger.error(f"✗ Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
