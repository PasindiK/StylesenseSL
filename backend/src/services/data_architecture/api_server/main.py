"""
FastAPI Server for Lakehouse Dashboard
Provides REST endpoints to serve backend data to the frontend
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import os
import glob
import csv
import importlib
import sys
import logging
import runpy
import io
import contextlib
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# Setup logging
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Lakehouse API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
METADATA_DIR = os.path.join(BASE_DIR, "pipeline", "metadata")
DRIFT_EVENTS_DIR = os.path.join(METADATA_DIR, "drift_events")
DRIFT_ACTIONS_DIR = os.path.join(METADATA_DIR, "drift_actions")
DQ_RESULTS_DIR = os.path.join(METADATA_DIR, "dq_results")
QUARANTINE_DIR = os.path.join(BASE_DIR, "medallions", "bronze", "quarantine")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
GOLD_DIR = os.path.join(BASE_DIR, "medallions", "gold")
DATA_DIR = os.path.join(BASE_DIR, "data")
BRONZE_RAW_DIR = os.path.join(BASE_DIR, "medallions", "bronze", "raw")
SILVER_CLEANED_DIR = os.path.join(BASE_DIR, "medallions", "silver", "cleaned")
SILVER_ENRICHED_DIR = os.path.join(BASE_DIR, "medallions", "silver", "enriched")
GOLD_CURATED_DIR = os.path.join(BASE_DIR, "medallions", "gold", "curated")
CATEGORIZATION_CONFIG_PATH = os.path.join(BASE_DIR, "pipeline", "configs", "data_categorization.yaml")
GOLD_ML_READY_DIR = os.path.join(BASE_DIR, "medallions", "gold", "ml_ready")
GOLD_STAKEHOLDER_VIEWS_DIR = os.path.join(BASE_DIR, "medallions", "gold", "stakeholder_views")
AUDIT_LOG_JSONL_PATH = os.path.join(METADATA_DIR, "audit_logs", "audit_log.jsonl")


# Lightweight in-memory TTL cache for expensive aggregations.
_METRICS_CACHE: Dict[str, Dict[str, Any]] = {}
_LAKEHOUSE_METRICS_SERVICE: Optional[Any] = None


def _get_lakehouse_metrics_service() -> Any:
    """Lazily construct service that computes lakehouse metrics from Azure/local files."""
    global _LAKEHOUSE_METRICS_SERVICE

    if _LAKEHOUSE_METRICS_SERVICE is not None:
        return _LAKEHOUSE_METRICS_SERVICE

    services_path = os.path.join(BASE_DIR, "services")
    if services_path not in sys.path:
        sys.path.insert(0, services_path)

    module = importlib.import_module("lakehouse_metrics_service")
    service_cls = getattr(module, "LakehouseMetricsService")
    _LAKEHOUSE_METRICS_SERVICE = service_cls(BASE_DIR, connection_string=get_azure_connection_string())
    return _LAKEHOUSE_METRICS_SERVICE


# Pydantic models for request bodies
class ApproveRejectRequest(BaseModel):
    table: str
    event_id: str


class TierAssignmentRequest(BaseModel):
    tier: str  # "hot", "warm", "cold", "archive"
    datasets: List[str]
    season: Optional[str] = None
    auto_tiering_enabled: Optional[bool] = True


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load a JSON file safely"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def load_drift_events(limit: int = None) -> List[Dict[str, Any]]:
    """Load drift events from metadata/drift_events/, deduplicated by table (latest only)"""
    events = []
    pattern = os.path.join(DRIFT_EVENTS_DIR, "*.json")
    
    # Load all events
    all_events = []
    for filepath in sorted(glob.glob(pattern), reverse=True):
        data = load_json_file(filepath)
        if data:
            data["file"] = os.path.basename(filepath)
            all_events.append(data)
    
    # Deduplicate by table - keep only the latest event per table
    seen_tables = set()
    for evt in all_events:
        table = evt.get("table")
        if table and table not in seen_tables:
            events.append(evt)
            seen_tables.add(table)
    
    if limit:
        events = events[:limit]
    
    return events


def load_drift_actions(limit: int = None) -> List[Dict[str, Any]]:
    """Load drift actions from metadata/drift_actions/"""
    actions = []
    pattern = os.path.join(DRIFT_ACTIONS_DIR, "*.json")
    
    for filepath in sorted(glob.glob(pattern), reverse=True):
        data = load_json_file(filepath)
        if data:
            data["file"] = os.path.basename(filepath)
            actions.append(data)
    
    if limit:
        actions = actions[:limit]
    
    return actions


def _parse_iso_timestamp(value: str) -> Optional[datetime]:
    """Parse ISO timestamp safely and normalize to naive UTC datetime"""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _estimate_file_rows(filepath: str) -> int:
    """Estimate row count for CSV/Parquet file"""
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return 0

    try:
        if filepath.endswith(".csv"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as file_handle:
                total_lines = sum(1 for _ in file_handle)
            return max(0, total_lines - 1)  # subtract header

        if filepath.endswith(".parquet"):
            pq = importlib.import_module("pyarrow.parquet")
            parquet_file = pq.ParquetFile(filepath)
            return parquet_file.metadata.num_rows or 0
    except Exception:
        return 0

    return 0


def _calculate_average_resolution_hours(drift_events: List[Dict[str, Any]]) -> float:
    """Calculate average resolution time from event timestamp to approved/rejected timestamp"""
    durations = []

    for event in drift_events:
        start_time = _parse_iso_timestamp(event.get("timestamp", ""))
        end_time = _parse_iso_timestamp(event.get("approved_at") or event.get("rejected_at"))

        if start_time and end_time and end_time >= start_time:
            duration_hours = (end_time - start_time).total_seconds() / 3600.0
            durations.append(duration_hours)

    if not durations:
        return 0.0

    return round(sum(durations) / len(durations), 2)


def _calculate_data_volume_tb(paths: List[str]) -> float:
    """Calculate total data volume across directories (TB)"""
    total_bytes = 0

    for path in paths:
        if not os.path.exists(path):
            continue

        for root, _, files in os.walk(path):
            for filename in files:
                filepath = os.path.join(root, filename)
                if os.path.isfile(filepath):
                    try:
                        total_bytes += os.path.getsize(filepath)
                    except OSError:
                        continue

    return round(total_bytes / (1024 ** 4), 4)


def _calculate_ingestion_throughput_records_per_sec(ingestion_dir: str, sample_size: int = 8) -> float:
    """Estimate ingestion throughput from latest ingestion batch files"""
    if not os.path.exists(ingestion_dir):
        return 0.0

    candidate_files = []
    for filename in os.listdir(ingestion_dir):
        if filename.startswith("batch_") and filename.endswith((".csv", ".parquet")):
            filepath = os.path.join(ingestion_dir, filename)
            if os.path.isfile(filepath):
                candidate_files.append(filepath)

    if not candidate_files:
        return 0.0

    latest_files = sorted(candidate_files, key=os.path.getmtime, reverse=True)[:sample_size]
    total_rows = 0
    modification_times = []

    for filepath in latest_files:
        total_rows += _estimate_file_rows(filepath)
        try:
            modification_times.append(os.path.getmtime(filepath))
        except OSError:
            continue

    if total_rows <= 0:
        return 0.0

    # Avoid unrealistically tiny windows from nearly-identical timestamps
    if len(modification_times) > 1:
        window_seconds = max(60.0, max(modification_times) - min(modification_times))
    else:
        window_seconds = 60.0

    return round(total_rows / window_seconds, 2)


def _load_latest_dq_report() -> Dict[str, Any]:
    """Load latest DQ report"""
    pattern = os.path.join(REPORTS_DIR, "dq_report_*.json")
    report_files = sorted(glob.glob(pattern), reverse=True)
    if not report_files:
        return {}

    return load_json_file(report_files[0])


def _load_data_categorization_config() -> Dict[str, Any]:
    """Load governance configuration used by the dashboard."""
    if not os.path.exists(CATEGORIZATION_CONFIG_PATH):
        return {}

    try:
        yaml_module = importlib.import_module("yaml")
        with open(CATEGORIZATION_CONFIG_PATH, "r", encoding="utf-8") as file_handle:
            return yaml_module.safe_load(file_handle) or {}
    except Exception:
        return {}


def _flatten_dq_entries(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten layer-based DQ report payload into a single entry list."""
    entries: List[Dict[str, Any]] = []
    layers = report.get("layers", {}) if isinstance(report, dict) else {}

    if not isinstance(layers, dict):
        return entries

    for layer_entries in layers.values():
        if not isinstance(layer_entries, list):
            continue
        for item in layer_entries:
            if isinstance(item, dict):
                entries.append(item)

    return entries


def _pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "0%"
    return f"{round((part / whole) * 100)}%"


def _risk_to_score(risk_level: str) -> float:
    level = (risk_level or "").strip().lower()
    if level == "high":
        return 3.0
    if level == "medium":
        return 2.0
    return 1.0


