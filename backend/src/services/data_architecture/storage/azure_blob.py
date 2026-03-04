"""
Azure Blob Storage uploader
Handles uploading parquet batches to Azure Blob Storage
"""
import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


def upload_file_to_azure_blob(local_path: str, container: str, blob_name: str,
                             connection_string: Optional[str] = None) -> bool:
    """
    Upload a file to Azure Blob Storage.
    
    Args:
        local_path: Local filesystem path to file
        container: Azure container name (e.g., 'bronze')
        blob_name: Blob name/path inside container (e.g., 'raw/batch_00001.parquet')
        connection_string: Azure Storage connection string (default: env var AZURE_STORAGE_CONNECTION_STRING)
    
    Returns:
        True on success, False otherwise
    
    Example:
        >>> upload_file_to_azure_blob('bronze/raw/batch_00001.parquet', 'bronze', 'raw/batch_00001.parquet')
    """
    try:
        from azure.storage.blob import BlobServiceClient
        
        # Get connection string from env if not provided. Fall back to .env file.
        if connection_string is None:
            connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
            if not connection_string:
                # Try reading from .env via helper
                env_file = Path(__file__).parent.parent / '.env'
                if env_file.exists():
                    from dotenv import dotenv_values
                    cfg = dotenv_values(str(env_file))
                    connection_string = cfg.get('AZURE_STORAGE_CONNECTION_STRING')

        if not connection_string:
            logger.error("AZURE_STORAGE_CONNECTION_STRING not set in environment or .env")
            return False
        
        # Ensure file exists locally
        path = Path(local_path)
        if not path.exists():
            logger.error(f"Local file not found: {local_path}")
            return False
        
        # Create blob client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container)
        blob_client = container_client.get_blob_client(blob_name)
        
        # Upload file
        with open(path, 'rb') as data:
            blob_client.upload_blob(data, overwrite=True)
        
        file_size = path.stat().st_size
        logger.info(f"✓ Uploaded {local_path} ({file_size:,} bytes) to Azure Blob: {container}/{blob_name}")
        return True
    
    except Exception as e:
        logger.error(f"✗ Azure Blob upload failed for {local_path}: {str(e)}")
        return False


def get_azure_connection_string() -> Optional[str]:
    """Get Azure Storage connection string from environment or .env file"""
    # First try environment variable
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    
    # If not found, try to read from .env file in project root
    if not conn_str:
        env_file = Path(__file__).parent.parent / '.env'
        if env_file.exists():
            from dotenv import dotenv_values
            config = dotenv_values(str(env_file))
            conn_str = config.get('AZURE_STORAGE_CONNECTION_STRING')
    
    return conn_str


def test_azure_blob_connection() -> bool:
    """Test if Azure Blob connection is valid"""
    try:
        from azure.storage.blob import BlobServiceClient
        
        conn_str = get_azure_connection_string()
        if not conn_str:
            logger.error("AZURE_STORAGE_CONNECTION_STRING not configured")
            return False
        
        client = BlobServiceClient.from_connection_string(conn_str)
        # Try to get account properties
        client.get_account_information()
        logger.info("✓ Azure Blob connection successful")
        return True
    
    except Exception as e:
        logger.error(f"✗ Azure Blob connection failed: {str(e)}")
        return False
