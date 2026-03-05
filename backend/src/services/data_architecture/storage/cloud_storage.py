"""
Cloud storage helpers
Current implementation: Amazon S3 uploader (boto3)
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def upload_file_to_s3(local_path: str, bucket: str, key: str, aws_profile: Optional[str] = None) -> bool:
    """
    Upload a file to S3.

    Args:
        local_path: Local filesystem path to file
        bucket: S3 bucket name
        key: S3 object key (path inside bucket)
        aws_profile: Optional AWS profile name to use

    Returns:
        True on success, False otherwise
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        session_kwargs = {}
        if aws_profile:
            session_kwargs['profile_name'] = aws_profile

        session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
        s3 = session.client('s3')

        # Ensure file exists
        path = Path(local_path)
        if not path.exists():
            logger.error(f"Local file not found for upload: {local_path}")
            return False

        with open(path, 'rb') as f:
            s3.upload_fileobj(f, bucket, key)

        logger.info(f"Uploaded {local_path} to s3://{bucket}/{key}")
        return True

    except Exception as e:
        logger.warning(f"S3 upload failed for {local_path} -> s3://{bucket}/{key}: {e}")
        return False


def get_cloud_bucket_from_env() -> Optional[str]:
    """Read default cloud bucket name from environment"""
    return os.environ.get('CLOUD_STORAGE_BUCKET')