def build_feature_importance_from_events(drift_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build explainability payload from actual drift event content."""
    grouped: Dict[str, Dict[str, Any]] = {}

    for evt in drift_events:
        action_name = str(evt.get("decision") or "UNKNOWN").strip().upper() or "UNKNOWN"
        diff = evt.get("diff", {}) if isinstance(evt.get("diff", {}), dict) else {}

        feature_vector = {
            "new_columns_count": float(len(diff.get("new_columns", []))),
            "missing_columns_count": float(len(diff.get("missing_columns", []))),
            "dtype_changes_count": float(len(diff.get("dtype_changes", []))),
            "renames_count": float(len(diff.get("renames", []))),
            "risk_score": _risk_to_score(str(evt.get("risk_level", "low"))),
        }

        if action_name not in grouped:
            grouped[action_name] = {
                "count": 0,
                "sums": {key: 0.0 for key in feature_vector.keys()},
            }

        grouped[action_name]["count"] += 1
        for key, value in feature_vector.items():
            grouped[action_name]["sums"][key] += value

    explainability: List[Dict[str, Any]] = []
    for action_name, stats in sorted(grouped.items(), key=lambda item: item[1]["count"], reverse=True):
        count = max(1, int(stats["count"]))
        averages = {
            key: (value / count)
            for key, value in stats["sums"].items()
        }
        magnitude = sum(max(val, 0.0) for val in averages.values())
        if magnitude <= 0:
            magnitude = 1.0

        features = [
            {
                "name": key,
                "weight": round(max(val, 0.0) / magnitude, 3),
            }
            for key, val in sorted(averages.items(), key=lambda item: item[1], reverse=True)
        ]

        explainability.append({
            "action": action_name,
            "features": features,
        })

    return explainability


def build_governance_snapshot() -> Dict[str, Any]:
    """Build governance page payload from config and latest DQ report."""
    config = _load_data_categorization_config()
    dq_report = _load_latest_dq_report()
    dq_entries = _flatten_dq_entries(dq_report)

    stakeholder_access = config.get("stakeholder_access", {}) if isinstance(config, dict) else {}
    access_validation = config.get("access_validation", {}) if isinstance(config, dict) else {}
    view_generation = config.get("view_generation", {}) if isinstance(config, dict) else {}
    data_categories = config.get("data_categories", {}) if isinstance(config, dict) else {}
    geographic_regions = config.get("geographic_regions", {}) if isinstance(config, dict) else {}
    compliance_cfg = config.get("compliance", {}) if isinstance(config, dict) else {}

    approval_levels = access_validation.get("approval_levels", {}) if isinstance(access_validation, dict) else {}
    pii_columns = access_validation.get("pii_columns", []) if isinstance(access_validation, dict) else []
    pii_handling = access_validation.get("pii_handling", {}) if isinstance(access_validation, dict) else {}
    audit_all_access = bool(access_validation.get("audit_all_access", False)) if isinstance(access_validation, dict) else False

    view_count = 0
    for stakeholder_view in view_generation.values() if isinstance(view_generation, dict) else []:
        if isinstance(stakeholder_view, dict):
            view_count += len(stakeholder_view.get("views", []))

    total_datasets = len(dq_entries)
    schema_passed = sum(1 for entry in dq_entries if int(entry.get("column_count", 0)) > 0)
    completeness_passed = sum(1 for entry in dq_entries if float(entry.get("null_ratio", 1.0)) <= 0.05)
    duplicates_passed = sum(1 for entry in dq_entries if int(entry.get("duplicate_count", 1)) == 0)
    quality_score_passed = sum(1 for entry in dq_entries if float(entry.get("quality_score", 0.0)) >= 95.0)

    provinces = geographic_regions.get("provinces", []) if isinstance(geographic_regions, dict) else []
    retention_policies = compliance_cfg.get("retention_policies", {}) if isinstance(compliance_cfg, dict) else {}
    data_residency = str(compliance_cfg.get("data_residency", "Unknown")) if isinstance(compliance_cfg, dict) else "Unknown"
    privacy_policy_version = str(compliance_cfg.get("privacy_policy_version", "Unknown")) if isinstance(compliance_cfg, dict) else "Unknown"

    policies = [
        {
            "id": "POL001",
            "name": "Stakeholder Access Profiles",
            "status": "active" if len(stakeholder_access) > 0 else "review",
            "description": f"{len(stakeholder_access)} access profiles configured for governed data products",
            "affected_datasets": len(data_categories),
        },
        {
            "id": "POL002",
            "name": "Approval Workflow Rules",
            "status": "active" if len(approval_levels) > 0 else "review",
            "description": f"{len(approval_levels)} approval levels defined for privileged access",
            "affected_datasets": len(data_categories),
        },
        {
            "id": "POL003",
            "name": "PII Protection Controls",
            "status": "active" if len(pii_columns) > 0 else "review",
            "description": f"{len(pii_columns)} sensitive columns tracked for protection and masking",
            "affected_datasets": len(data_categories),
        },
        {
            "id": "POL004",
            "name": "Governed View Generation",
            "status": "active" if view_count > 0 else "review",
            "description": f"{view_count} stakeholder-facing governed views configured",
            "affected_datasets": len(data_categories),
        },
    ]

    quality_rules = [
        {
            "id": "QR001",
            "name": "Schema Validation",
            "description": "Column-level schema checks across silver and gold datasets",
            "datasets": total_datasets,
            "passed": schema_passed,
            "failed": max(0, total_datasets - schema_passed),
            "coverage": _pct(schema_passed, total_datasets),
        },
        {
            "id": "QR002",
            "name": "Null Ratio Control",
            "description": "Dataset null ratio threshold monitoring (<= 5%)",
            "datasets": total_datasets,
            "passed": completeness_passed,
            "failed": max(0, total_datasets - completeness_passed),
            "coverage": _pct(completeness_passed, total_datasets),
        },
        {
            "id": "QR003",
            "name": "Duplicate Detection",
            "description": "Duplicate record checks from latest DQ execution",
            "datasets": total_datasets,
            "passed": duplicates_passed,
            "failed": max(0, total_datasets - duplicates_passed),
            "coverage": _pct(duplicates_passed, total_datasets),
        },
        {
            "id": "QR004",
            "name": "Quality Score Gate",
            "description": "Datasets meeting quality score target (>= 95)",
            "datasets": total_datasets,
            "passed": quality_score_passed,
            "failed": max(0, total_datasets - quality_score_passed),
            "coverage": _pct(quality_score_passed, total_datasets),
        },
    ]

    compliance = [
        {
            "standard": "Data Residency",
            "status": "compliant" if data_residency.lower() == "sri lanka" else "review",
            "score": data_residency,
            "audits": len(provinces),
        },
        {
            "standard": "Access Auditing",
            "status": "compliant" if audit_all_access else "warning",
            "score": "Enabled" if audit_all_access else "Disabled",
            "audits": len(approval_levels),
        },
        {
            "standard": "PII Handling",
            "status": "compliant" if len(pii_handling) > 0 else "review",
            "score": f"{len(pii_handling)} roles",
            "audits": len(pii_columns),
        },
        {
            "standard": "Retention Policies",
            "status": "compliant" if len(retention_policies) > 0 else "review",
            "score": f"v{privacy_policy_version}",
            "audits": len(retention_policies),
        },
    ]

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "config_and_dq_report",
        "policies": policies,
        "quality_rules": quality_rules,
        "compliance": compliance,
    }


def _calculate_quality_score_pct() -> float:
    """Calculate average quality score from latest DQ report"""
    report = _load_latest_dq_report()
    layers = report.get("layers", {}) if isinstance(report, dict) else {}
    scores = []

    for layer_entries in layers.values():
        if not isinstance(layer_entries, list):
            continue
        for item in layer_entries:
            score = item.get("quality_score")
            if isinstance(score, (int, float)):
                scores.append(float(score))

    if not scores:
        return 0.0

    return round(sum(scores) / len(scores), 2)


def _count_governance_rules() -> int:
    """Count governance rules from data categorization config"""
    config = _load_data_categorization_config()
    if not config:
        return 0

    stakeholder_access = config.get("stakeholder_access", {})
    access_validation = config.get("access_validation", {})
    view_generation = config.get("view_generation", {})
    data_categories = config.get("data_categories", {})

    approval_levels = access_validation.get("approval_levels", {})
    pii_columns = access_validation.get("pii_columns", [])

    view_count = 0
    for stakeholder_view in view_generation.values():
        if isinstance(stakeholder_view, dict):
            view_count += len(stakeholder_view.get("views", []))

    return (
        len(stakeholder_access)
        + len(approval_levels)
        + len(pii_columns)
        + len(data_categories)
        + view_count
    )


def _count_active_pipeline_layers() -> int:
    """Count active data pipeline layers with at least one dataset"""
    layer_paths = [
        DATA_DIR,
        BRONZE_RAW_DIR,
        SILVER_CLEANED_DIR,
        SILVER_ENRICHED_DIR,
        GOLD_CURATED_DIR,
    ]

    active_layers = 0
    for layer_path in layer_paths:
        if not os.path.exists(layer_path):
            continue

        has_data = any(
            filename.endswith((".csv", ".parquet", ".json"))
            for filename in os.listdir(layer_path)
        )
        if has_data:
            active_layers += 1

    return active_layers


def build_extended_live_metrics(live_metrics: Dict[str, Any], drift_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build additional dashboard metrics from real backend data sources"""
    total_drifts = live_metrics.get("total_drifts", 0)
    auto_resolved = live_metrics.get("auto_resolved", 0)
    pending_approvals = live_metrics.get("pending_approvals", 0)
    quarantined = live_metrics.get("quarantined", 0)

    automation_rate_pct = round((auto_resolved / total_drifts) * 100, 2) if total_drifts > 0 else 0.0
    success_rate_pct = round(((total_drifts - quarantined) / total_drifts) * 100, 2) if total_drifts > 0 else 100.0

    return {
        "automation_rate_pct": automation_rate_pct,
        "success_rate_pct": success_rate_pct,
        "avg_resolution_hours": _calculate_average_resolution_hours(drift_events),
        "governance_rules_count": _count_governance_rules(),
        "throughput_records_per_sec": _calculate_ingestion_throughput_records_per_sec(BRONZE_RAW_DIR),
        "active_pipelines": _count_active_pipeline_layers(),
        "data_volume_tb": _calculate_data_volume_tb([
            DATA_DIR,
            BRONZE_RAW_DIR,
            SILVER_CLEANED_DIR,
            SILVER_ENRICHED_DIR,
            GOLD_CURATED_DIR,
        ]),
        "quality_score_pct": _calculate_quality_score_pct(),
    }


def calculate_live_metrics(drift_events: List[Dict], drift_actions: List[Dict]) -> Dict[str, Any]:
    """
    Calculate live metrics from drift events and actions
    
    Rules:
    - auto_resolved: Only events with AUTO_* decision AND not in quarantine AND not requiring approval
    - pending_approvals: Events with REQUIRES_APPROVAL or QUARANTINED decision that haven't been approved/rejected
    - quarantined: Actual files in quarantine directory
    - total_drifts: All drift events
    """
    # Get list of quarantined table names from actual files in quarantine folder
    quarantined_tables = set()
    quarantined = 0
    if os.path.exists(QUARANTINE_DIR):
        for date_folder in os.listdir(QUARANTINE_DIR):
            date_path = os.path.join(QUARANTINE_DIR, date_folder)
            if os.path.isdir(date_path):
                for filename in os.listdir(date_path):
                    if filename.endswith('.csv'):
                        quarantined += 1
                        table_name = filename.replace('_raw.csv', '').replace('.csv', '')
                        quarantined_tables.add(table_name)
    
    # Count truly auto-resolved:
    # - Has AUTO_ decision (AUTO_ACCEPT, AUTO_CAST, etc)
    # - NOT in quarantine
    # - NOT requiring approval that's still pending
    auto_resolved = sum(
        1 for evt in drift_events 
        if ("AUTO_" in evt.get("decision", "").upper()
            and evt.get("table", "") not in quarantined_tables
            and not (evt.get("requires_approval", False) and not evt.get("approved", False)))
    )
    
    # Count pending approvals:
    # - Has REQUIRES_APPROVAL decision AND not approved/rejected
    # - OR has QUARANTINED decision AND not approved/rejected
    # - OR is in quarantine folder
    pending_approvals = sum(
        1 for evt in drift_events 
        if ((evt.get("requires_approval", False) and not evt.get("approved", False) and not evt.get("rejected", False))
            or ("QUARANTINED" in evt.get("decision", "").upper() and not evt.get("approved", False) and not evt.get("rejected", False)))
    )
    
    # Total drifts = all unique drift events
    total_drifts = len(drift_events)
    
    pipeline_status = "Running" if pending_approvals == 0 else "Paused"
    
    return {
        "total_drifts": total_drifts,
        "auto_resolved": auto_resolved,
        "pending_approvals": pending_approvals,
        "quarantined": quarantined,
        "pipeline_status": pipeline_status
    }


def load_dataset_previews() -> Dict[str, Any]:
    """Load CSV previews from various layers"""
    import csv
    
    previews = {}
    
    # Define layers and their paths
    layers = {
        "data": os.path.join(BASE_DIR, "data"),
        "bronze": os.path.join(BASE_DIR, "medallions", "bronze", "raw"),
        "silver_cleaned": os.path.join(BASE_DIR, "medallions", "silver", "cleaned"),
        "silver_enriched": os.path.join(BASE_DIR, "medallions", "silver", "enriched"),
        "gold": os.path.join(BASE_DIR, "medallions", "gold", "curated")
    }
    
    for layer_name, layer_path in layers.items():
        if not os.path.exists(layer_path):
            continue
            
        for filename in os.listdir(layer_path):
            if not filename.endswith('.csv'):
                continue
                
            filepath = os.path.join(layer_path, filename)
            dataset_key = f"{layer_name}/{filename}"
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    columns = reader.fieldnames or []
                    preview = []
                    rows_total = 0
                    
                    for i, row in enumerate(reader):
                        if i < 10:  # First 10 rows
                            preview.append(row)
                        rows_total += 1
                        if i >= 100:  # Don't read entire file
                            break
                    
                    previews[dataset_key] = {
                        "layer": layer_name,
                        "file": filename,
                        "rows_total": rows_total,
                        "columns": columns,
                        "preview": preview
                    }
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
    
    return previews


def get_actual_datasets_by_layer() -> Dict[str, List[str]]:
    """Scan filesystem and return actual datasets grouped by layer"""
    layers = {
        "Raw Data": os.path.join(BASE_DIR, "data"),
        "Bronze": os.path.join(BASE_DIR, "medallions", "bronze", "raw"),
        "Silver (Cleaned)": os.path.join(BASE_DIR, "medallions", "silver", "cleaned"),
        "Silver (Enriched)": os.path.join(BASE_DIR, "medallions", "silver", "enriched"),
        "Gold": os.path.join(BASE_DIR, "medallions", "gold", "curated")
    }
    
    result = {}
    
    for layer_name, layer_path in layers.items():
        datasets = []
        if os.path.exists(layer_path):
            for filename in os.listdir(layer_path):
                if filename.endswith('.csv'):
                    # Remove extensions and format name
                    dataset_name = filename.replace('_dataset.csv', '').replace('_raw.csv', '').replace('.csv', '')
                    if dataset_name:  # Only add non-empty names
                        datasets.append(dataset_name)
        result[layer_name] = sorted(datasets)
    
    return result


def load_quarantine_details() -> List[Dict[str, Any]]:
    """Load quarantine file details - returns unique datasets with latest date only"""
    import csv
    
    # Dictionary to track latest quarantine for each dataset
    quarantine_dict = {}
    
    if not os.path.exists(QUARANTINE_DIR):
        return []
    
    for date_folder in sorted(os.listdir(QUARANTINE_DIR), reverse=True):
        date_path = os.path.join(QUARANTINE_DIR, date_folder)
        if not os.path.isdir(date_path):
            continue
        
        for filename in os.listdir(date_path):
            if not filename.endswith('.csv'):
                continue
            
            filepath = os.path.join(date_path, filename)
            dataset_name = filename.replace('_raw.csv', '').replace('.csv', '')
            
            # Only add if we haven't seen this dataset yet (we're iterating newest first)
            if dataset_name in quarantine_dict:
                continue
            
            # Try to read CSV preview
            columns = []
            preview = []
            rows_preview = 0
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    columns = reader.fieldnames or []
                    for i, row in enumerate(reader):
                        if i < 5:  # First 5 rows
                            preview.append(row)
                        rows_preview += 1
                        if i >= 100:  # Don't read entire file
                            break
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                columns = []
                preview = []
                rows_preview = 0
            
            quarantine_dict[dataset_name] = {
                "dataset": dataset_name,
                "filename": filename,
                "quarantine_date": date_folder,
                "quarantine_path": filepath,
                "status": "quarantined",
                "reason": ["Schema drift detected", "Pending review"],
                "rows_preview": rows_preview,
                "columns": columns,
                "preview": preview
            }
    
    return list(quarantine_dict.values())


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get('/api/health')
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "lakehouse-api"
    }


