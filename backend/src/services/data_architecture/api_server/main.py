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
import importlib
import logging
from datetime import datetime, timezone
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


