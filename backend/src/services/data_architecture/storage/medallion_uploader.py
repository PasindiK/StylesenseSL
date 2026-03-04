"""
Medallion Architecture → Azure Blob with Storage Tiers
Bronze (raw) → Silver (cleaned) → Gold (curated)
Each layer uploads to Azure in separate containers with lifecycle policies
"""
import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from dotenv import dotenv_values
import pandas as pd

logger = logging.getLogger(__name__)


def get_azure_connection_string() -> Optional[str]:
    """Get Azure connection string from .env or environment"""
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    
    if not conn_str:
        env_file = Path(__file__).parent.parent / '.env'
        if env_file.exists():
            from dotenv import dotenv_values
            config = dotenv_values(str(env_file))
            conn_str = config.get('AZURE_STORAGE_CONNECTION_STRING')
    
    return conn_str


def upload_to_medallion_layer(layer: str, batch_df: pd.DataFrame, batch_id: int, 
                             batch_date: str) -> bool:
    """
    Upload batch to appropriate medallion layer in Azure with storage tier
    
    Args:
        layer: 'bronze', 'silver', or 'gold'
        batch_df: DataFrame to upload
        batch_id: Batch identifier
        batch_date: Date string (YYYYMMDD)
    
    Returns:
        True if successful
    """
    try:
        from azure.storage.blob import BlobServiceClient, StandardBlobTier
        
        conn_str = get_azure_connection_string()
        if not conn_str:
            logger.error(f"✗ Azure connection string not configured for {layer}")
            return False
        
        # Create parquet bytes
        import io
        parquet_bytes = io.BytesIO()
        batch_df.to_parquet(parquet_bytes, index=False, compression='snappy')
        parquet_bytes.seek(0)
        
        # Set up Azure paths (add timestamp to avoid collisions with archived blobs)
        from datetime import datetime
        timestamp = datetime.utcnow().strftime('%H%M%S')
        container = f"{layer.lower()}"
        blob_name = f"{layer}/{batch_id:05d}_{batch_date}_{timestamp}.parquet"
        
        # Upload
        client = BlobServiceClient.from_connection_string(conn_str)
        blob_client = client.get_blob_client(container, blob_name)
        blob_client.upload_blob(parquet_bytes.getvalue(), overwrite=True)
        
        file_size = len(parquet_bytes.getvalue())
        logger.info(f"✓ Uploaded batch {batch_id} to {layer} ({file_size:,} bytes)")
        # Attempt to apply seasonal tiering strategy after upload
        try:
            conn = get_azure_connection_string()
            if conn:
                try:
                    # local import to avoid import-time dependency issues
                    from storage.seasonal_tier_manager import SeasonalTierManager
                except Exception:
                    from seasonal_tier_manager import SeasonalTierManager

                try:
                    manager = SeasonalTierManager(conn)
                    manager.set_tier_for_layer(container, layer)
                except Exception as inner_e:
                    logger.warning(f"Could not apply seasonal tier for {layer}: {inner_e}")

        except Exception:
            # Non-fatal: continue even if tiering cannot be applied
            logger.debug("Seasonal tiering not applied (no connection or error)")
        return True
    
    except Exception as e:
        logger.error(f"✗ Failed to upload to {layer}: {str(e)}")
        return False


def create_containers_if_not_exist(layers: list = None):
    """Create medallion layer containers in Azure if they don't exist"""
    if layers is None:
        layers = ['bronze', 'silver', 'gold']
    
    try:
        from azure.storage.blob import BlobServiceClient
        
        conn_str = get_azure_connection_string()
        if not conn_str:
            logger.error("✗ Azure connection string not configured")
            return False
        
        client = BlobServiceClient.from_connection_string(conn_str)
        
        for layer in layers:
            try:
                container_client = client.get_container_client(layer)
                container_client.get_container_properties()
                logger.info(f"✓ Container '{layer}' already exists")
            except:
                container_client = client.create_container(layer)
                logger.info(f"✓ Created container '{layer}'")
        
        return True
    
    except Exception as e:
        logger.error(f"✗ Failed to create containers: {str(e)}")
        return False