@app.get('/api/dashboard-data')
async def get_dashboard_data():
    """
    Main endpoint: Returns complete dashboard data
    GET /api/dashboard-data
    """
    try:
        # Load all data sources
        drift_events = load_drift_events(limit=20)
        drift_actions = load_drift_actions(limit=20)
        quarantine_details = load_quarantine_details()
        
        # Build pending approvals list - include items requiring approval OR quarantined datasets
        pending_approvals = []
        
        # Add drift events that need approval (check both requires_approval field and decision field)
        for evt in drift_events:
            decision = evt.get("decision", "").upper()
            needs_approval = (evt.get("requires_approval", False) or 
                            "REQUIRES" in decision or 
                            "QUARANTINED" in decision)
            is_not_resolved = not evt.get("approved", False) and not evt.get("rejected", False)
            
            if needs_approval and is_not_resolved:
                # Add counts field from diff if not present
                if "counts" not in evt and "diff" in evt:
                    diff = evt.get("diff", {})
                    evt["counts"] = {
                        "new": len(diff.get("new_columns", [])),
                        "missing": len(diff.get("missing_columns", [])),
                        "dtype": len(diff.get("dtype_changes", [])),
                        "renames": len(diff.get("renames", []))
                    }
                # Set risk level if not present
                if "risk_level" not in evt:
                    counts = evt.get("counts", {})
                    total_changes = sum([counts.get("new", 0), counts.get("missing", 0), 
                                       counts.get("dtype", 0), counts.get("renames", 0)])
                    if total_changes > 10 or counts.get("missing", 0) > 0 or "QUARANTINED" in decision:
                        evt["risk_level"] = "high"
                    elif total_changes > 5:
                        evt["risk_level"] = "medium"
                    else:
                        evt["risk_level"] = "low"
                
                pending_approvals.append(evt)
        
        # Add quarantined datasets as pending approvals (they need review)
        for quarantine_item in quarantine_details:
            # Create a drift event structure for quarantined items
            pending_approvals.append({
                "table": quarantine_item["dataset"],
                "file": f"quarantine_{quarantine_item['dataset']}_{quarantine_item['quarantine_date']}.json",
                "timestamp": quarantine_item["quarantine_date"],
                "decision": "QUARANTINED",
                "requires_approval": True,
                "risk_level": "high",
                "source_file": quarantine_item["filename"],
                "diff": {
                    "new_columns": [],
                    "missing_columns": [],
                    "dtype_changes": []
                },
                "counts": {
                    "new": 0,
                    "missing": 0,
                    "dtype": 0
                }
            })
        
        # Calculate metrics AFTER building pending_approvals list
        live_metrics = calculate_live_metrics(drift_events, drift_actions)
        # Override with actual counts
        live_metrics["pending_approvals"] = len(pending_approvals)
        live_metrics["quarantined"] = len(quarantine_details)  # Use unique count
        live_metrics["pipeline_status"] = "Paused" if len(pending_approvals) > 0 else "Running"
        live_metrics.update(build_extended_live_metrics(live_metrics, drift_events))
        
        # Build decisions timeline from drift events (since drift_actions might be empty)
        decisions_timeline = []
        for evt in drift_events:
            approval_status = "Auto"
            if evt.get("approved"):
                approval_status = "Approved"
            elif evt.get("rejected"):
                approval_status = "Rejected"
            elif evt.get("requires_approval"):
                approval_status = "Pending"
            
            decisions_timeline.append({
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "drift_type": "schema",
                "action": evt.get("decision", ""),
                "approval_status": approval_status,
                "policy_confidence": evt.get("confidence", 0.85),
                "counts": {
                    "new": len(evt.get("diff", {}).get("new_columns", [])),
                    "missing": len(evt.get("diff", {}).get("missing_columns", [])),
                    "dtype": len(evt.get("diff", {}).get("dtype_changes", [])),
                    "renames": len(evt.get("diff", {}).get("renames", []))
                },
                "risk_level": evt.get("risk_level", "low")
            })
        
        # Build detailed metrics lists
        total_drifts_list = []
        auto_resolved_list = []
        pending_approvals_list = []
        
        for evt in drift_events:
            # Calculate counts from diff structure
            diff = evt.get("diff", {})
            counts = {
                "new": len(diff.get("new_columns", [])),
                "missing": len(diff.get("missing_columns", [])),
                "dtype": len(diff.get("dtype_changes", [])),
                "renames": len(diff.get("renames", []))
            }
            
            item = {
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "drift_type": "schema",
                "action": evt.get("decision", ""),
                "approval_status": "Pending" if evt.get("requires_approval") and not evt.get("approved") else "Auto",
                "policy_confidence": evt.get("confidence", 0.85),
                "counts": counts,
                "risk_level": evt.get("risk_level", "low"),
                "file": evt.get("file", "")
            }
            
            total_drifts_list.append(item)
            
            if evt.get("requires_approval", False) and not evt.get("approved", False):
                pending_approvals_list.append(item)
            else:
                auto_resolved_list.append(item)
        
        # Build notifications
        notifications = []
        for evt in pending_approvals:
            notifications.append({
                "timestamp": evt.get("timestamp", ""),
                "table": evt.get("table", ""),
                "reason": f"Schema drift detected: {evt.get('counts', {}).get('new', 0)} new cols, {evt.get('counts', {}).get('missing', 0)} missing",
                "type": "approval",
                "risk_level": evt.get("risk_level", "medium")
            })
        
        # Build action distribution from drift events
        # automated = AUTO_* decisions not requiring human review
        # human_reviewed = REQUIRES_APPROVAL or decisions that need human input
        action_counts = {}
        quarantined_tables = set()
        if os.path.exists(QUARANTINE_DIR):
            for date_folder in os.listdir(QUARANTINE_DIR):
                date_path = os.path.join(QUARANTINE_DIR, date_folder)
                if os.path.isdir(date_path):
                    for filename in os.listdir(date_path):
                        if filename.endswith('.csv'):
                            table_name = filename.replace('_raw.csv', '').replace('.csv', '')
                            quarantined_tables.add(table_name)
        
        for evt in drift_events:
            action_type = evt.get("decision", "UNKNOWN")
            if action_type not in action_counts:
                action_counts[action_type] = {"count": 0, "automated": 0, "human_reviewed": 0}
            
            action_counts[action_type]["count"] += 1
            
            # Determine if automated or human_reviewed
            is_auto = "AUTO_" in action_type
            is_pending_approval = evt.get("requires_approval", False) and not evt.get("approved", False) and not evt.get("rejected", False)
            is_in_quarantine = evt.get("table", "") in quarantined_tables
            
            if is_auto and not is_pending_approval and not is_in_quarantine:
                action_counts[action_type]["automated"] += 1
            else:
                action_counts[action_type]["human_reviewed"] += 1
        
        action_distribution = [
            {"action": k, "count": v["count"], "automated": v["automated"], "human_reviewed": v["human_reviewed"]}
            for k, v in action_counts.items()
        ]
        
        # Explainability derived from actual drift events
        feature_importance = build_feature_importance_from_events(drift_events)

        # Governance payload from config + latest DQ report
        governance = build_governance_snapshot()
        
        # Architecture status with ACTUAL datasets in each stage
        actual_datasets = get_actual_datasets_by_layer()
        
        architecture = {
            "stages": [
                {
                    "name": layer_name,
                    "status": "active",
                    "datasets": datasets
                }
                for layer_name, datasets in actual_datasets.items()
            ],
            "drift_gate_note": "Schema Drift Gate: Active between Bronze → Silver"
        }
        
        # CSV previews (load from actual files)
        csv_previews = load_dataset_previews()
        
        # Build response
        response = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "live_metrics": live_metrics,
            "detailed_metrics": {
                "total_drifts_list": total_drifts_list,
                "auto_resolved_list": auto_resolved_list,
                "pending_approvals_list": pending_approvals_list,
                "quarantined_list": quarantine_details
            },
            "notifications": notifications,
            "drift_events": drift_events,
            "latest_decision": decisions_timeline[0] if decisions_timeline else None,
            "decisions_timeline": decisions_timeline,
            "action_distribution": action_distribution,
            "feature_importance": feature_importance,
            "governance": governance,
            "architecture": architecture,
            "pending_approvals": pending_approvals,
            "quarantine_details": quarantine_details,
            "csv_previews": csv_previews
        }
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/drift-events')
async def get_drift_events(
    limit: Optional[int] = Query(None, description="Maximum number of events to return"),
    table: Optional[str] = Query(None, description="Filter by table name")
):
    """
    Get drift events with optional filtering
    GET /api/drift-events?limit=10&table=products
    """
    try:
        events = load_drift_events(limit=limit)
        
        # Filter by table if specified
        if table:
            events = [evt for evt in events if evt.get("table") == table]
        
        return {
            "count": len(events),
            "events": events
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/metrics')
async def get_metrics():
    """
    Get live metrics only
    GET /api/metrics
    """
    try:
        drift_events = load_drift_events()
        drift_actions = load_drift_actions()
        metrics = calculate_live_metrics(drift_events, drift_actions)
        metrics.update(build_extended_live_metrics(metrics, drift_events))
        
        return metrics
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/quarantine')
async def get_quarantine():
    """
    Get quarantined files
    GET /api/quarantine
    """
    try:
        quarantine_items = load_quarantine_details()
        
        return {
            "count": len(quarantine_items),
            "quarantined_files": quarantine_items
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/approve-drift')
async def approve_drift(request: ApproveRejectRequest):
    """
    Approve a pending drift event
    POST /api/approve-drift
    Body: {"table": "products", "event_id": "drift_products_20260105_123456.json"}
    """
    try:
        if not request.table or not request.event_id:
            raise HTTPException(status_code=400, detail="Missing table or event_id")
        
        # Find and update the event file
        event_path = os.path.join(DRIFT_EVENTS_DIR, request.event_id)
        
        if not os.path.exists(event_path):
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Load, update, and save
        event_data = load_json_file(event_path)
        event_data["approved"] = True
        event_data["approved_at"] = datetime.utcnow().isoformat() + "Z"
        event_data["approved_by"] = "user"  # Could add authentication
        
        with open(event_path, 'w', encoding='utf-8') as f:
            json.dump(event_data, f, indent=2)
        
        return {
            "status": "approved",
            "table": request.table,
            "event_id": request.event_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _utc_iso_now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _cache_get_or_build(cache_key: str, ttl_seconds: int, builder):
    now_ts = datetime.utcnow().timestamp()
    cached = _METRICS_CACHE.get(cache_key)
    if cached and (now_ts - float(cached.get("ts", 0))) < ttl_seconds:
        return cached.get("value")

    value = builder()
    _METRICS_CACHE[cache_key] = {
        "ts": now_ts,
        "value": value,
    }
    return value


def _invalidate_metrics_cache() -> None:
    _METRICS_CACHE.clear()


def _is_data_file(filename: str) -> bool:
    return filename.lower().endswith((".csv", ".parquet", ".json", ".jsonl"))


def _safe_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    dt_val = value
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)
    return dt_val.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _estimate_rows_from_size(size_bytes: int) -> int:
    # Fallback estimate when row-level parsing is not available.
    if size_bytes <= 0:
        return 0
    return max(1, int(size_bytes / 220))


def _extract_dataset_name(path_or_name: str) -> str:
    name = os.path.basename(path_or_name)
    name = name.replace(".parquet", "").replace(".csv", "").replace(".jsonl", "").replace(".json", "")
    for suffix in ["_raw", "_cleaned", "_enriched", "_curated"]:
        if suffix in name:
            name = name.replace(suffix, "")
    return name


def _layer_local_paths(layer: str) -> List[str]:
    normalized = layer.lower()
    if normalized == "bronze":
        return [BRONZE_RAW_DIR]
    if normalized == "silver":
        return [SILVER_CLEANED_DIR, SILVER_ENRICHED_DIR]
    if normalized == "gold":
        return [GOLD_CURATED_DIR, GOLD_ML_READY_DIR, GOLD_STAKEHOLDER_VIEWS_DIR]
    raise ValueError(f"Unsupported layer: {layer}")


def _derive_local_tier(layer: str, modified_at: datetime) -> str:
    age_days = max(0, int((datetime.now(timezone.utc) - modified_at).total_seconds() // 86400))
    layer_name = layer.lower()

    if layer_name == "bronze":
        if age_days <= 3:
            return "HOT"
        if age_days <= 14:
            return "WARM"
        return "COLD"

    if layer_name == "silver":
        if age_days <= 7:
            return "HOT"
        if age_days <= 60:
            return "WARM"
        return "COLD"

    if age_days <= 30:
        return "HOT"
    if age_days <= 90:
        return "WARM"
    return "COLD"


def _scan_layer_files_local(layer: str) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for root_path in _layer_local_paths(layer):
        if not os.path.exists(root_path):
            continue

        for root, _, names in os.walk(root_path):
            for name in names:
                if not _is_data_file(name):
                    continue
                full_path = os.path.join(root, name)
                try:
                    size_bytes = int(os.path.getsize(full_path))
                    modified_dt = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
                    rows = _estimate_file_rows(full_path)
                    if rows <= 0:
                        rows = _estimate_rows_from_size(size_bytes)
                    relative_path = os.path.relpath(full_path, BASE_DIR).replace("\\", "/")
                    files.append(
                        {
                            "layer": layer,
                            "name": name,
                            "dataset_name": _extract_dataset_name(name),
                            "path": relative_path,
                            "size_bytes": size_bytes,
                            "records": int(rows),
                            "last_modified": _safe_iso(modified_dt),
                            "access_tier": _derive_local_tier(layer, modified_dt),
                            "source": "filesystem",
                        }
                    )
                except Exception:
                    continue

    files.sort(key=lambda item: item.get("last_modified") or "", reverse=True)
    return {
        "layer": layer,
        "source": "filesystem",
        "files": files,
    }


def _scan_layer_files_azure(layer: str, connection_string: str) -> Dict[str, Any]:
    try:
        from azure.storage.blob import BlobServiceClient
    except Exception as exc:
        raise RuntimeError(f"Azure blob dependency unavailable: {exc}")

    service = BlobServiceClient.from_connection_string(connection_string)
    container_client = service.get_container_client(layer.lower())
    files: List[Dict[str, Any]] = []

    for blob in container_client.list_blobs():
        blob_name = str(getattr(blob, "name", ""))
        if not _is_data_file(blob_name):
            continue

        size_bytes = int(getattr(blob, "size", 0) or 0)
        modified_dt = getattr(blob, "last_modified", None)
        if modified_dt is None:
            modified_dt = datetime.now(timezone.utc)
        elif modified_dt.tzinfo is None:
            modified_dt = modified_dt.replace(tzinfo=timezone.utc)

        tier_value = getattr(blob, "blob_tier", None)
        tier_name = str(tier_value.value if hasattr(tier_value, "value") else tier_value or "HOT").upper()
        estimated_rows = _estimate_rows_from_size(size_bytes)

        files.append(
            {
                "layer": layer,
                "name": os.path.basename(blob_name),
                "dataset_name": _extract_dataset_name(blob_name),
                "path": f"{layer}/{blob_name}",
                "size_bytes": size_bytes,
                "records": estimated_rows,
                "last_modified": _safe_iso(modified_dt),
                "access_tier": tier_name,
                "source": "azure_blob",
            }
        )

    files.sort(key=lambda item: item.get("last_modified") or "", reverse=True)
    return {
        "layer": layer,
        "source": "azure_blob",
        "files": files,
    }


def _scan_layer_files(layer: str) -> Dict[str, Any]:
    normalized = layer.lower()
    if normalized not in {"bronze", "silver", "gold"}:
        raise HTTPException(status_code=400, detail=f"Unsupported layer: {layer}")

    conn_str = get_azure_connection_string()
    if conn_str:
        try:
            return _scan_layer_files_azure(normalized, conn_str)
        except Exception as exc:
            logger.warning("Falling back to filesystem scan for %s: %s", normalized, exc)

    return _scan_layer_files_local(normalized)


def _build_layer_stats(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_size = sum(int(item.get("size_bytes", 0) or 0) for item in files)
    total_records = sum(int(item.get("records", 0) or 0) for item in files)

    latest = None
    for item in files:
        dt_val = _parse_dt(item.get("last_modified"))
        if dt_val and (latest is None or dt_val > latest):
            latest = dt_val

    now_utc = datetime.now(timezone.utc)
    records_today = 0
    for item in files:
        dt_val = _parse_dt(item.get("last_modified"))
        if dt_val and dt_val.date() == now_utc.date():
            records_today += int(item.get("records", 0) or 0)

    return {
        "file_count": len(files),
        "size_bytes": total_size,
        "size_gb": round(total_size / (1024 ** 3), 4),
        "records": total_records,
        "records_today": records_today,
        "latest_ingestion": _safe_iso(latest) if latest else None,
    }


def _aggregate_storage_tiers(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tier_totals: Dict[str, int] = defaultdict(int)
    for item in files:
        tier_name = str(item.get("access_tier") or "UNKNOWN").upper()
        if tier_name == "COOL":
            tier_name = "WARM"
        tier_totals[tier_name] += int(item.get("size_bytes", 0) or 0)

    ordered = ["HOT", "WARM", "COLD", "ARCHIVE", "UNKNOWN"]
    return [
        {
            "tier": tier,
            "size_bytes": tier_totals.get(tier, 0),
            "size_gb": round(tier_totals.get(tier, 0) / (1024 ** 3), 4),
        }
        for tier in ordered
        if tier_totals.get(tier, 0) > 0 or tier in {"HOT", "WARM", "COLD"}
    ]


def _build_growth_series(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_date: Dict[str, int] = defaultdict(int)
    for item in files:
        dt_val = _parse_dt(item.get("last_modified"))
        if not dt_val:
            continue
        key = dt_val.date().isoformat()
        by_date[key] += int(item.get("size_bytes", 0) or 0)

    series = []
    cumulative = 0
    for date_key in sorted(by_date.keys()):
        daily = by_date[date_key]
        cumulative += daily
        series.append(
            {
                "date": date_key,
                "daily_size_bytes": daily,
                "daily_size_gb": round(daily / (1024 ** 3), 4),
                "cumulative_size_bytes": cumulative,
                "cumulative_size_gb": round(cumulative / (1024 ** 3), 4),
            }
        )
    return series


def _build_largest_datasets(files: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    ranked = sorted(files, key=lambda item: int(item.get("size_bytes", 0) or 0), reverse=True)
    output = []
    for item in ranked[:top_n]:
        output.append(
            {
                "dataset": item.get("dataset_name"),
                "path": item.get("path"),
                "layer": item.get("layer"),
                "size_bytes": int(item.get("size_bytes", 0) or 0),
                "size_mb": round(int(item.get("size_bytes", 0) or 0) / (1024 ** 2), 3),
                "records": int(item.get("records", 0) or 0),
                "last_modified": item.get("last_modified"),
            }
        )
    return output


def _load_audit_events(limit: int = 1000) -> List[Dict[str, Any]]:
    if not os.path.exists(AUDIT_LOG_JSONL_PATH):
        return []

    events: List[Dict[str, Any]] = []
    try:
        with open(AUDIT_LOG_JSONL_PATH, "r", encoding="utf-8") as file_handle:
            for line in file_handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                    events.append(parsed)
                except Exception:
                    continue
    except Exception:
        return []

    events.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return events[:limit]


def _build_governance_analytics(audit_events: List[Dict[str, Any]], quality_score_pct: float) -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    events_today = 0
    access_requests = 0
    unauthorized = 0
    policy_violations = 0

    hourly: Dict[str, int] = defaultdict(int)
    stakeholder_counts: Dict[str, int] = defaultdict(int)
    regional_counts: Dict[str, int] = defaultdict(int)

    for event in audit_events:
        ts = _parse_dt(event.get("timestamp"))
        if ts and ts.date() == now_utc.date():
            events_today += 1
        if ts:
            hour_key = ts.strftime("%Y-%m-%d %H:00")
            hourly[hour_key] += 1

        event_type = str(event.get("event_type", "")).lower()
        status = str(event.get("status", "")).lower()
        details = event.get("details", {}) if isinstance(event.get("details", {}), dict) else {}

        if event_type == "data_access":
            access_requests += 1

        if "denied" in status or "unauthorized" in status:
            unauthorized += 1
            policy_violations += 1

        if event_type in {"policy_violation", "compliance_violation"}:
            policy_violations += 1

        stakeholder = str(details.get("stakeholder_type") or details.get("stakeholder") or "unknown")
        stakeholder_counts[stakeholder] += 1

        region = str(details.get("region") or details.get("province") or "unknown")
        regional_counts[region] += 1

    governance_snapshot = build_governance_snapshot()
    compliance_items = governance_snapshot.get("compliance", []) if isinstance(governance_snapshot, dict) else []

    retention_status = "compliant"
    access_status = "compliant"
    for item in compliance_items:
        standard = str(item.get("standard", "")).lower()
        status = str(item.get("status", "review")).lower()
        if "retention" in standard:
            retention_status = status
        if "access" in standard:
            access_status = status

    data_quality_status = "compliant" if quality_score_pct >= 95 else "review"

    return {
        "metric_cards": {
            "audit_events_today": events_today,
            "access_requests": access_requests,
            "policy_violations": policy_violations,
            "unauthorized_access_attempts": unauthorized,
        },
        "audit_activity_per_hour": [
            {"hour": key, "count": hourly[key]} for key in sorted(hourly.keys())[-24:]
        ],
        "stakeholder_access": [
            {"stakeholder": key, "count": stakeholder_counts[key]}
            for key in sorted(stakeholder_counts.keys())
        ],
        "regional_access": [
            {"province": key, "count": regional_counts[key]}
            for key in sorted(regional_counts.keys())
        ],
        "compliance_indicators": [
            {"name": "Retention compliance", "status": retention_status},
            {"name": "Access control compliance", "status": access_status},
            {"name": "Data quality compliance", "status": data_quality_status},
        ],
        "audit_events": audit_events[:200],
    }


def _load_feature_importance_from_reports() -> List[Dict[str, Any]]:
    report_path = os.path.join(GOLD_DIR, "ml_decision_engine", "reports", "top_features_per_action.csv")
    if not os.path.exists(report_path):
        return []

    output: List[Dict[str, Any]] = []
    try:
        with open(report_path, "r", encoding="utf-8") as file_handle:
            reader = csv.DictReader(file_handle)
            for row in reader:
                features = []
                for idx in [1, 2, 3]:
                    feature_name = str(row.get(f"feature{idx}", "") or "").strip()
                    feature_value = str(row.get(f"feat{idx}_val", "") or "").strip()
                    if not feature_name:
                        continue
                    try:
                        weight = float(feature_value)
                    except Exception:
                        weight = 0.0
                    features.append({"name": feature_name, "weight": round(weight, 4)})

                output.append(
                    {
                        "action": row.get("action", "unknown"),
                        "count": int(float(row.get("count", 0) or 0)),
                        "features": features,
                    }
                )
    except Exception:
        return []

    return output


def _load_embedding_clusters(limit: int = 180) -> List[Dict[str, Any]]:
    candidates = [
        os.path.join(GOLD_CURATED_DIR, "product_embeddings_gold.parquet"),
        os.path.join(GOLD_ML_READY_DIR, "drift_baseline_features_latest.csv"),
    ]

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            import pandas as pd

            if candidate.endswith(".parquet"):
                df = pd.read_parquet(candidate)
            else:
                df = pd.read_csv(candidate)

            if df.empty:
                continue

            numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
            if len(numeric_cols) < 2:
                continue

            x_col, y_col = numeric_cols[0], numeric_cols[1]
            sample = df[[x_col, y_col]].dropna().head(limit)
            if sample.empty:
                continue

            x_values = sample[x_col].tolist()
            y_values = sample[y_col].tolist()
            median_score = sorted([x + y for x, y in zip(x_values, y_values)])[len(sample) // 2]

            points = []
            for index, (x_val, y_val) in enumerate(zip(x_values, y_values)):
                score = float(x_val) + float(y_val)
                cluster = "high" if score >= median_score else "baseline"
                points.append(
                    {
                        "x": float(x_val),
                        "y": float(y_val),
                        "cluster": cluster,
                        "label": f"point_{index + 1}",
                    }
                )
            return points
        except Exception:
            continue

    return []


def _load_ml_dataset_metrics() -> Dict[str, Any]:
    metrics = {
        "training_dataset_size": 0,
        "feature_count": 0,
        "embedding_vectors_generated": 0,
        "model_accuracy": 0.0,
    }

    baseline_csv = os.path.join(GOLD_ML_READY_DIR, "drift_baseline_features_latest.csv")
    if os.path.exists(baseline_csv):
        try:
            import pandas as pd

            df = pd.read_csv(baseline_csv)
            metrics["training_dataset_size"] = int(len(df))
            metrics["feature_count"] = int(len(df.columns))
        except Exception:
            pass

    embeddings_parquet = os.path.join(GOLD_CURATED_DIR, "product_embeddings_gold.parquet")
    if os.path.exists(embeddings_parquet):
        try:
            import pandas as pd

            embeddings_df = pd.read_parquet(embeddings_parquet)
            metrics["embedding_vectors_generated"] = int(len(embeddings_df))
        except Exception:
            pass

    training_metrics_path = os.path.join(GOLD_DIR, "ml_decision_engine", "models", "training_metrics.json")
    if os.path.exists(training_metrics_path):
        training_metrics = load_json_file(training_metrics_path)
        if isinstance(training_metrics, dict):
            if isinstance(training_metrics.get("model_accuracy"), (int, float)):
                metrics["model_accuracy"] = float(training_metrics["model_accuracy"])
            elif isinstance(training_metrics.get("accuracy"), (int, float)):
                metrics["model_accuracy"] = float(training_metrics["accuracy"])
            else:
                action_counts = training_metrics.get("action_counts", {})
                if isinstance(action_counts, dict) and action_counts:
                    total = sum(int(v) for v in action_counts.values())
                    auto = sum(int(v) for k, v in action_counts.items() if "auto" in str(k).lower())
                    if total > 0:
                        metrics["model_accuracy"] = round((auto / total) * 100, 2)

    return metrics


def _build_recommendation_explanations(feature_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    explanations: List[Dict[str, Any]] = []
    for row in feature_rows[:3]:
        action = str(row.get("action", "recommendation"))
        features = row.get("features", []) if isinstance(row.get("features", []), list) else []
        if not features:
            continue
        top_feature = features[0]
        explanations.append(
            {
                "title": action,
                "reason": f"Primary driver: {top_feature.get('name')} ({round(float(top_feature.get('weight', 0)) * 100, 1)}%).",
                "confidence": round(float(top_feature.get("weight", 0)) * 100, 2),
            }
        )
    return explanations


def _build_ingestion_series(bronze_files: List[Dict[str, Any]], pending_approvals: int) -> Dict[str, Any]:
    per_minute: Dict[str, int] = defaultdict(int)
    per_hour: Dict[str, int] = defaultdict(int)
    per_day: Dict[str, int] = defaultdict(int)

    for item in bronze_files:
        ts = _parse_dt(item.get("last_modified"))
        if not ts:
            continue
        records = int(item.get("records", 0) or 0)
        minute_key = ts.strftime("%Y-%m-%d %H:%M")
        hour_key = ts.strftime("%Y-%m-%d %H:00")
        day_key = ts.strftime("%Y-%m-%d")
        per_minute[minute_key] += records
        per_hour[hour_key] += records
        per_day[day_key] += records

    minute_points = [{"timestamp": key, "records": per_minute[key]} for key in sorted(per_minute.keys())[-120:]]
    hour_points = [{"timestamp": key, "records": per_hour[key]} for key in sorted(per_hour.keys())[-72:]]
    day_points = [{"date": key, "records": per_day[key]} for key in sorted(per_day.keys())[-30:]]

    now_utc = datetime.now(timezone.utc)
    lag_series = []
    for point in minute_points[-60:]:
        ts = _parse_dt(point.get("timestamp"))
        lag_minutes = 0
        if ts:
            lag_minutes = max(0, int((now_utc - ts).total_seconds() // 60))
        lag_series.append({"timestamp": point.get("timestamp"), "lag_minutes": lag_minutes})

    failed_messages = [
        {
            "timestamp": point.get("timestamp"),
            "failed": pending_approvals if idx == len(hour_points) - 1 else 0,
        }
        for idx, point in enumerate(hour_points)
    ]

    return {
        "records_per_minute": minute_points,
        "records_per_hour": hour_points,
        "daily_ingestion_volume": day_points,
        "failed_messages": failed_messages,
        "consumer_lag": lag_series,
    }


def _build_freshness_series(files_by_layer: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    output: List[Dict[str, Any]] = []
    for day_offset in range(13, -1, -1):
        day = (now_utc - timedelta(days=day_offset)).date()
        point: Dict[str, Any] = {"date": day.isoformat()}

        for layer in ["bronze", "silver", "gold"]:
            layer_files = files_by_layer.get(layer, [])
            latest_for_day = None
            for item in layer_files:
                ts = _parse_dt(item.get("last_modified"))
                if ts and ts.date() <= day and (latest_for_day is None or ts > latest_for_day):
                    latest_for_day = ts

            if latest_for_day is None:
                point[f"{layer}_freshness_hours"] = None
                point[f"{layer}_last_update"] = None
            else:
                point[f"{layer}_freshness_hours"] = round((now_utc - latest_for_day).total_seconds() / 3600, 2)
                point[f"{layer}_last_update"] = _safe_iso(latest_for_day)

        output.append(point)

    return output


def _build_pipeline_flow(layer_stats: Dict[str, Dict[str, Any]], pending_alerts: int) -> List[Dict[str, Any]]:
    bronze_records = int(layer_stats.get("bronze", {}).get("records", 0) or 0)
    silver_records = int(layer_stats.get("silver", {}).get("records", 0) or 0)
    gold_records = int(layer_stats.get("gold", {}).get("records", 0) or 0)

    def _safe_success(current: int, prev: int) -> float:
        if prev <= 0:
            return 100.0
        return round(max(0.0, min(100.0, (current / prev) * 100.0)), 2)

    silver_success = _safe_success(silver_records, bronze_records)
    gold_success = _safe_success(gold_records, silver_records)
    kafka_failures = pending_alerts

    return [
        {
            "stage": "Kafka",
            "records_processed": bronze_records,
            "success_rate": round(max(0.0, 100.0 - float(kafka_failures)), 2),
            "failed_records": kafka_failures,
        },
        {
            "stage": "Bronze",
            "records_processed": bronze_records,
            "success_rate": 100.0,
            "failed_records": 0,
        },
        {
            "stage": "Silver",
            "records_processed": silver_records,
            "success_rate": silver_success,
            "failed_records": max(0, bronze_records - silver_records),
        },
        {
            "stage": "Gold",
            "records_processed": gold_records,
            "success_rate": gold_success,
            "failed_records": max(0, silver_records - gold_records),
        },
    ]


def _build_timeline_events(files_by_layer: Dict[str, List[Dict[str, Any]]], drift_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    stage_map = {
        "bronze": "Bronze creation",
        "silver": "Silver cleaning",
        "gold": "Gold creation",
    }

    for layer, entries in files_by_layer.items():
        for item in entries[:20]:
            events.append(
                {
                    "timestamp": item.get("last_modified"),
                    "operation": stage_map.get(layer, layer),
                    "records_processed": int(item.get("records", 0) or 0),
                    "dataset": item.get("dataset_name"),
                }
            )

    for drift in drift_events[:20]:
        events.append(
            {
                "timestamp": drift.get("timestamp"),
                "operation": "Schema drift review",
                "records_processed": int(sum((drift.get("counts") or {}).values())) if isinstance(drift.get("counts"), dict) else 0,
                "dataset": drift.get("table"),
            }
        )

    events = [item for item in events if item.get("timestamp")]
    events.sort(key=lambda item: str(item.get("timestamp")), reverse=True)
    return events[:120]


def _load_drift_events_for_dashboard() -> Dict[str, Any]:
    drift_events = load_drift_events(limit=200)
    pending = []
    approved = 0
    rejected = 0

    for evt in drift_events:
        approved_flag = bool(evt.get("approved", False))
        rejected_flag = bool(evt.get("rejected", False))
        if approved_flag:
            approved += 1
        if rejected_flag:
            rejected += 1

        needs_approval = bool(evt.get("requires_approval", False)) or "QUARANTINED" in str(evt.get("decision", "")).upper()
        if needs_approval and not approved_flag and not rejected_flag:
            if "counts" not in evt and isinstance(evt.get("diff", {}), dict):
                diff = evt.get("diff", {})
                evt["counts"] = {
                    "new": len(diff.get("new_columns", [])),
                    "missing": len(diff.get("missing_columns", [])),
                    "dtype": len(diff.get("dtype_changes", [])),
                    "renames": len(diff.get("renames", [])),
                }
            pending.append(evt)

    return {
        "all": drift_events,
        "pending": pending,
        "approved_count": approved,
        "rejected_count": rejected,
    }


def _build_summary_payload() -> Dict[str, Any]:
    files_by_layer: Dict[str, List[Dict[str, Any]]] = {}
    layer_sources: Dict[str, str] = {}
    layer_stats: Dict[str, Dict[str, Any]] = {}

    for layer in ["bronze", "silver", "gold"]:
        scanned = _scan_layer_files(layer)
        files = scanned.get("files", []) if isinstance(scanned, dict) else []
        files_by_layer[layer] = files
        layer_sources[layer] = str(scanned.get("source", "unknown"))
        layer_stats[layer] = _build_layer_stats(files)

    all_files = files_by_layer["bronze"] + files_by_layer["silver"] + files_by_layer["gold"]
    drift_data = _load_drift_events_for_dashboard()
    drift_events = drift_data["all"]
    pending_approvals = drift_data["pending"]
    quality_score = _calculate_quality_score_pct()
    audit_events = _load_audit_events(limit=2000)

    feature_importance = _load_feature_importance_from_reports()
    if not feature_importance:
        feature_importance = build_feature_importance_from_events(drift_events)

    overview_metrics = {
        "total_records_ingested_today": int(layer_stats["bronze"].get("records_today", 0) or 0),
        "bronze_files_count": int(layer_stats["bronze"].get("file_count", 0) or 0),
        "silver_datasets_count": int(layer_stats["silver"].get("file_count", 0) or 0),
        "gold_tables_count": int(layer_stats["gold"].get("file_count", 0) or 0),
        "active_drift_alerts": len(pending_approvals),
        "data_quality_score": round(float(quality_score), 2),
    }

    storage_tier_usage = _aggregate_storage_tiers(all_files)
    governance_payload = _build_governance_analytics(audit_events, quality_score)
    ingestion_metrics = _build_ingestion_series(files_by_layer["bronze"], len(pending_approvals))

    medallion_payload = {
        "metrics": {
            "bronze_records": int(layer_stats["bronze"].get("records", 0) or 0),
            "silver_records": int(layer_stats["silver"].get("records", 0) or 0),
            "gold_records": int(layer_stats["gold"].get("records", 0) or 0),
        },
        "layer_comparison": [
            {"layer": "Bronze", "records": int(layer_stats["bronze"].get("records", 0) or 0)},
            {"layer": "Silver", "records": int(layer_stats["silver"].get("records", 0) or 0)},
            {"layer": "Gold", "records": int(layer_stats["gold"].get("records", 0) or 0)},
        ],
        "transformation_success_rate": _build_pipeline_flow(layer_stats, len(pending_approvals))[-1]["success_rate"],
        "dataset_explorer": {
            "bronze": files_by_layer["bronze"][:30],
            "silver": files_by_layer["silver"][:30],
            "gold": files_by_layer["gold"][:30],
        },
    }

    storage_payload = {
        "metric_cards": {
            "total_storage_used": round(sum(item.get("size_bytes", 0) for item in all_files) / (1024 ** 3), 4),
            "hot_tier_size": round(sum(item.get("size_bytes", 0) for item in all_files if str(item.get("access_tier", "")).upper() == "HOT") / (1024 ** 3), 4),
            "warm_tier_size": round(sum(item.get("size_bytes", 0) for item in all_files if str(item.get("access_tier", "")).upper() in {"WARM", "COOL"}) / (1024 ** 3), 4),
            "cold_tier_size": round(sum(item.get("size_bytes", 0) for item in all_files if str(item.get("access_tier", "")).upper() in {"COLD", "ARCHIVE"}) / (1024 ** 3), 4),
        },
        "tier_usage": storage_tier_usage,
        "storage_growth_over_time": _build_growth_series(all_files),
        "largest_datasets": _build_largest_datasets(all_files, top_n=10),
        "tier_movement_activity": [
            {
                "date": key,
                "movements": value,
            }
            for key, value in sorted(
                (
                    (hourly_key.split(" ")[0], count)
                    for hourly_key, count in {
                        row.get("hour"): row.get("count")
                        for row in governance_payload.get("audit_activity_per_hour", [])
                        if row.get("hour")
                    }.items()
                ),
                key=lambda item: item[0],
            )
        ],
    }

    return {
        "generated_at": _utc_iso_now(),
        "source": {
            "bronze": layer_sources.get("bronze"),
            "silver": layer_sources.get("silver"),
            "gold": layer_sources.get("gold"),
        },
        "overview": {
            "metrics": overview_metrics,
            "pipeline_flow": _build_pipeline_flow(layer_stats, len(pending_approvals)),
            "freshness": _build_freshness_series(files_by_layer),
            "ingestion_metrics": ingestion_metrics,
            "data_volume_distribution": [
                {"layer": "Bronze", "size_bytes": int(layer_stats["bronze"].get("size_bytes", 0) or 0)},
                {"layer": "Silver", "size_bytes": int(layer_stats["silver"].get("size_bytes", 0) or 0)},
                {"layer": "Gold", "size_bytes": int(layer_stats["gold"].get("size_bytes", 0) or 0)},
            ],
            "storage_tier_usage": storage_tier_usage,
        },
        "governance": governance_payload,
        "explainability": {
            "feature_importance": feature_importance,
            "embedding_clusters": _load_embedding_clusters(),
            "recommendation_explanations": _build_recommendation_explanations(feature_importance),
            "ml_dataset_metrics": _load_ml_dataset_metrics(),
        },
        "actions": {
            "pipeline_status": "Paused" if len(pending_approvals) > 0 else "Running",
            "last_run": _utc_iso_now(),
        },
        "medallion": medallion_payload,
        "approvals": {
            "pending_count": len(pending_approvals),
            "approved_count": drift_data.get("approved_count", 0),
            "rejected_count": drift_data.get("rejected_count", 0),
            "events": pending_approvals,
        },
        "timeline": _build_timeline_events(files_by_layer, drift_events),
        "storage": storage_payload,
    }


def _script_path(script_name: str) -> str:
    return os.path.join(BASE_DIR, "scripts", script_name)


def _run_script(script_name: str, init_globals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    path = _script_path(script_name)
    if not os.path.exists(path):
        return {
            "status": "error",
            "script": script_name,
            "error": f"Script not found: {script_name}",
            "logs": [],
        }

    buffer = io.StringIO()
    old_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            runpy.run_path(path, run_name="__main__", init_globals=(init_globals or {}))
        log_lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        return {
            "status": "success",
            "script": script_name,
            "logs": log_lines[-200:],
        }
    except Exception as exc:
        log_lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        return {
            "status": "error",
            "script": script_name,
            "error": str(exc),
            "logs": log_lines[-200:],
        }
    finally:
        os.chdir(old_cwd)


def _run_bronze_to_silver_jobs() -> Dict[str, Any]:
    raw_files = sorted(glob.glob(os.path.join(BRONZE_RAW_DIR, "*_raw.csv")))
    if not raw_files:
        return {
            "status": "success",
            "processed": 0,
            "results": [],
            "message": "No bronze CSV files found",
        }

    results = []
    for file_path in raw_files:
        table_name = os.path.basename(file_path).replace("_raw.csv", "")
        result = _run_script(
            "s02_bronze_to_silver_cleaned.py",
            {
                "INPUT_FILE": file_path,
                "TABLE_NAME": table_name,
            },
        )
        results.append({
            "table": table_name,
            **result,
        })

    failures = [item for item in results if item.get("status") != "success"]
    return {
        "status": "error" if failures else "success",
        "processed": len(results),
        "failed": len(failures),
        "results": results,
    }


def _run_silver_to_gold_jobs() -> Dict[str, Any]:
    cleaned_files = sorted(glob.glob(os.path.join(SILVER_CLEANED_DIR, "*_cleaned.csv")))
    enrichment_results = []

    for file_path in cleaned_files:
        table_name = os.path.basename(file_path).replace("_cleaned.csv", "")
        enrichment_results.append(
            {
                "table": table_name,
                **_run_script(
                    "s03_silver_to_enriched.py",
                    {
                        "INPUT_FILE": file_path,
                        "TABLE_NAME": table_name,
                    },
                ),
            }
        )

    gold_result = _run_script("s05_silver_to_gold_curated.py")
    failures = [item for item in enrichment_results if item.get("status") != "success"]
    if gold_result.get("status") != "success":
        failures.append(gold_result)

    return {
        "status": "error" if failures else "success",
        "enriched_tables": len(enrichment_results),
        "gold_curation": gold_result,
        "results": enrichment_results,
    }


def _generate_stakeholder_views_job() -> Dict[str, Any]:
    try:
        import sys
        import pandas as pd

        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)

        from pipeline.ingestion.kafka_config import DataCategorizationConfig
        from pipeline.governance.data_categorization import DataCategorizationManager

        source_files = sorted(glob.glob(os.path.join(BRONZE_RAW_DIR, "*.csv")))
        if not source_files:
            source_files = sorted(glob.glob(os.path.join(GOLD_CURATED_DIR, "*.csv")))

        if not source_files:
            return {
                "status": "error",
                "error": "No source CSV files found for stakeholder view generation",
                "view_files": [],
            }

        frames = []
        for file_path in source_files[:4]:
            try:
                frames.append(pd.read_csv(file_path))
            except Exception:
                continue

        if not frames:
            return {
                "status": "error",
                "error": "Unable to read source datasets for view generation",
                "view_files": [],
            }

        combined = pd.concat(frames, ignore_index=True)
        cfg = DataCategorizationConfig.from_yaml()
        manager = DataCategorizationManager(cfg)
        os.makedirs(GOLD_STAKEHOLDER_VIEWS_DIR, exist_ok=True)
        generated = manager.generate_stakeholder_views(combined, GOLD_STAKEHOLDER_VIEWS_DIR)

        output_files = []
        for stakeholder, path in generated.items():
            path_str = str(path)
            output_files.append(
                {
                    "stakeholder": stakeholder,
                    "path": os.path.relpath(path_str, BASE_DIR).replace("\\", "/"),
                    "size_bytes": int(os.path.getsize(path_str)) if os.path.exists(path_str) else 0,
                }
            )

        return {
            "status": "success",
            "view_count": len(output_files),
            "view_files": output_files,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "view_files": [],
        }


@app.get('/api/dashboard/summary')
async def get_dashboard_summary():
    """
    Enterprise dashboard summary built from live medallion + governance data.
    """
    try:
        payload = _cache_get_or_build("dashboard_summary", 45, _build_summary_payload)
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/medallion/{layer}/files')
async def get_medallion_layer_files(layer: str):
    """
    Returns file-level metadata for bronze/silver/gold layers.
    """
    try:
        normalized = layer.lower()
        if normalized not in {"bronze", "silver", "gold"}:
            raise HTTPException(status_code=400, detail="Layer must be one of: bronze, silver, gold")

        payload = _cache_get_or_build(f"medallion_files::{normalized}", 45, lambda: _scan_layer_files(normalized))
        files = payload.get("files", []) if isinstance(payload, dict) else []
        return {
            "layer": normalized,
            "source": payload.get("source", "unknown") if isinstance(payload, dict) else "unknown",
            "count": len(files),
            "files": files,
            "summary": _build_layer_stats(files),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/drift/events')
async def get_drift_events_v2(limit: Optional[int] = Query(100, description="Maximum drift events to return")):
    """
    Drift events endpoint with path contract used by the refactored dashboard.
    """
    try:
        resolved_limit = int(limit or 100)
        payload = _load_drift_events_for_dashboard()
        events = payload.get("all", [])[:resolved_limit]
        return {
            "count": len(events),
            "pending_count": len(payload.get("pending", [])),
            "approved_count": payload.get("approved_count", 0),
            "rejected_count": payload.get("rejected_count", 0),
            "events": events,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/governance/audit-log')
async def get_governance_audit_log(limit: Optional[int] = Query(500, description="Maximum audit events to return")):
    """
    Governance audit log with aggregate compliance/access analytics.
    """
    try:
        events = _load_audit_events(limit=int(limit or 500))
        analytics = _build_governance_analytics(events, _calculate_quality_score_pct())
        return {
            "generated_at": _utc_iso_now(),
            "count": len(events),
            **analytics,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/storage/tier-statistics')
async def get_storage_tier_statistics():
    """
    Storage usage analytics grouped by tiers and dataset growth.
    """
    try:
        summary = _cache_get_or_build("dashboard_summary", 45, _build_summary_payload)
        storage = summary.get("storage", {}) if isinstance(summary, dict) else {}
        return {
            "generated_at": _utc_iso_now(),
            **storage,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/stakeholder/views/{view_type}')
async def get_stakeholder_views(view_type: str):
    """
    Returns generated stakeholder views and file metadata.
    """
    try:
        requested = view_type.strip().lower()
        if not os.path.exists(GOLD_STAKEHOLDER_VIEWS_DIR):
            return {
                "stakeholder_type": requested,
                "count": 0,
                "views": [],
            }

        matches = []
        for root, _, names in os.walk(GOLD_STAKEHOLDER_VIEWS_DIR):
            for name in names:
                if not _is_data_file(name):
                    continue
                full_path = os.path.join(root, name)
                stem = Path(name).stem.lower()
                if requested != "all" and requested not in stem:
                    continue

                size_bytes = int(os.path.getsize(full_path))
                modified = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
                rows = _estimate_file_rows(full_path)
                if rows <= 0:
                    rows = _estimate_rows_from_size(size_bytes)
                matches.append(
                    {
                        "name": name,
                        "path": os.path.relpath(full_path, BASE_DIR).replace("\\", "/"),
                        "size_bytes": size_bytes,
                        "records": int(rows),
                        "last_modified": _safe_iso(modified),
                    }
                )

        matches.sort(key=lambda item: item.get("last_modified") or "", reverse=True)
        return {
            "stakeholder_type": requested,
            "count": len(matches),
            "views": matches,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/bronze-metrics')
async def get_lakehouse_bronze_metrics():
    """Bronze-layer ingestion and storage telemetry from blob metadata."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::bronze_metrics", 45, service.get_bronze_metrics)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/silver-metrics')
async def get_lakehouse_silver_metrics():
    """Silver-layer transformation analytics, timestamps, and success rate."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::silver_metrics", 45, service.get_silver_metrics)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/gold-metrics')
async def get_lakehouse_gold_metrics():
    """Gold-layer analytics for tables, features, and stakeholder view outputs."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::gold_metrics", 45, service.get_gold_metrics)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/storage-analytics')
async def get_lakehouse_storage_analytics():
    """Storage usage grouped by access tier with largest-dataset analysis."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::storage_analytics", 45, service.get_storage_analytics)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/storage-growth')
async def get_lakehouse_storage_growth():
    """Time-series storage growth computed from blob last-modified dates."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::storage_growth", 45, service.get_storage_growth)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/ingestion-metrics')
async def get_lakehouse_ingestion_metrics():
    """Per-minute, per-hour, and per-day ingestion metrics from bronze timestamps."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::ingestion_metrics", 45, service.get_ingestion_metrics)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/data-freshness')
async def get_lakehouse_data_freshness():
    """Freshness status for bronze/silver/gold based on latest update timestamps."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = _cache_get_or_build("lakehouse::data_freshness", 45, service.get_data_freshness)
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/current-season')
async def get_lakehouse_current_season(simulate_season: Optional[str] = Query(None)):
    """Detect current retail season or return a simulated season."""
    try:
        service = _get_lakehouse_metrics_service()
        payload = service.get_current_season(simulate_season=simulate_season)
        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/lakehouse/seasonal-analytics')
async def get_lakehouse_seasonal_analytics(simulate_season: Optional[str] = Query(None)):
    """Season-aware storage distribution and dataset activity analytics."""
    try:
        service = _get_lakehouse_metrics_service()

        if simulate_season:
            payload = service.get_seasonal_storage_analytics(simulate_season=simulate_season)
        else:
            payload = _cache_get_or_build(
                "lakehouse::seasonal_analytics::current",
                45,
                lambda: service.get_seasonal_storage_analytics(simulate_season=None),
            )

        return {
            "generated_at": _utc_iso_now(),
            **payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/api/actions/kafka-ingestion')
async def run_kafka_ingestion_action():
    """
    Executes ingestion step into bronze layer.
    """
    result = _run_script("s01_upload_to_bronze.py")
    _invalidate_metrics_cache()
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)
    return {
        "operation": "kafka_ingestion",
        "status": "success",
        "message": "Kafka ingestion started and completed.",
        "result": result,
    }


@app.post('/api/actions/bronze-to-silver')
async def run_bronze_to_silver_action():
    """
    Executes Bronze -> Silver transformation for available raw datasets.
    """
    result = _run_bronze_to_silver_jobs()
    _invalidate_metrics_cache()
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)
    return {
        "operation": "bronze_to_silver",
        "status": "success",
        "message": "Bronze -> Silver transformation completed.",
        "result": result,
    }


@app.post('/api/actions/silver-to-gold')
async def run_silver_to_gold_action():
    """
    Executes Silver enrichment and Gold curation.
    """
    result = _run_silver_to_gold_jobs()
    _invalidate_metrics_cache()
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)
    return {
        "operation": "silver_to_gold",
        "status": "success",
        "message": "Silver -> Gold transformation completed.",
        "result": result,
    }


@app.post('/api/actions/data-quality-checks')
async def run_data_quality_action():
    """
    Executes data quality validation report generation.
    """
    result = _run_script("s04_dq_validation_report.py")
    _invalidate_metrics_cache()
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)
    return {
        "operation": "data_quality_checks",
        "status": "success",
        "message": "Data quality checks completed.",
        "result": result,
    }


@app.post('/api/actions/generate-stakeholder-views')
async def run_generate_stakeholder_views_action():
    """
    Generates stakeholder views from live medallion datasets.
    """
    result = _generate_stakeholder_views_job()
    _invalidate_metrics_cache()
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result)
    return {
        "operation": "generate_stakeholder_views",
        "status": "success",
        "message": "Stakeholder views generated.",
        "result": result,
    }


@app.post('/api/reject-drift')
async def reject_drift(request: ApproveRejectRequest):
    """
    Reject a pending drift event
    POST /api/reject-drift
    Body: {"table": "products", "event_id": "drift_products_20260105_123456.json"}
    """
    try:
        if not request.table or not request.event_id:
            raise HTTPException(status_code=400, detail="Missing table or event_id")
        
        event_path = os.path.join(DRIFT_EVENTS_DIR, request.event_id)
        
        if not os.path.exists(event_path):
            raise HTTPException(status_code=404, detail="Event not found")
        
        event_data = load_json_file(event_path)
        event_data["rejected"] = True
        event_data["rejected_at"] = datetime.utcnow().isoformat() + "Z"
        event_data["rejected_by"] = "user"
        
        with open(event_path, 'w', encoding='utf-8') as f:
            json.dump(event_data, f, indent=2)
        
        return {
            "status": "rejected",
            "table": request.table,
            "event_id": request.event_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Storage Tier Management Endpoints
# ============================================================================

def get_azure_connection_string() -> Optional[str]:
    """Get Azure connection string from environment"""
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        env_file = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        key, value = line.split('=', 1)
                        if key.strip() == 'AZURE_STORAGE_CONNECTION_STRING':
                            conn_str = value.strip().strip('"').strip("'")
                            break
            except Exception:
                conn_str = None
    return conn_str


def _default_storage_policy_rules() -> Dict[str, Any]:
    """Default policy explanation payload for storage tier dashboard."""
    return {
        "layer_rules": {
            "bronze": {"hot": "< 3 days", "cool": "3-14 days", "archive": "> 14 days"},
            "silver": {"hot": "< 7 days", "cool": "7-60 days", "archive": "> 60 days"},
            "gold": {"hot": "< 30 days", "cool": "30-90 days", "archive": "> 90 days"},
        },
        "access_overrides": {
            "promote_to_hot": "If accessed within 1 day (when access telemetry exists)",
            "promote_archive_to_cool": "If accessed within 7 days (when access telemetry exists)",
        },
        "seasonal_override": "Datasets matching current seasonal product keywords are promoted to HOT",
    }


def _load_seasonal_tier_manager():
    """Load SeasonalTierManager directly from storage module path."""
    import sys

    storage_path = os.path.join(BASE_DIR, "storage")
    if storage_path not in sys.path:
        sys.path.insert(0, storage_path)

    module = importlib.import_module("seasonal_tier_manager")
    return module.SeasonalTierManager


@app.get('/api/storage-tiers/current')
async def get_current_storage_tiers():
    """
    Get current storage tier assignments and dataset-level policy details
    GET /api/storage-tiers/current
    """
    try:
        conn_str = get_azure_connection_string()
        
        if not conn_str:
            # Return mock data if Azure not configured
            return {
                "hot": ["transactions", "products", "users", "inventory"],
                "warm": ["orders_history", "user_preferences"],
                "cold": ["archived_transactions", "old_logs"],
                "archive": ["compliance_data", "audit_logs"],
                "dataset_details": [
                    {
                        "dataset_name": "transactions",
                        "medallion_layer": "gold",
                        "blob_path": "gold/transactions.parquet",
                        "current_blob_tier": "HOT",
                        "target_policy_tier": "HOT",
                        "data_age_days": 1,
                        "retention_days": 30,
                        "tier_reason": "age-based: hot recent gold dataset",
                    },
                    {
                        "dataset_name": "orders_history",
                        "medallion_layer": "silver",
                        "blob_path": "silver/orders_history.parquet",
                        "current_blob_tier": "COOL",
                        "target_policy_tier": "COOL",
                        "data_age_days": 22,
                        "retention_days": 60,
                        "tier_reason": "age-based: medium age silver dataset",
                    },
                    {
                        "dataset_name": "audit_logs",
                        "medallion_layer": "bronze",
                        "blob_path": "bronze/audit_logs.parquet",
                        "current_blob_tier": "ARCHIVE",
                        "target_policy_tier": "ARCHIVE",
                        "data_age_days": 120,
                        "retention_days": 365,
                        "tier_reason": "age-based: stale bronze dataset archived",
                    },
                ],
                "policy_rules": _default_storage_policy_rules(),
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "season": "festive",
                "auto_tiering_enabled": True,
                "source": "mock_data"
            }
        
        SeasonalTierManager = _load_seasonal_tier_manager()
        
        manager = SeasonalTierManager(conn_str)
        assignments = manager.get_tier_assignments()

        if not assignments.get("dataset_details"):
            assignments = manager.sync_tier_assignments_from_azure()

        assignments.setdefault("dataset_details", [])
        assignments.setdefault("policy_rules", manager.get_policy_explanation())
        assignments["source"] = "azure"
        
        return assignments
    
    except Exception as e:
        logger.error(f"Error retrieving tier assignments: {e}")
        # Fallback to mock data
        return {
            "hot": ["transactions", "products"],
            "warm": ["orders_history"],
            "cold": ["archived_transactions"],
            "archive": ["compliance_data"],
            "dataset_details": [],
            "policy_rules": _default_storage_policy_rules(),
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "season": "unknown",
            "auto_tiering_enabled": True,
            "source": "error_fallback",
            "error": str(e)
        }


@app.post('/api/storage-tiers/update')
async def update_storage_tier_assignment(request: TierAssignmentRequest):
    """
    Update tier assignment for datasets
    POST /api/storage-tiers/update
    Body: {
        "tier": "hot",
        "datasets": ["transactions", "products"],
        "season": "festive",
        "auto_tiering_enabled": true
    }
    """
    try:
        conn_str = get_azure_connection_string()
        
        if not conn_str:
            raise HTTPException(
                status_code=503,
                detail="Azure Storage not configured"
            )
        
        SeasonalTierManager = _load_seasonal_tier_manager()
        
        manager = SeasonalTierManager(conn_str)
        
        # Get current assignments
        assignments = manager.get_tier_assignments()
        assignments.setdefault("dataset_details", [])
        assignments.setdefault("policy_rules", manager.get_policy_explanation())
        
        # Remove datasets from all tiers
        for tier in ["hot", "warm", "cold", "archive"]:
            assignments[tier] = [
                d for d in assignments.get(tier, [])
                if d not in request.datasets
            ]
        
        # Add to requested tier
        target_tier = request.tier.lower()
        if target_tier not in ["hot", "warm", "cold", "archive"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier: {request.tier}"
            )
        
        assignments[target_tier].extend(request.datasets)
        
        # Update metadata
        if request.season:
            assignments["season"] = request.season
        if request.auto_tiering_enabled is not None:
            assignments["auto_tiering_enabled"] = request.auto_tiering_enabled
        
        # Save to Azure
        success = manager.save_tier_assignments(assignments)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update tier assignments"
            )
        
        return {
            "status": "success",
            "tier": request.tier,
            "datasets": request.datasets,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/storage-tiers/history')
async def get_tier_history(year_month: Optional[str] = None):
    """
    Get tier assignment history
    GET /api/storage-tiers/history?year_month=202603
    """
    try:
        conn_str = get_azure_connection_string()
        
        if not conn_str:
            return {
                "year_month": year_month or datetime.utcnow().strftime('%Y%m'),
                "history": [],
                "source": "mock_data"
            }
        
        # Note: History tracking is saved automatically by save_tier_assignments
        # This endpoint reads the monthly JSONL history files
        SeasonalTierManager = _load_seasonal_tier_manager()
        from azure.core.exceptions import ResourceNotFoundError
        
        manager = SeasonalTierManager(conn_str)
        ym = year_month or datetime.utcnow().strftime('%Y%m')
        
        # Read history from Azure
        history = []
        try:
            blob_client = manager.client.get_blob_client(
                "tier-metadata",
                f"history/tier_assignments_{ym}.jsonl"
            )
            data = blob_client.download_blob().readall().decode('utf-8')
            
            for line in data.strip().split('\n'):
                if line:
                    history.append(json.loads(line))
        except ResourceNotFoundError:
            pass
        
        return {
            "year_month": ym,
            "history": history,
            "source": "azure"
        }
    
    except Exception as e:
        logger.error(f"Error retrieving tier history: {e}")
        return {
            "year_month": year_month or datetime.utcnow().strftime('%Y%m'),
            "history": [],
            "source": "error_fallback",
            "error": str(e)
        }


@app.get('/api/storage-tiers/seasonal-recommendations')
async def get_seasonal_recommendations(season: str = "festive"):
    """
    Get recommended tier assignments for a season
    GET /api/storage-tiers/seasonal-recommendations?season=festive
    Valid seasons: festive, monsoon, dry, historical
    """
    try:
        conn_str = get_azure_connection_string()
        
        # Seasonal patterns for Sri Lankan fashion retail
        seasonal_patterns = {
            "festive": {
                "hot": ["transactions", "products", "inventory", "users", 
                        "real_time_sales", "trending_products", "customer_behavior"],
                "warm": ["orders_history", "user_preferences", "product_reviews"],
                "cold": ["archived_transactions", "old_inventory"],
                "archive": ["compliance_data", "audit_logs_historical"]
            },
            "monsoon": {
                "hot": ["transactions", "users", "inventory"],
                "warm": ["products", "orders_history", "user_preferences", "weather_impact_analysis"],
                "cold": ["archived_transactions", "seasonal_trends"],
                "archive": ["compliance_data", "audit_logs_historical"]
            },
            "dry": {
                "hot": ["transactions", "inventory"],
                "warm": ["products", "users", "orders_history"],
                "cold": ["user_preferences", "archived_transactions", "seasonal_analysis"],
                "archive": ["compliance_data", "audit_logs_historical", "yearly_reports"]
            },
            "historical": {
                "hot": [],
                "warm": ["trend_analysis", "ml_training_data"],
                "cold": ["yearly_summaries"],
                "archive": ["all_historical_data", "compliance_data", "audit_logs", "archived_transactions"]
            }
        }
        
        recommendations = seasonal_patterns.get(season, seasonal_patterns["dry"])
        
        return {
            "season": season,
            "recommendations": recommendations,
            "source": "business_rules"
        }
    
    except Exception as e:
        logger.error(f"Error getting seasonal recommendations: {e}")
        return {
            "season": season,
            "recommendations": {"hot": [], "warm": [], "cold": [], "archive": []},
            "source": "error_fallback",
            "error": str(e)
        }


@app.post('/api/storage-tiers/sync')
async def sync_tier_assignments():
    """
    Scan Azure and sync tier assignments based on actual blob tiers
    POST /api/storage-tiers/sync
    """
    try:
        conn_str = get_azure_connection_string()
        
        if not conn_str:
            raise HTTPException(
                status_code=503,
                detail="Azure Storage not configured"
            )
        
        SeasonalTierManager = _load_seasonal_tier_manager()
        
        manager = SeasonalTierManager(conn_str)
        assignments = manager.sync_tier_assignments_from_azure()
        
        return {
            "status": "success",
            "assignments": assignments,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/storage-tiers/current-season')
async def get_current_business_season():
    """
    Get current business season for Sri Lankan fashion retail
    GET /api/storage-tiers/current-season
    """
    try:
        conn_str = get_azure_connection_string()
        
        if not conn_str:
            # Calculate season without Azure
            month = datetime.utcnow().month
            season_map = {
                1: "festive", 2: "dry", 3: "dry", 4: "festive",
                5: "monsoon", 6: "monsoon", 7: "monsoon", 8: "monsoon",
                9: "monsoon", 10: "dry", 11: "dry", 12: "festive"
            }
            season = season_map.get(month, "dry")
            return {
                "season": season,
                "month": month,
                "description": f"{season.title()} Season",
                "source": "mock_data"
            }
        
        SeasonalTierManager = _load_seasonal_tier_manager()
        
        manager = SeasonalTierManager(conn_str)
        season, description = manager.get_current_season()
        
        return {
            "season": season.value,
            "month": datetime.utcnow().month,
            "description": description,
            "source": "azure"
        }
    
    except Exception as e:
        logger.error(f"Error getting current season: {e}")
        return {
            "season": "unknown",
            "month": datetime.utcnow().month,
            "description": "Unknown season",
            "source": "error_fallback",
            "error": str(e)
        }


# ============================================================================
# Filtering & Analytics Endpoints
# ============================================================================

@app.get('/api/storage-tiers/by-tier')
async def get_datasets_by_tier(tier: str = Query(..., description="Storage tier: hot, warm, cold, archive")):
    """
    Get all datasets assigned to a specific storage tier
    GET /api/storage-tiers/by-tier?tier=hot
    """
    try:
        tier_lower = tier.lower()
        
        # Get tier assignments (from architecture or mock data)
        assignments = {
            "hot": ["transactions", "products", "users", "real_time_sales"],
            "warm": ["orders_history", "user_preferences", "product_reviews"],
            "cold": ["archived_transactions", "old_inventory", "seasonal_trends"],
            "archive": ["compliance_data", "audit_logs_historical", "yearly_reports"]
        }
        
        datasets = assignments.get(tier_lower, [])
        
        return {
            "tier": tier_lower,
            "datasets": datasets,
            "count": len(datasets),
            "cost_per_tb": {
                "hot": 23,
                "warm": 10,
                "cool": 10,
                "cold": 4,
                "archive": 1
            }.get(tier_lower, 0),
            "description": {
                "hot": "High-performance active data (< 1 day access)",
                "warm": "Transitional / unclassified workloads (1-30 days)",
                "cold": "Cost-optimized cool storage (30-90 days)",
                "archive": "Long-term archival retention (> 90 days)"
            }.get(tier_lower, "Unknown")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/drift-events/by-date-range')
async def get_drift_events_by_date_range(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    limit: Optional[int] = Query(None, description="Max results")
):
    """
    Get drift events within a date range
    GET /api/drift-events/by-date-range?start_date=2025-03-01&end_date=2025-03-06
    """
    try:
        from datetime import datetime as dt
        
        start_dt = dt.strptime(start_date, "%Y-%m-%d")
        end_dt = dt.strptime(end_date, "%Y-%m-%d")
        
        drift_events = load_drift_events()
        filtered_events = []
        
        for evt in drift_events:
            ts = evt.get("timestamp", "")
            if not ts:
                continue
            
            try:
                evt_dt = _parse_iso_timestamp(ts)
                if evt_dt and start_dt <= evt_dt.date() <= end_dt.date():
                    filtered_events.append(evt)
            except Exception:
                continue
        
        if limit:
            filtered_events = filtered_events[:limit]
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "count": len(filtered_events),
            "events": filtered_events
        }
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/approvals/{notification_id}')
async def get_approval_details(notification_id: str):
    """
    Get details for a specific approval notification
    GET /api/approvals/drift_products_20250306_123456.json
    """
    try:
        event_path = os.path.join(DRIFT_EVENTS_DIR, notification_id)
        
        if not os.path.exists(event_path):
            raise HTTPException(status_code=404, detail="Event not found")
        
        event = load_json_file(event_path)
        
        return {
            "event_id": notification_id,
            "table": event.get("table"),
            "timestamp": event.get("timestamp"),
            "decision": event.get("decision"),
            "risk_level": event.get("risk_level"),
            "diff": event.get("diff"),
            "counts": {
                "new": len(event.get("diff", {}).get("new_columns", [])),
                "missing": len(event.get("diff", {}).get("missing_columns", [])),
                "dtype": len(event.get("diff", {}).get("dtype_changes", [])),
                "renames": len(event.get("diff", {}).get("renames", []))
            },
            "requires_approval": event.get("requires_approval"),
            "approved": event.get("approved", False),
            "rejected": event.get("rejected", False),
            "approved_at": event.get("approved_at"),
            "rejected_at": event.get("rejected_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


