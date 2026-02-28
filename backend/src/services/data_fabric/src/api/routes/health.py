"""Health check endpoints."""

from fastapi import APIRouter
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/ping")
async def health_check() -> Dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy", "message": "Data Fabric API is running"}


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get API status.

    Returns:
        API status details
    """
    return {
        "status": "running",
        "version": "1.0.0",
        "service": "Data Fabric API",
    }
