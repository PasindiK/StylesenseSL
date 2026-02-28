"""API schemas / Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class DataSourceSchema(BaseModel):
    """Schema for data source."""

    id: str
    name: str
    source_type: str
    connection_string: str


class DatasetSchema(BaseModel):
    """Schema for dataset."""

    id: str
    name: str
    row_count: int
    column_count: int
    created_at: datetime


class TransformationSchema(BaseModel):
    """Schema for transformation."""

    type: str
    parameters: Dict[str, Any]


class ModelTrainingSchema(BaseModel):
    """Schema for model training."""

    model_type: str
    dataset_id: str
    hyperparameters: Optional[Dict[str, Any]] = None


class PredictionSchema(BaseModel):
    """Schema for predictions."""

    model_id: str
    data: Dict[str, Any]


class AssetMetadataSchema(BaseModel):
    """Schema for asset metadata."""

    name: str
    description: str
    owner: str
    asset_type: str
    tags: List[str] = Field(default_factory=list)
