"""Data Fabric - Enterprise Data Management System.

A modular, production-ready data fabric architecture supporting:
- Data ingestion from multiple sources
- Data preprocessing and transformation
- Quality validation and monitoring
- Metadata catalog and lineage tracking
- ML model integration and training
- RESTful API endpoints
- Automation scripts for batch processing
"""

__version__ = "1.0.0"
__author__ = "Data Fabric Team"

from .ingestion import SourceConnector, DataExtractor
from .preprocessing import DataTransformer, DataCleaner
from .validation import DataValidator, QualityChecker
from .metadata import MetadataCatalog, LineageTracker
from .integration import WorkflowOrchestrator

__all__ = [
    "SourceConnector",
    "DataExtractor",
    "DataTransformer",
    "DataCleaner",
    "DataValidator",
    "QualityChecker",
    "MetadataCatalog",
    "LineageTracker",
    "WorkflowOrchestrator",
]
