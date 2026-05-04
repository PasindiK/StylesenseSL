"""
Logical data models for semantic drift (persisted as JSON in ChromaDB documents).

These mirror the relational design from the spec; we do not use SQLAlchemy here
because the project owner asked for Chroma-backed storage with unique IDs for
demo and append/quarantine routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SemanticBaselineRegistry:
    id: str
    dataset_name: str
    baseline_version: str
    status: str  # active | inactive
    created_at: str
    created_by: str


@dataclass
class BaselineColumnProfile:
    id: str
    baseline_id: str
    column_name: str
    business_meaning: str
    role: str
    domain: str
    unit: str
    scale: str
    data_type: str
    value_direction: str
    expected_pattern: str = ""
    drift_sensitivity: str = "medium"


@dataclass
class IngestionBatch:
    id: str
    batch_id: str
    dataset_name: str
    baseline_version: str
    uploaded_at: str
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int


@dataclass
class SemanticDriftResultRow:
    id: str
    batch_id: str
    baseline_version: str
    column_name: str
    baseline_meaning: str
    new_meaning: str
    similarity_score: float
    drift_score: float
    severity: str
    decision: str
    reasons: List[str]
    explanation: str
    business_risk: str = ""
    recommended_action: str = ""


@dataclass
class QuarantinedDataset:
    id: str
    batch_id: str
    dataset_name: str
    reason: str
    suggested_action: str
    created_at: str


@dataclass
class SalesTransaction:
    record_id: str
    customer_id: str
    order_id: str
    sales_amount: float
    quantity: int
    discount_amount: float
    order_date: str
    ingestion_batch_id: str
    baseline_version: str
    drift_status: str
    repair_action: str
    ingested_at: str
    extra: Dict[str, Any] = field(default_factory=dict)


def demo_rules_baseline_columns() -> Dict[str, Dict[str, str]]:
    """Rule-based approved meanings for demo sales CSV (viva script)."""
    return {
        "customer_id": {
            "business_meaning": "Unique customer identifier",
            "role": "identifier",
            "domain": "Customer",
            "unit": "none",
            "scale": "categorical",
            "data_type": "string",
            "value_direction": "not applicable",
            "expected_pattern": "",
            "drift_sensitivity": "low",
        },
        "order_id": {
            "business_meaning": "Unique order transaction identifier",
            "role": "identifier",
            "domain": "Sales",
            "unit": "none",
            "scale": "categorical",
            "data_type": "string",
            "value_direction": "not applicable",
            "expected_pattern": "",
            "drift_sensitivity": "low",
        },
        "sales_amount": {
            "business_meaning": "Final sales revenue after applying discounts",
            "role": "measure",
            "domain": "Sales",
            "unit": "LKR",
            "scale": "currency",
            "data_type": "decimal",
            "value_direction": "higher means more revenue",
            "expected_pattern": "",
            "drift_sensitivity": "high",
        },
        "quantity": {
            "business_meaning": "Number of products sold in the order",
            "role": "measure",
            "domain": "Sales",
            "unit": "count",
            "scale": "integer",
            "data_type": "integer",
            "value_direction": "higher means more sold items",
            "expected_pattern": "",
            "drift_sensitivity": "high",
        },
        "discount_amount": {
            "business_meaning": "Discount value applied to the order",
            "role": "measure",
            "domain": "Sales",
            "unit": "LKR",
            "scale": "currency",
            "data_type": "decimal",
            "value_direction": "higher means greater discount",
            "expected_pattern": "",
            "drift_sensitivity": "medium",
        },
        "order_date": {
            "business_meaning": "Date when the customer order was placed",
            "role": "date",
            "domain": "Sales",
            "unit": "date",
            "scale": "date",
            "data_type": "date",
            "value_direction": "newer date means more recent order",
            "expected_pattern": "",
            "drift_sensitivity": "medium",
        },
    }
