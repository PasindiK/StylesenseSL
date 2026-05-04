"""Pydantic schemas for API request/response validation (OpenAPI /docs)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaselineSummaryResponse(BaseModel):
    baseline_id: str
    dataset_name: str
    baseline_version: str
    status: str
    column_count: int
    message: str


class IngestionResponse(BaseModel):
    batch_id: str = Field(..., description="Unique ingestion batch id (Chroma-backed)")
    dataset_name: str
    status: str
    total_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    baseline_version: str = ""
    drift_results: List[Dict[str, Any]] = Field(default_factory=list)
    repair_actions: List[str] = Field(default_factory=list)
    message: str = ""


class BaselineVersionApproveBody(BaseModel):
    """Human-approved governance: register a new CSV as the next baseline version."""

    dataset_name: str
    created_by: str = "human_governance"
