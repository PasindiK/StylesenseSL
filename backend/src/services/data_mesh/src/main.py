from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
from pathlib import Path
import os
import shutil
from datetime import datetime, timedelta
import importlib.util
import json
import sys
from threading import Lock, Thread
import uuid
import time
try:
    from .domains_metadata_loader import get_domains_metadata
except ImportError:
    from domains_metadata_loader import get_domains_metadata
from fastapi.responses import FileResponse
try:
    from .pipeline_conversational_agent import PipelineConversationalAgent
except ImportError:
    from pipeline_conversational_agent import PipelineConversationalAgent
try:
    from .governance_intelligence import GovernanceIntelligenceEngine
except ImportError:
    from governance_intelligence import GovernanceIntelligenceEngine
try:
    from .governance_prioritization import GovernancePrioritizationEngine
except ImportError:
    from governance_prioritization import GovernancePrioritizationEngine
try:
    from .date_rebase_utility import BusinessDateRebaseUtility
except ImportError:
    from date_rebase_utility import BusinessDateRebaseUtility
try:
    from .correct_silver_inputs_for_adgri import correct_product, correct_sales, correct_users
except ImportError:
    from correct_silver_inputs_for_adgri import correct_product, correct_sales, correct_users

# Paths for Data Mesh assets (safe after folder relocation)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data"
DATA_PATH = DATA_ROOT / "Data_Mesh_Domains"
TEST_CASES_ROOTS = [
    DATA_ROOT / "test_cases",
    DATA_ROOT / "Data" / "test_cases",
    DATA_ROOT / "Data" / "governance_test_cases",
]
IMMUTABLE_BASELINE_ROOTS = [
    DATA_ROOT / "baseline_cases",
    DATA_ROOT / "Data" / "baseline_cases",
]
CONTRACTS_PATH = DATA_ROOT / "Contracts"
MONITORING_HISTORY_PATH = DATA_ROOT / "monitoring" / "domain_health_history.csv"
SCENARIO_COMPARISON_HISTORY_PATH = DATA_ROOT / "monitoring" / "scenario_test_case_history.json"
CREDENTIALS_PATH = DATA_ROOT / "monitoring" / "config" / "credentials.json"

# List of domains
DOMAINS = ["users_domain", "product_domain", "sales_domain", "shop_domain"]

SILVER_DOMAIN_MAPPING = {
    "users_clean.csv": "users_domain",
    "products_clean.csv": "product_domain",
    "shops_clean.csv": "shop_domain",
    "transactions_clean.csv": "sales_domain",
    "trends_clean.csv": "engagement_domain",
    "users_preferences_clean.csv": "user_preferences_domain",
    "interactions_clean.csv": "interaction_domain",
}

GOVERNANCE_TEST_CASES = {
    "sales_domain": {
        "silver_target": "transactions_clean.csv",
        "business_date_field": "transaction_date",
        "baseline_file": "sales_baseline.csv",
        "prepared_files": [
            "sales_baseline.csv",
            "sales_current.csv",
            "sales_stale_30days.csv",
            "sales_stale_60days.csv",
            "sales_volume_drop.csv",
            "sales_distribution_shift.csv",
            "sales_stale_and_distribution_shift.csv",
            "sales_volume_spike.csv",
        ],
        "demo_scenarios": [
            {
                "name": "sales_baseline",
                "label": "Sales Baseline (Healthy)",
                "file": "sales_baseline.csv",
                "factors": ["healthy_baseline"],
            },
            {
                "name": "sales_stale_30days",
                "label": "Sales Freshness Instability (30-day stale)",
                "file": "sales_stale_30days.csv",
                "factors": ["freshness_instability"],
            },
            {
                "name": "sales_volume_drop",
                "label": "Sales Volume Instability (drop)",
                "file": "sales_volume_drop.csv",
                "factors": ["volume_instability"],
            },
            {
                "name": "sales_distribution_shift",
                "label": "Sales Distribution Instability (shift)",
                "file": "sales_distribution_shift.csv",
                "factors": ["distribution_instability"],
            },
            {
                "name": "sales_stale_and_distribution_shift",
                "label": "Sales Combined Degradation (freshness + distribution)",
                "file": "sales_stale_and_distribution_shift.csv",
                "factors": ["freshness_instability", "distribution_instability", "combined"],
            },
            {
                "name": "sales_volume_spike",
                "label": "Sales Volume Instability (spike)",
                "file": "sales_volume_spike.csv",
                "factors": ["volume_instability"],
            },
        ],
    },
    "users_domain": {
        "silver_target": "users_clean.csv",
        "business_date_field": "signup_ts",
        "prepared_files": [
            "users_current.csv",
            "users_stale_30days.csv",
            "users_stale_60days.csv",
            "users_stale_distribution_shift.csv",
        ],
    },
}

TEST_CASE_PREFIX_DOMAIN_MAPPING = {
    "sales_": "sales_domain",
    "users_": "users_domain",
    "products_": "product_domain",
    "shops_": "shop_domain",
}

app = FastAPI()

_rerun_lock = Lock()
_rerun_state = {
    "status": "idle",
    "job_id": None,
    "started_at": None,
    "finished_at": None,
    "summary": None,
    "error": None,
    "progress_percent": 0.0,
    "domains_completed": 0,
    "total_domains": 0,
    "rows_processed_so_far": 0,
    "current_domain": None,
    "current_domain_status": None,
}


def _load_reload_pipeline_class():
    module_path = DATA_ROOT / "monitoring" / "pipelines" / "reload_data_mesh_pipeline.py"
    spec = importlib.util.spec_from_file_location("reload_data_mesh_pipeline", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load reload_data_mesh_pipeline module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.DataMeshReloadPipeline


def _load_rerun_credentials() -> list[dict]:
    if not CREDENTIALS_PATH.exists():
        return []
    try:
        payload = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict):
        if "users" in payload and isinstance(payload["users"], list):
            users = []
            for item in payload["users"]:
                if isinstance(item, dict) and item.get("username") and item.get("password"):
                    users.append(
                        {
                            "username": str(item.get("username")),
                            "password": str(item.get("password")),
                        }
                    )
            return users

        if payload.get("username") and payload.get("password"):
            return [
                {
                    "username": str(payload.get("username")),
                    "password": str(payload.get("password")),
                }
            ]

    return []


def _is_rerun_authorized(
    session_id: str,
    user_id: str,
    auth_token: str,
    auth_username: str,
    auth_password: str,
) -> bool:
    _ = (session_id, user_id, auth_token)
    credentials = _load_rerun_credentials()
    if auth_username and auth_password:
        for entry in credentials:
            if auth_username == entry.get("username") and auth_password == entry.get("password"):
                return True
    return False


def _run_rerun_job(job_id: str) -> None:
    try:
        pipeline_class = _load_reload_pipeline_class()
        pipeline = pipeline_class()

        def _progress_update(progress: dict) -> None:
            with _rerun_lock:
                if _rerun_state.get("job_id") != job_id or _rerun_state.get("status") != "running":
                    return
                _rerun_state.update(
                    {
                        "progress_percent": float(progress.get("progress_percent") or 0.0),
                        "domains_completed": int(progress.get("domains_completed") or 0),
                        "total_domains": int(progress.get("total_domains") or 0),
                        "rows_processed_so_far": int(progress.get("rows_processed_cumulative") or 0),
                        "current_domain": progress.get("domain"),
                        "current_domain_status": progress.get("status"),
                    }
                )

        summary = pipeline.run_once(progress_callback=_progress_update)
        with _rerun_lock:
            _rerun_state.update(
                {
                    "status": "completed",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "summary": summary,
                    "error": None,
                    "progress_percent": 100.0,
                    "domains_completed": int(summary.get("domains_processed") or 0),
                    "total_domains": int(summary.get("domains_processed") or 0),
                    "rows_processed_so_far": int(summary.get("rows_processed") or 0),
                    "current_domain": None,
                    "current_domain_status": None,
                }
            )
    except Exception as exc:
        with _rerun_lock:
            _rerun_state.update(
                {
                    "status": "failed",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "error": str(exc),
                    "current_domain_status": "FAILED",
                }
            )


def _trigger_pipeline_rerun() -> dict:
    with _rerun_lock:
        if _rerun_state.get("status") == "running":
            return {
                "status": "already_running",
                "job_id": _rerun_state.get("job_id"),
                "started_at": _rerun_state.get("started_at"),
            }

        job_id = str(uuid.uuid4())[:8]
        _rerun_state.update(
            {
                "status": "running",
                "job_id": job_id,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": None,
                "summary": None,
                "error": None,
                "progress_percent": 0.0,
                "domains_completed": 0,
                "total_domains": 0,
                "rows_processed_so_far": 0,
                "current_domain": None,
                "current_domain_status": None,
            }
        )

    worker = Thread(target=_run_rerun_job, args=(job_id,), daemon=True)
    worker.start()
    return {
        "status": "started",
        "job_id": job_id,
        "started_at": _rerun_state.get("started_at"),
    }


def _get_rerun_state() -> dict:
    with _rerun_lock:
        return dict(_rerun_state)


def _normalize_domain_name(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if not raw.endswith("_domain"):
        raw = f"{raw}_domain"
    return raw


def _domain_silver_targets(selected_domain: str) -> list[Path]:
    normalized = _normalize_domain_name(selected_domain)
    files = [
        DATA_ROOT / "Data" / "Silver-data" / file_name
        for file_name, mapped_domain in SILVER_DOMAIN_MAPPING.items()
        if _normalize_domain_name(mapped_domain) == normalized
    ]
    return [file_path for file_path in files if file_path.exists()]


def _domain_simulation_options() -> list[dict]:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    options = []
    for domain in sorted(set(SILVER_DOMAIN_MAPPING.values())):
        files = _domain_silver_targets(domain)
        latest_dates = []
        for file_path in files:
            latest = utility._file_latest_business_date(file_path)
            if latest is not None:
                latest_dates.append(latest)
        options.append(
            {
                "domain": _normalize_domain_name(domain),
                "silver_files": [str(path) for path in files],
                "supported": len(latest_dates) > 0,
                "latest_business_data_date": max(latest_dates).isoformat() if latest_dates else None,
            }
        )
    return options


def _inspect_domain_silver_stale_dates(selected_domain: str) -> dict:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    target_files = _domain_silver_targets(selected_domain)
    if not target_files:
        return {
            "domain": _normalize_domain_name(selected_domain),
            "supported": False,
            "message": "No Silver file mapping found for selected domain.",
            "files_scanned": 0,
            "stale_files_count": 0,
            "stale_files": [],
        }

    today = datetime.now().date()
    files: list[dict] = []
    for file_path in target_files:
        latest = utility._file_latest_business_date(file_path)
        if latest is None:
            files.append(
                {
                    "file": str(file_path),
                    "has_business_date": False,
                    "latest_business_date": None,
                    "stale": False,
                    "days_stale": None,
                }
            )
            continue
        days_stale = int((today - latest.date()).days)
        files.append(
            {
                "file": str(file_path),
                "has_business_date": True,
                "latest_business_date": latest.isoformat(),
                "stale": days_stale > 0,
                "days_stale": days_stale,
            }
        )

    stale_files = [item for item in files if item.get("stale")]
    supported = any(item.get("has_business_date") for item in files)
    return {
        "domain": _normalize_domain_name(selected_domain),
        "supported": supported,
        "message": None if supported else "Stale-date simulation is not supported for this domain because no business-date field is available.",
        "files_scanned": len(target_files),
        "stale_files_count": len(stale_files),
        "stale_files": stale_files,
        "files": files,
    }


def _run_domain_silver_rebase(selected_domain: str, simulation_days_offset: int) -> dict:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    target_files = _domain_silver_targets(selected_domain)
    if not target_files:
        return {
            "status": "no_files",
            "message": "No Silver CSV files discovered for selected domain.",
            "domain": _normalize_domain_name(selected_domain),
            "files_scanned": 0,
            "files_changed": 0,
            "shifted_rows_total": 0,
            "results": [],
            "old_latest_business_date": None,
            "new_latest_business_date": None,
        }

    results = []
    changed_files = 0
    shifted_rows_total = 0
    old_latest_values = []
    new_latest_values = []

    for file_path in target_files:
        latest = utility._file_latest_business_date(file_path)
        if latest is None:
            continue

        if simulation_days_offset == 0:
            delta_days = int((datetime.now().date() - latest.date()).days)
            delta = timedelta(days=delta_days)
        else:
            delta = timedelta(days=int(simulation_days_offset))

        result = utility._rebase_file(file_path=file_path, delta=delta, apply_changes=True)
        if result is None:
            continue

        changed_files += 1
        shifted_rows_total += int(result.shifted_rows)
        if result.old_latest_business_date:
            old_latest_values.append(datetime.fromisoformat(result.old_latest_business_date))
        if result.new_latest_business_date:
            new_latest_values.append(datetime.fromisoformat(result.new_latest_business_date))

        results.append(
            {
                "file": result.file,
                "shifted_rows": int(result.shifted_rows),
                "shifted_columns": result.shifted_columns,
                "old_latest_business_date": result.old_latest_business_date,
                "new_latest_business_date": result.new_latest_business_date,
            }
        )

    return {
        "status": "applied_manual_shift" if simulation_days_offset != 0 else "normalized_to_current_business_date",
        "message": "Domain-targeted Silver business-date shift completed.",
        "domain": _normalize_domain_name(selected_domain),
        "offset_days": int(simulation_days_offset),
        "files_scanned": len(target_files),
        "files_changed": changed_files,
        "shifted_rows_total": shifted_rows_total,
        "results": results,
        "old_latest_business_date": max(old_latest_values).isoformat() if old_latest_values else None,
        "new_latest_business_date": max(new_latest_values).isoformat() if new_latest_values else None,
    }


def _domain_governance_snapshot(domain_name: str) -> dict:
    detail = governance_engine.governance_domain(domain_name)
    freshness = detail.get("freshness_stability") if isinstance(detail, dict) else {}
    distribution = detail.get("distribution_stability") if isinstance(detail, dict) else {}
    volume = detail.get("volume_stability") if isinstance(detail, dict) else {}
    freshness_risk = None
    distribution_risk = None
    volume_risk = None
    if isinstance(freshness, dict) and freshness.get("risk") is not None:
        freshness_risk = round(float(freshness.get("risk")), 6)
    if isinstance(distribution, dict) and distribution.get("risk") is not None:
        distribution_risk = round(float(distribution.get("risk")), 6)
    if isinstance(volume, dict) and volume.get("risk") is not None:
        volume_risk = round(float(volume.get("risk")), 6)

    return {
        "domain": _normalize_domain_name(domain_name),
        "adgri": detail.get("adgri_score"),
        "top_reason": detail.get("top_reason"),
        "explanation": detail.get("explanation"),
        "low_score_reason_label": detail.get("low_score_reason_label"),
        "freshness_instability": freshness_risk,
        "distribution_instability": distribution_risk,
        "volume_instability": volume_risk,
        "latest_business_data_date": detail.get("latest_business_data_date"),
        "latest_domain_refresh_time": detail.get("latest_domain_refresh_time"),
        "governance_evaluation_time": detail.get("latest_governance_evaluation_time"),
        "freshness_reference": detail.get("freshness_reference"),
        "risk_trend": detail.get("risk_trend") if isinstance(detail.get("risk_trend"), list) else [],
        "trend_label": detail.get("trend_label") or "Governance Evaluation Trend",
    }


def _load_scenario_comparison_history() -> list[dict]:
    if not SCENARIO_COMPARISON_HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(SCENARIO_COMPARISON_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _save_scenario_comparison_history(rows: list[dict]) -> None:
    SCENARIO_COMPARISON_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_COMPARISON_HISTORY_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _scenario_score_delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(float(current) - float(baseline), 4)


def _record_scenario_test_case_run(selected_domain: str, baseline_score: float | None, scenario_score: float | None) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    now_iso = datetime.now().isoformat(timespec="seconds")
    record = {
        "cycle_id": str(uuid.uuid4())[:10],
        "selected_domain": normalized_domain,
        "status": "scenario_applied",
        "baseline_score": baseline_score,
        "scenario_score": scenario_score,
        "restored_score": None,
        "scenario_delta": _scenario_score_delta(scenario_score, baseline_score),
        "restore_delta": None,
        "recovery_from_scenario": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    rows = _load_scenario_comparison_history()
    rows.append(record)
    _save_scenario_comparison_history(rows)
    return record


def _record_scenario_restore(selected_domain: str, restored_score: float | None) -> dict | None:
    normalized_domain = _normalize_domain_name(selected_domain)
    rows = _load_scenario_comparison_history()

    latest_idx = None
    for idx in range(len(rows) - 1, -1, -1):
        item = rows[idx]
        if _normalize_domain_name(item.get("selected_domain") or "") != normalized_domain:
            continue
        if item.get("status") == "scenario_applied":
            latest_idx = idx
            break

    if latest_idx is None:
        return None

    target = dict(rows[latest_idx])
    target["status"] = "restored"
    target["restored_score"] = restored_score
    target["restore_delta"] = _scenario_score_delta(restored_score, target.get("baseline_score"))
    target["recovery_from_scenario"] = _scenario_score_delta(restored_score, target.get("scenario_score"))
    target["updated_at"] = datetime.now().isoformat(timespec="seconds")
    rows[latest_idx] = target
    _save_scenario_comparison_history(rows)
    return target


def _latest_scenario_comparison(selected_domain: str) -> dict | None:
    normalized_domain = _normalize_domain_name(selected_domain)
    rows = _load_scenario_comparison_history()
    for item in reversed(rows):
        if _normalize_domain_name(item.get("selected_domain") or "") == normalized_domain:
            return item
    return None


def _infer_domain_from_test_case_name(test_case_name: str) -> str | None:
    normalized_name = str(test_case_name or "").strip().lower()
    if not normalized_name:
        return None
    for prefix, domain in TEST_CASE_PREFIX_DOMAIN_MAPPING.items():
        if normalized_name.startswith(prefix):
            return _normalize_domain_name(domain)
    return None


def _test_case_scenario_label(test_case_name: str) -> str:
    name = str(test_case_name or "").strip().lower()
    if "baseline" in name or "current" in name:
        return "baseline"
    if "volume_drop" in name:
        return "volume drop"
    if "volume_spike" in name:
        return "volume spike"
    if "distribution_shift" in name and "stale" not in name:
        return "distribution shift"
    if "stale_and_distribution_shift" in name or "stale_distribution_shift" in name or "and_shifted" in name:
        return "stale + distribution shift"
    if "current" in name:
        return "Current"
    if "stale_30" in name:
        return "30 days stale"
    if "stale_60" in name:
        return "60 days stale"
    if "distribution_shift" in name or "and_shifted" in name:
        return "stale + distribution shift"
    return "Custom scenario"


def _resolve_test_case_source(file_name: str, domain: str | None = None) -> Path | None:
    normalized_name = str(file_name or "").strip()
    if not normalized_name:
        return None

    normalized_domain = _normalize_domain_name(domain or "") if domain else ""
    for root in TEST_CASES_ROOTS:
        direct = root / normalized_name
        if direct.exists():
            return direct

        if normalized_domain:
            per_domain = root / normalized_domain / normalized_name
            if per_domain.exists():
                return per_domain

    return None


def _resolve_immutable_baseline_source(file_name: str, domain: str | None = None) -> Path | None:
    normalized_name = str(file_name or "").strip()
    if not normalized_name:
        return None

    normalized_domain = _normalize_domain_name(domain or "") if domain else ""
    for root in IMMUTABLE_BASELINE_ROOTS:
        direct = root / normalized_name
        if direct.exists():
            return direct

        if normalized_domain:
            per_domain = root / normalized_domain / normalized_name
            if per_domain.exists():
                return per_domain

    return None


def _reset_domain_output_state(selected_domain: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    domain_folder = DATA_PATH / normalized_domain
    removed_files = 0
    removed_dirs = 0

    if domain_folder.exists() and domain_folder.is_dir():
        for child in domain_folder.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
                removed_files += 1
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed_dirs += 1

    domain_folder.mkdir(parents=True, exist_ok=True)
    return {
        "selected_domain": normalized_domain,
        "domain_output_path": str(domain_folder),
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
    }


def _reset_domain_governance_state(selected_domain: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    removed_rows = 0

    if MONITORING_HISTORY_PATH.exists():
        try:
            history_df = pd.read_csv(MONITORING_HISTORY_PATH)
            if not history_df.empty and "domain_name" in history_df.columns:
                original_rows = int(len(history_df))
                filtered = history_df[
                    history_df["domain_name"].astype(str).str.strip().str.lower() != normalized_domain
                ].copy()
                removed_rows = max(0, original_rows - int(len(filtered)))
                filtered.to_csv(MONITORING_HISTORY_PATH, index=False)
        except Exception:
            removed_rows = 0

    return {
        "selected_domain": normalized_domain,
        "history_rows_removed": removed_rows,
        "history_file": str(MONITORING_HISTORY_PATH),
    }


def _reset_domain_pipeline_log_state(selected_domain: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    pipeline_log_path = MONITORING_HISTORY_PATH.parent / "logs" / "pipeline_log.json"
    removed_rows = 0

    if pipeline_log_path.exists():
        try:
            logs = pd.read_json(pipeline_log_path)
            if not logs.empty and "domain" in logs.columns:
                original_rows = int(len(logs))
                filtered = logs[
                    logs["domain"].astype(str).str.strip().str.lower() != normalized_domain
                ].copy()
                removed_rows = max(0, original_rows - int(len(filtered)))
                filtered.to_json(pipeline_log_path, orient="records", indent=2, date_format="iso")
        except Exception:
            removed_rows = 0

    return {
        "selected_domain": normalized_domain,
        "pipeline_log_file": str(pipeline_log_path),
        "pipeline_log_rows_removed": removed_rows,
    }


def _seed_clean_domain_history_from_output(selected_domain: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    domain_csv = DATA_PATH / normalized_domain / f"{normalized_domain}.csv"
    if not domain_csv.exists():
        return {
            "selected_domain": normalized_domain,
            "seeded": False,
            "message": f"Domain output not found for history seeding: {domain_csv}",
        }

    df = pd.read_csv(domain_csv)
    row_count = int(len(df))
    config = GOVERNANCE_TEST_CASES.get(normalized_domain) or {}
    business_date_field = str(config.get("business_date_field") or "").strip()
    freshness_hours = 0.0

    if business_date_field and business_date_field in df.columns:
        parsed = pd.to_datetime(df[business_date_field], errors="coerce").dropna()
        if not parsed.empty:
            latest_business_ts = pd.Timestamp(parsed.max()).to_pydatetime()
            freshness_hours = max(0.0, (datetime.now() - latest_business_ts).total_seconds() / 3600.0)

    seed_points = []
    base_time = datetime.now()
    for i in range(14, 0, -1):
        seed_points.append(
            {
                "domain_name": normalized_domain,
                "row_count": row_count,
                "timestamp": (base_time - timedelta(days=i)).isoformat(timespec="seconds"),
                "freshness_hours": round(float(freshness_hours), 6),
            }
        )

    if MONITORING_HISTORY_PATH.exists():
        try:
            history_df = pd.read_csv(MONITORING_HISTORY_PATH)
        except Exception:
            history_df = pd.DataFrame(columns=["domain_name", "row_count", "timestamp", "freshness_hours"])
    else:
        history_df = pd.DataFrame(columns=["domain_name", "row_count", "timestamp", "freshness_hours"])

    if "domain_name" not in history_df.columns:
        history_df["domain_name"] = ""
    history_df = history_df[
        history_df["domain_name"].astype(str).str.strip().str.lower() != normalized_domain
    ].copy()

    seeded_df = pd.DataFrame(seed_points)
    combined = pd.concat([history_df, seeded_df], ignore_index=True)
    combined.to_csv(MONITORING_HISTORY_PATH, index=False)

    return {
        "selected_domain": normalized_domain,
        "seeded": True,
        "seed_rows": len(seed_points),
        "row_count_seeded": row_count,
        "freshness_hours_seeded": round(float(freshness_hours), 6),
        "history_file": str(MONITORING_HISTORY_PATH),
    }


def _governance_test_case_options() -> list[dict]:
    rows: list[dict] = []
    for domain, cfg in GOVERNANCE_TEST_CASES.items():
        normalized_domain = _normalize_domain_name(domain)
        for file_name in cfg.get("prepared_files", []):
            source_path = _resolve_test_case_source(file_name=file_name, domain=normalized_domain)
            rows.append(
                {
                    "name": file_name,
                    "scenario": _test_case_scenario_label(file_name),
                    "inferred_domain": normalized_domain,
                    "business_date_field": cfg.get("business_date_field"),
                    "exists": source_path is not None,
                    "source_path": str(source_path) if source_path is not None else None,
                }
            )
    return rows


def _governance_demo_scenarios(selected_domain: str) -> list[dict]:
    normalized_domain = _normalize_domain_name(selected_domain)
    config = GOVERNANCE_TEST_CASES.get(normalized_domain) or {}
    scenarios = config.get("demo_scenarios") or []
    rows: list[dict] = []

    for scenario in scenarios:
        scenario_name = str(scenario.get("name") or "").strip()
        file_name = str(scenario.get("file") or "").strip()
        if not scenario_name or not file_name:
            continue
        source_path = _resolve_test_case_source(file_name=file_name, domain=normalized_domain)
        rows.append(
            {
                "name": scenario_name,
                "label": str(scenario.get("label") or scenario_name),
                "file": file_name,
                "factors": scenario.get("factors") or [],
                "selected_domain": normalized_domain,
                "exists": source_path is not None,
                "source_path": str(source_path) if source_path is not None else None,
            }
        )

    return rows


def _copy_named_demo_scenario_to_silver(selected_domain: str, scenario_name: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    config = GOVERNANCE_TEST_CASES.get(normalized_domain)
    if not config:
        return {
            "supported": False,
            "loaded": False,
            "message": f"Domain '{normalized_domain}' is not configured for governance demo scenarios.",
            "selected_domain": normalized_domain,
            "selected_scenario": scenario_name,
        }

    target_file = DATA_ROOT / "Data" / "Silver-data" / str(config.get("silver_target") or "")
    scenarios = {str(item.get("name") or "").strip(): item for item in (config.get("demo_scenarios") or [])}
    chosen = scenarios.get(str(scenario_name or "").strip())
    if not chosen:
        return {
            "supported": True,
            "loaded": False,
            "message": f"Scenario '{scenario_name}' is not available for {normalized_domain}.",
            "selected_domain": normalized_domain,
            "selected_scenario": scenario_name,
        }

    scenario_file = str(chosen.get("file") or "").strip()
    source_file = _resolve_test_case_source(file_name=scenario_file, domain=normalized_domain)

    if source_file is None:
        return {
            "supported": True,
            "loaded": False,
            "message": f"Scenario source file not found: {scenario_file}",
            "selected_domain": normalized_domain,
            "selected_scenario": scenario_name,
            "target_file": str(target_file),
            "source_file": None,
        }

    if not target_file.exists():
        return {
            "supported": True,
            "loaded": False,
            "message": f"Active Silver target file not found: {target_file}",
            "selected_domain": normalized_domain,
            "selected_scenario": scenario_name,
            "target_file": str(target_file),
            "source_file": str(source_file),
        }

    shutil.copy2(source_file, target_file)
    return {
        "supported": True,
        "loaded": True,
        "message": "Scenario dataset loaded into active Silver file.",
        "selected_domain": normalized_domain,
        "selected_scenario": scenario_name,
        "scenario_label": str(chosen.get("label") or scenario_name),
        "source_file": str(source_file),
        "target_file": str(target_file),
    }


def _restore_domain_baseline_to_silver(selected_domain: str) -> dict:
    normalized_domain = _normalize_domain_name(selected_domain)
    config = GOVERNANCE_TEST_CASES.get(normalized_domain)
    if not config:
        return {
            "supported": False,
            "restored": False,
            "message": f"Domain '{normalized_domain}' is not configured for baseline restore.",
            "selected_domain": normalized_domain,
        }

    baseline_file = str(config.get("baseline_file") or "").strip()
    if not baseline_file:
        return {
            "supported": True,
            "restored": False,
            "message": f"No baseline_file is configured for domain '{normalized_domain}'.",
            "selected_domain": normalized_domain,
        }

    source_file = _resolve_immutable_baseline_source(file_name=baseline_file, domain=normalized_domain)
    target_file = DATA_ROOT / "Data" / "Silver-data" / str(config.get("silver_target") or "")

    if source_file is None:
        return {
            "supported": True,
            "restored": False,
            "message": f"Immutable baseline file not found: {baseline_file}",
            "selected_domain": normalized_domain,
            "source_file": None,
            "target_file": str(target_file),
        }

    if not target_file.exists():
        return {
            "supported": True,
            "restored": False,
            "message": f"Active Silver target file not found: {target_file}",
            "selected_domain": normalized_domain,
            "source_file": str(source_file),
            "target_file": str(target_file),
        }

    before_size = target_file.stat().st_size if target_file.exists() else 0
    shutil.copy2(source_file, target_file)
    after_size = target_file.stat().st_size if target_file.exists() else 0
    silver_replaced = bool(target_file.exists() and after_size > 0 and (after_size != before_size or before_size == 0))

    return {
        "supported": True,
        "restored": True,
        "message": "Immutable baseline dataset restored into active Silver file.",
        "selected_domain": normalized_domain,
        "baseline_file": baseline_file,
        "source_file": str(source_file),
        "target_file": str(target_file),
        "silver_replaced": silver_replaced,
    }


def _build_domain_before_after_comparison(selected_domain: str, selected_scenario: str, before: dict, after: dict) -> dict:
    return {
        "selected_scenario": selected_scenario,
        "selected_domain": selected_domain,
        "adgri_before": before.get("adgri"),
        "adgri_after": after.get("adgri"),
        "freshness_instability_before": before.get("freshness_instability"),
        "freshness_instability_after": after.get("freshness_instability"),
        "volume_instability_before": before.get("volume_instability"),
        "volume_instability_after": after.get("volume_instability"),
        "distribution_instability_before": before.get("distribution_instability"),
        "distribution_instability_after": after.get("distribution_instability"),
        "top_reason_before": before.get("top_reason"),
        "top_reason_after": after.get("top_reason"),
        "latest_evaluation_time_after": after.get("governance_evaluation_time"),
        "latest_business_data_date_after": after.get("latest_business_data_date"),
    }


def _copy_governance_test_case_to_silver(test_case_name: str) -> dict:
    selected_domain = _infer_domain_from_test_case_name(test_case_name)
    if not selected_domain:
        return {
            "supported": False,
            "loaded": False,
            "message": "Unable to infer target domain from selected test-case file name.",
            "selected_test_case": test_case_name,
        }

    config = GOVERNANCE_TEST_CASES.get(selected_domain)
    if not config:
        return {
            "supported": False,
            "loaded": False,
            "message": f"Inferred domain '{selected_domain}' is not configured for governance test-case workflow yet.",
            "selected_test_case": test_case_name,
            "selected_domain": selected_domain,
        }

    source_file = _resolve_test_case_source(file_name=test_case_name, domain=selected_domain)
    target_file = DATA_ROOT / "Data" / "Silver-data" / str(config.get("silver_target"))

    if source_file is None:
        return {
            "supported": True,
            "loaded": False,
            "message": f"Prepared test-case file not found in configured test_cases folders: {test_case_name}",
            "source_file": None,
            "target_file": str(target_file),
            "selected_test_case": test_case_name,
            "selected_domain": selected_domain,
        }

    if not target_file.exists():
        return {
            "supported": True,
            "loaded": False,
            "message": f"Active Silver target file not found: {target_file}",
            "source_file": str(source_file),
            "target_file": str(target_file),
            "selected_test_case": test_case_name,
            "selected_domain": selected_domain,
        }

    shutil.copy2(source_file, target_file)
    return {
        "supported": True,
        "loaded": True,
        "message": "Prepared governance test-case loaded into active Silver dataset.",
        "source_file": str(source_file),
        "target_file": str(target_file),
        "selected_test_case": test_case_name,
        "selected_domain": selected_domain,
    }


def _map_uploaded_file_to_silver_target(uploaded_file_name: str) -> dict:
    file_name = Path(str(uploaded_file_name or "").strip()).name.lower()
    if not file_name:
        return {
            "mapped": False,
            "message": "Uploaded file name is empty.",
        }

    if file_name in SILVER_DOMAIN_MAPPING:
        mapped_domain = _normalize_domain_name(SILVER_DOMAIN_MAPPING[file_name])
        target_file = DATA_ROOT / "Data" / "Silver-data" / file_name
        return {
            "mapped": True,
            "mapped_domain": mapped_domain,
            "target_file": target_file,
            "mapped_by": "silver_filename",
        }

    inferred_domain = _infer_domain_from_test_case_name(file_name)
    if inferred_domain and inferred_domain in GOVERNANCE_TEST_CASES:
        target_name = str(GOVERNANCE_TEST_CASES[inferred_domain].get("silver_target"))
        target_file = DATA_ROOT / "Data" / "Silver-data" / target_name
        return {
            "mapped": True,
            "mapped_domain": inferred_domain,
            "target_file": target_file,
            "mapped_by": "domain_prefix",
        }

    return {
        "mapped": False,
        "message": "Unable to map uploaded file to a supported Silver dataset. Use names like sales_*.csv or users_*.csv, or exact Silver file names.",
    }


def _inspect_silver_stale_dates() -> dict:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    utility.targets = [DATA_ROOT / "Data" / "Silver-data"]
    csv_files = utility._list_csv_files()
    today = datetime.now().date()
    files: list[dict] = []

    for file_path in csv_files:
        latest = utility._file_latest_business_date(file_path)
        if latest is None:
            files.append(
                {
                    "file": str(file_path),
                    "has_business_date": False,
                    "latest_business_date": None,
                    "stale": False,
                    "days_stale": None,
                }
            )
            continue

        days_stale = int((today - latest.date()).days)
        files.append(
            {
                "file": str(file_path),
                "has_business_date": True,
                "latest_business_date": latest.isoformat(),
                "stale": days_stale > 0,
                "days_stale": days_stale,
            }
        )

    stale_files = [item for item in files if item.get("stale")]
    return {
        "files_scanned": len(csv_files),
        "stale_files_count": len(stale_files),
        "stale_files": stale_files,
    }


def _run_silver_only_rebase() -> dict:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    utility.targets = [DATA_ROOT / "Data" / "Silver-data"]
    return utility.run(apply_changes=True)


def _shift_silver_dates_by_offset(offset_days: int) -> dict:
    utility = BusinessDateRebaseUtility(data_root=DATA_ROOT)
    utility.targets = [DATA_ROOT / "Data" / "Silver-data"]
    csv_files = utility._list_csv_files()
    if not csv_files:
        return {
            "status": "no_files",
            "message": "No Silver CSV files discovered.",
            "files_scanned": 0,
            "files_changed": 0,
            "shifted_rows_total": 0,
            "results": [],
        }

    delta = timedelta(days=int(offset_days))
    results = []
    changed_files = 0
    shifted_rows_total = 0

    for file_path in csv_files:
        result = utility._rebase_file(file_path=file_path, delta=delta, apply_changes=True)
        if result is None:
            continue
        changed_files += 1
        shifted_rows_total += int(result.shifted_rows)
        results.append(
            {
                "file": result.file,
                "shifted_rows": int(result.shifted_rows),
                "shifted_columns": result.shifted_columns,
                "old_latest_business_date": result.old_latest_business_date,
                "new_latest_business_date": result.new_latest_business_date,
            }
        )

    return {
        "status": "applied_manual_shift",
        "message": "Manual Silver business-date shift completed.",
        "offset_days": int(offset_days),
        "files_scanned": len(csv_files),
        "files_changed": changed_files,
        "shifted_rows_total": shifted_rows_total,
        "results": results,
    }


def _governance_score_snapshot() -> dict:
    summary = governance_engine.governance_summary()
    domains = summary.get("domains") if isinstance(summary, dict) else []
    if not isinstance(domains, list):
        domains = []

    scored = []
    per_domain = {}
    for item in domains:
        if not isinstance(item, dict):
            continue
        domain_name = str(item.get("domain_name") or "").strip()
        score = item.get("governance_score")
        if domain_name and score is not None:
            numeric_score = float(score)
            per_domain[domain_name] = round(numeric_score, 4)
            scored.append(numeric_score)

    avg_score = round(sum(scored) / len(scored), 4) if scored else None
    return {
        "as_of": summary.get("as_of") if isinstance(summary, dict) else None,
        "average_governance_score": avg_score,
        "domain_scores": per_domain,
        "domains_count": len(per_domain),
    }


def _wait_for_rerun_completion(job_id: str, timeout_seconds: int = 300) -> dict:
    deadline = time.time() + max(10, int(timeout_seconds))
    while time.time() < deadline:
        state = _get_rerun_state()
        if state.get("job_id") != job_id:
            time.sleep(0.5)
            continue
        status = str(state.get("status") or "").lower()
        if status in {"completed", "failed"}:
            return state
        time.sleep(1.0)
    return {
        "status": "timeout",
        "job_id": job_id,
        "error": f"Pipeline rerun did not complete within {timeout_seconds} seconds.",
    }


pipeline_chat_agent = PipelineConversationalAgent(
    data_root=DATA_ROOT,
    rerun_trigger=_trigger_pipeline_rerun,
    rerun_status_provider=_get_rerun_state,
    rerun_authorizer=_is_rerun_authorized,
)

governance_engine = GovernanceIntelligenceEngine(
    data_path=DATA_PATH,
    monitoring_history_path=MONITORING_HISTORY_PATH,
)

governance_prioritization_engine = GovernancePrioritizationEngine(
    governance_engine=governance_engine,
)

# Enable CORS for local frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
def get_domain_csv(domain):
    """Helper to load a domain CSV as a DataFrame."""
    file_path = DATA_PATH / f"{domain}/{domain}.csv"
    if not file_path.exists():
        return None, None
    df = pd.read_csv(file_path)
    stat = os.stat(file_path)
    last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return df, last_modified

@app.get("/users")
def get_users():
    df, last_modified = get_domain_csv("users_domain")
    if df is None:
        return {"error": "users_domain not found"}
    return {
        "data": df.to_dict(orient="records"),
        "last_modified": last_modified,
        "row_count": len(df)
    }
@app.get("/products")
def get_products():
    df, last_modified = get_domain_csv("product_domain")
    if df is None:
        return {"error": "product_domain not found"}
    return {
        "data": df.to_dict(orient="records"),
        "last_modified": last_modified,
        "row_count": len(df)
    }
@app.get("/sales")
def get_sales(shop_id: int = None):
    df, last_modified = get_domain_csv("sales_domain")
    if df is None:
        return {"error": "sales_domain not found"}
    if shop_id is not None:
        df = df[df["shop_id"] == shop_id]
    # Calculate total revenue and total orders
    if "final_amount" in df.columns:
        total_revenue = float(df["final_amount"].sum())
    else:
        total_revenue = None
    total_orders = len(df)
    # Simple sales trend: compare last 2 days' sales count
    trend = "unknown"
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(df["transaction_date"])
        last_dates = df["transaction_date"].dt.date.value_counts().sort_index()
        if len(last_dates) >= 2:
            trend = "up" if last_dates.iloc[-1] > last_dates.iloc[-2] else "down"
    return {
        "data": df.to_dict(orient="records"),
        "last_modified": last_modified,
        "row_count": total_orders,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "trend": trend
    }
@app.get("/health")
def get_health():
    """Returns row counts, last modified, and null counts for all domains, including folders with any casing."""
    domain_dirs = [d for d in os.listdir(DATA_PATH) if os.path.isdir(DATA_PATH / d) and d.lower().endswith('_domain')]
    health = {}
    for domain in domain_dirs:
        df, last_modified = get_domain_csv(domain)
        if df is not None:
            health[domain] = {
                "row_count": len(df),
                "last_modified": last_modified,
                "null_counts": df.isnull().sum().to_dict()
            }
        else:
            health[domain] = {"error": "not found"}
    return health

# Optional: endpoint for low stock products
@app.get("/products/low-stock")
def get_low_stock():
    df, _ = get_domain_csv("product_domain")
    if df is None or "stock_count" not in df.columns:
        return []
    low_stock = df[df["stock_count"] < 10]
    return low_stock.to_dict(orient="records")
@app.get("/kpis")
def get_kpis():
    users, _ = get_domain_csv("users_domain")
    products, _ = get_domain_csv("product_domain")
    sales, _ = get_domain_csv("sales_domain")
    if sales is not None and "final_amount" in sales.columns:
        total_sales = float(sales["final_amount"].sum())
    else:
        total_sales = None
    return {
        "user_count": len(users) if users is not None else 0,
        "product_count": len(products) if products is not None else 0,
        "sales_count": len(sales) if sales is not None else 0,
        "total_sales": total_sales
    }

@app.get("/shops")
def get_shops():
    df, _ = get_domain_csv("shop_domain")
    if df is None:
        return []
    return df.to_dict(orient="records")

@app.get("/domains/metadata")
def get_domains_metadata_api():
    health = get_health()
    domains = get_domains_metadata(DATA_PATH, health)
    return JSONResponse(domains)

@app.get("/domain-health/anomalies")
def get_domain_health_anomalies():
    """
    Returns latest health metrics, anomaly flag, score, and timestamp for each domain.
    """
    try:
        history_path = str(MONITORING_HISTORY_PATH)
        if not os.path.exists(history_path):
            return JSONResponse(content={"error": f"File not found: {history_path}"}, status_code=500)
        df = pd.read_csv(history_path)
        # Only keep allowed domains (case-insensitive)
        allowed = [
            "engagement_domain",
            "interaction_domain",
            "product_domain",
            "sales_domain",
            "shop_domain",
            "user_preferences_domain",
            "users_domain"
        ]
        # Normalize domain names to lowercase and strip whitespace
        df["domain_name"] = df["domain_name"].str.lower().str.strip()
        # Fix any known casing issues (e.g., 'interaction_domain' from 'Interaction_domain')
        df["domain_name"] = df["domain_name"].replace({"interaction_domain": "interaction_domain", "interaction_domain": "interaction_domain"})
        # Ensure required columns exist
        required_cols = ["domain_name", "row_count", "null_percentage", "duplicate_percentage", "freshness_hours", "timestamp"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return JSONResponse(content={"error": f"Missing columns in CSV: {missing_cols}"}, status_code=500)
        # If anomaly flag column missing, fill with 0
        if "if_anomaly_flag" not in df.columns:
            df["if_anomaly_flag"] = 0
        df = df[df["domain_name"].isin(allowed)]
        if df.empty:
            return JSONResponse(content={"error": "No matching domain data found in CSV."}, status_code=500)
        # Get latest record per domain
        latest = df.sort_values("timestamp").groupby("domain_name").tail(1)
        result = []
        for _, row in latest.iterrows():
            result.append({
                "domain_name": row["domain_name"],
                "row_count": row["row_count"],
                "null_percentage": row["null_percentage"],
                "duplicate_percentage": row["duplicate_percentage"],
                "freshness_hours": row["freshness_hours"],
                "anomaly_flag": int(row["if_anomaly_flag"]),
                "anomaly_score": row["anomaly_score"] if "anomaly_score" in row else None,
                "timestamp": row["timestamp"]
            })
        return JSONResponse(content={"domains": result})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/overview")
def get_overview():
    """
    Returns summary KPIs and recent anomaly/health status for the dashboard Overview tab.
    """
    # KPIs
    users, users_last = get_domain_csv("users_domain")
    products, products_last = get_domain_csv("product_domain")
    sales, sales_last = get_domain_csv("sales_domain")
    if sales is not None and "final_amount" in sales.columns:
        total_sales = float(sales["final_amount"].sum())
    else:
        total_sales = None
    user_count = len(users) if users is not None else 0
    product_count = len(products) if products is not None else 0
    sales_count = len(sales) if sales is not None else 0

    # Use the latest last_modified among all main domains for last_refreshed
    last_refreshed = max([d for d in [users_last, products_last, sales_last] if d is not None], default=None)

    # Domain health/anomaly summary
    import pandas as pd
    history_path = str(MONITORING_HISTORY_PATH)
    healthy_domains = 0
    anomalous_domains = 0
    recent_anomalies = []
    try:
        if os.path.exists(history_path):
            df = pd.read_csv(history_path)
            if "domain_name" in df.columns and "if_anomaly_flag" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                # Only keep allowed domains
                allowed = [
                    "engagement_domain",
                    "interaction_domain",
                    "product_domain",
                    "sales_domain",
                    "shop_domain",
                    "user_preferences_domain",
                    "users_domain"
                ]
                df["domain_name"] = df["domain_name"].str.lower().str.strip()
                df = df[df["domain_name"].isin(allowed)]
                if not df.empty:
                    latest = df.sort_values("timestamp").groupby("domain_name").tail(1)
                    healthy_domains = int((latest["if_anomaly_flag"] == 0).sum())
                    anomalous_domains = int((latest["if_anomaly_flag"] == 1).sum())
                    # Don't override last_refreshed if already set from file mod times
                    # last_refreshed = str(latest["timestamp"].max())
                    # Recent anomalies (last 5)
                    recent_anomalies = latest[latest["if_anomaly_flag"] == 1][["domain_name", "timestamp"]] \
                        .sort_values("timestamp", ascending=False) \
                        .head(5) \
                        .to_dict(orient="records")
    except Exception as e:
        pass  # Don't break overview if anomaly data is missing

    return {
        "user_count": user_count,
        "product_count": product_count,
        "sales_count": sales_count,
        "total_sales": total_sales,
        "healthy_domains": healthy_domains,
        "anomalous_domains": anomalous_domains,
        "last_refreshed": last_refreshed,
        "recent_anomalies": recent_anomalies
    }

@app.get("/contracts/{contract_name}")
def get_contract(contract_name: str):
    from fastapi.responses import FileResponse
    import logging
    contracts_dir = CONTRACTS_PATH
    contract_path = contracts_dir / contract_name
    logging.warning(f"Trying contracts_dir: {contract_path} (exists: {contract_path.exists()})")
    if contract_path.exists():
        return FileResponse(str(contract_path), media_type="text/yaml", filename=contract_name)
    # Try case-insensitive match in the Contracts folder
    for f in contracts_dir.glob("*.yml"):
        if f.name.lower() == contract_name.lower():
            return FileResponse(str(f), media_type="text/yaml", filename=f.name)
    return JSONResponse(content={"error": f"Contract not found: {contract_name}"}, status_code=404)

@app.get("/api/domain-metrics/{domain_key}")
def get_domain_metrics(domain_key: str):
    file_path = DATA_PATH / f"{domain_key}/{domain_key}.csv"
    if not file_path.exists():
        return {"error": "Domain not found"}
    df = pd.read_csv(file_path)
    total = len(df)
    completeness = round(100 * (1 - df.isnull().any(axis=1).sum() / total), 2) if total else 0
    errors = int(df.isnull().any(axis=1).sum())
    last_refreshed = datetime.fromtimestamp(os.stat(file_path).st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    new_this_month = 0
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        this_month = datetime.now().month
        new_this_month = df[df['created_at'].dt.month == this_month].shape[0]
    return {
        "health": "Healthy" if completeness > 95 else "Warning",
        "lastRefreshed": last_refreshed,
        "metrics": {
            "total": total,
            "newThisMonth": new_this_month,
            "completeness": f"{completeness}%",
            "errors": errors
        }
    }

@app.get("/api/shop-overview")
def shop_overview():
    """
    Returns key shop KPIs for Shop Analysis dashboard:
    - Total Shops Registered
    - Active Shops Today
    - Shops with Sales Today
    - Shops with Missing Sales Data
    - Shops with Stale Updates (>24h)
    """
    shop_path = DATA_PATH / "shop_domain/shop_domain.csv"
    sales_path = DATA_PATH / "sales_domain/sales_domain.csv"
    if not shop_path.exists() or not sales_path.exists():
        return {"error": "Missing data"}
    shops = pd.read_csv(shop_path)
    sales = pd.read_csv(sales_path)
    today = datetime.now().date()

    # Total shops
    total_shops = len(shops)

    # Active shops today (if you have a last_active or similar column)
    active_shops = None
    if 'last_active' in shops.columns:
        shops['last_active'] = pd.to_datetime(shops['last_active'], errors='coerce')
        active_shops = shops[shops['last_active'].dt.date == today].shape[0]

    # Shops with sales today
    shops_with_sales_today = None
    sales_today = pd.DataFrame()
    if 'transaction_date' in sales.columns and 'shop_id' in sales.columns:
        sales['transaction_date'] = pd.to_datetime(sales['transaction_date'], errors='coerce')
        sales_today = sales[sales['transaction_date'].dt.date == today]
        shops_with_sales_today = sales_today['shop_id'].nunique()

    # Shops with missing sales data
    all_shop_ids = set(shops['shop_id']) if 'shop_id' in shops.columns else set()
    sales_today_shop_ids = set(sales_today['shop_id']) if 'shop_id' in sales_today.columns else set()
    missing_sales = len(all_shop_ids - sales_today_shop_ids)

    # Shops with stale updates (>24h)
    stale_updates = None
    if 'last_updated' in shops.columns:
        shops['last_updated'] = pd.to_datetime(shops['last_updated'], errors='coerce')
        stale_cutoff = datetime.now() - pd.Timedelta(hours=24)
        stale_updates = shops[shops['last_updated'] < stale_cutoff].shape[0]

    return {
        "total_shops": total_shops,
        "active_shops": active_shops,
        "shops_with_sales_today": shops_with_sales_today,
        "missing_sales": missing_sales,
        "stale_updates": stale_updates
    }

@app.get("/data-products")
def get_data_products():
    """Return a list of all available domain datasets dynamically, including folders with any casing."""
    domain_dirs = [d for d in os.listdir(DATA_PATH) if os.path.isdir(DATA_PATH / d) and d.lower().endswith('_domain')]
    products = []
    for domain in domain_dirs:
        df, last_modified = get_domain_csv(domain)
        if df is not None:
            products.append({
                "domain": domain,
                "row_count": len(df),
                "last_modified": last_modified,
                "columns": list(df.columns),
                "sample": df.head(3).to_dict(orient="records")
            })
    return {"data": products, "count": len(products)}


@app.get("/governance/summary")
def governance_summary():
    """Return adaptive governance reliability summary for all domains."""
    try:
        return governance_engine.governance_summary()
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@app.get("/governance/domain/{domain_name}")
def governance_domain(domain_name: str):
    """Return detailed adaptive governance metrics for one domain."""
    try:
        return governance_engine.governance_domain(domain_name)
    except ValueError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@app.get("/governance/test-case-comparison/{domain_name}")
def governance_test_case_comparison(domain_name: str):
    normalized_domain = _normalize_domain_name(domain_name)
    latest = _latest_scenario_comparison(normalized_domain)
    return {
        "selected_domain": normalized_domain,
        "latest": latest,
        "history_file": str(SCENARIO_COMPARISON_HISTORY_PATH),
    }


@app.get("/governance/priorities")
def governance_priorities():
    """Return impact-aware governance prioritization across all domains."""
    try:
        return governance_prioritization_engine.priorities_summary()
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@app.get("/governance/priorities/{domain_name}")
def governance_priority_for_domain(domain_name: str):
    """Return impact-aware governance prioritization details for one domain."""
    try:
        return governance_prioritization_engine.priority_for_domain(domain_name)
    except ValueError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)

@app.get("/pipeline-status")
def get_pipeline_status():
    """Return latest status per pipeline/domain from monitoring logs."""
    return pipeline_chat_agent.pipeline_status_snapshot()


@app.get("/pipeline-monitoring/context")
def get_pipeline_monitoring_context():
    """Return structured monitoring context used by the conversational assistant."""
    return pipeline_chat_agent.build_context()


@app.post("/pipeline-monitoring/chat")
def pipeline_monitoring_chat(payload: dict = Body(default={})):
    """Conversational monitoring endpoint powered by semantic intent + Gemini."""
    question = str(payload.get("question") or "").strip()
    session_id = str(payload.get("session_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "").strip()
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()
    return pipeline_chat_agent.answer(
        question,
        session_id=session_id,
        user_id=user_id,
        auth_token=auth_token,
        auth_username=auth_username,
        auth_password=auth_password,
    )


@app.get("/pipeline-monitoring/rerun-status")
def get_pipeline_rerun_status():
    """Return current pipeline rerun execution status."""
    return _get_rerun_state()


@app.get("/admin/stale-simulation-options")
def get_stale_simulation_options():
    return {
        "domains": _domain_simulation_options(),
        "message": "Select a domain to run stale-date simulation on mapped Silver dataset(s).",
    }


@app.get("/admin/governance-test-cases/options")
def get_governance_test_case_options():
    return {
        "workflow": "governance_evaluation_test_cases",
        "test_cases": _governance_test_case_options(),
        "test_case_roots": [str(path) for path in TEST_CASES_ROOTS],
        "message": "Select a prepared Silver test-case, auto-identify its target domain, then rerun pipeline to evaluate governance behavior.",
    }


@app.get("/admin/governance-demo/options")
def get_governance_demo_options(selected_domain: str = "sales_domain"):
    normalized_domain = _normalize_domain_name(selected_domain or "sales_domain")
    configured_domains = sorted([_normalize_domain_name(name) for name in GOVERNANCE_TEST_CASES.keys()])
    scenarios = _governance_demo_scenarios(normalized_domain)
    baseline_file = str((GOVERNANCE_TEST_CASES.get(normalized_domain) or {}).get("baseline_file") or "")
    baseline_source = _resolve_immutable_baseline_source(file_name=baseline_file, domain=normalized_domain) if baseline_file else None

    return {
        "workflow": "professional_governance_demo_framework",
        "selected_domain": normalized_domain,
        "supported_domains": configured_domains,
        "scenarios": scenarios,
        "baseline": {
            "file": baseline_file,
            "exists": baseline_source is not None,
            "source_path": str(baseline_source) if baseline_source is not None else None,
        },
        "message": "Run controlled governance scenarios and restore baseline to demonstrate ADGRI behavior across governance factors.",
    }


@app.post("/admin/governance-demo/run-scenario")
def admin_run_governance_demo_scenario(payload: dict = Body(default={})):
    session_id = str(payload.get("session_id") or "admin-governance-demo-run").strip() or "admin-governance-demo-run"
    user_id = str(payload.get("user_id") or "admin").strip() or "admin"
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()
    selected_domain = _normalize_domain_name(payload.get("selected_domain") or "sales_domain")
    selected_scenario = str(payload.get("selected_scenario") or "").strip()

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for governance demo scenario run.")
    if not selected_scenario:
        raise HTTPException(status_code=400, detail="selected_scenario is required.")

    domain_before = _domain_governance_snapshot(selected_domain)
    load_result = _copy_named_demo_scenario_to_silver(selected_domain, selected_scenario)
    if not load_result.get("supported"):
        raise HTTPException(status_code=400, detail=load_result.get("message") or "Unsupported domain.")
    if not load_result.get("loaded"):
        raise HTTPException(status_code=400, detail=load_result.get("message") or "Unable to load selected scenario dataset.")

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    domain_after = _domain_governance_snapshot(selected_domain)
    comparison = _build_domain_before_after_comparison(selected_domain, selected_scenario, domain_before, domain_after)

    return {
        "workflow": "professional_governance_demo_framework",
        "action": "run_scenario",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "selected_domain": selected_domain,
        "selected_scenario": selected_scenario,
        "scenario_load": load_result,
        "comparison": comparison,
        "pipeline_validation": {
            "rerun_succeeded": pipeline_rerun_succeeded,
            "final_status": rerun_state.get("status"),
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
            "latest_evaluation_time": domain_after.get("governance_evaluation_time"),
            "latest_business_data_date": domain_after.get("latest_business_data_date"),
        },
    }


@app.post("/admin/governance-demo/restore-baseline-rerun")
def admin_restore_governance_demo_baseline(payload: dict = Body(default={})):
    session_id = str(payload.get("session_id") or "admin-governance-demo-restore").strip() or "admin-governance-demo-restore"
    user_id = str(payload.get("user_id") or "admin").strip() or "admin"
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()
    selected_domain = _normalize_domain_name(payload.get("selected_domain") or "sales_domain")

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for baseline restore workflow.")

    domain_before = _domain_governance_snapshot(selected_domain)
    restore_result = _restore_domain_baseline_to_silver(selected_domain)
    if not restore_result.get("supported"):
        raise HTTPException(status_code=400, detail=restore_result.get("message") or "Unsupported domain.")
    if not restore_result.get("restored"):
        raise HTTPException(status_code=400, detail=restore_result.get("message") or "Unable to restore baseline dataset.")

    output_reset = _reset_domain_output_state(selected_domain)
    governance_state_reset = _reset_domain_governance_state(selected_domain)

    domain_output_csv = DATA_PATH / selected_domain / f"{selected_domain}.csv"
    output_exists_before = domain_output_csv.exists()

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    pipeline_log_reset = _reset_domain_pipeline_log_state(selected_domain)
    clean_history_seed = _seed_clean_domain_history_from_output(selected_domain)

    domain_after = _domain_governance_snapshot(selected_domain)
    output_exists_after = domain_output_csv.exists()
    domain_overwritten = bool(pipeline_rerun_succeeded and output_exists_after)
    governance_recomputed = bool(
        pipeline_rerun_succeeded
        and domain_after.get("governance_evaluation_time") is not None
    )

    comparison = _build_domain_before_after_comparison(
        selected_domain=selected_domain,
        selected_scenario="sales_baseline",
        before=domain_before,
        after=domain_after,
    )
    scenario_comparison = _record_scenario_restore(
        selected_domain=selected_domain,
        restored_score=domain_after.get("adgri"),
    )

    return {
        "workflow": "professional_governance_demo_framework",
        "action": "restore_baseline",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "selected_domain": selected_domain,
        "selected_scenario": "sales_baseline",
        "baseline_restore": restore_result,
        "restore_summary": {
            "baseline_source_file_used": restore_result.get("source_file"),
            "silver_replaced": bool(restore_result.get("silver_replaced")),
            "domain_overwritten": domain_overwritten,
            "governance_recomputed": governance_recomputed,
            "adgri_before_restore": domain_before.get("adgri"),
            "adgri_after_restore": domain_after.get("adgri"),
            "domain_output_exists_before_rerun": output_exists_before,
            "domain_output_exists_after_rerun": output_exists_after,
        },
        "state_reset": {
            "domain_output_reset": output_reset,
            "governance_state_reset": governance_state_reset,
            "pipeline_log_reset": pipeline_log_reset,
            "clean_history_seed": clean_history_seed,
        },
        "scenario_test_case_comparison": scenario_comparison,
        "comparison": comparison,
        "pipeline_validation": {
            "rerun_succeeded": pipeline_rerun_succeeded,
            "final_status": rerun_state.get("status"),
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
            "latest_evaluation_time": domain_after.get("governance_evaluation_time"),
            "latest_business_data_date": domain_after.get("latest_business_data_date"),
        },
    }


@app.post("/admin/governance-test-cases/load-and-rerun")
def admin_load_governance_test_case_and_rerun(payload: dict = Body(default={})):
    session_id = str(payload.get("session_id") or "admin-governance-evaluation").strip() or "admin-governance-evaluation"
    user_id = str(payload.get("user_id") or "admin").strip() or "admin"
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()
    selected_test_case = str(payload.get("selected_test_case") or "").strip()

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for governance test-case workflow.")

    if not selected_test_case:
        raise HTTPException(status_code=400, detail="selected_test_case is required.")

    selected_domain = _infer_domain_from_test_case_name(selected_test_case)
    if not selected_domain:
        raise HTTPException(status_code=400, detail="Unable to infer target domain from selected_test_case file name.")

    if selected_domain not in GOVERNANCE_TEST_CASES:
        raise HTTPException(status_code=400, detail=f"Inferred domain '{selected_domain}' is not configured for governance test-case workflow yet.")

    governance_before = _governance_score_snapshot()
    domain_before = _domain_governance_snapshot(selected_domain)

    load_result = _copy_governance_test_case_to_silver(selected_test_case)
    if not load_result.get("supported"):
        raise HTTPException(status_code=400, detail=load_result.get("message") or "Unsupported domain.")
    if not load_result.get("loaded"):
        raise HTTPException(status_code=400, detail=load_result.get("message") or "Unable to load selected test-case.")

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    domain_after = _domain_governance_snapshot(selected_domain)
    governance_after = _governance_score_snapshot()

    return {
        "workflow": "governance_evaluation_test_cases",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "selected_test_case": selected_test_case,
        "selected_domain": selected_domain,
        "test_case_load": load_result,
        "pipeline_rerun": {
            "trigger": rerun_start,
            "final_status": rerun_state.get("status"),
            "succeeded": pipeline_rerun_succeeded,
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
        },
        "governance_refresh": {
            "latest_refresh_time": governance_after.get("as_of"),
            "score_before": governance_before.get("average_governance_score"),
            "score_after": governance_after.get("average_governance_score"),
            "before": governance_before,
            "after": governance_after,
        },
        "domain_evaluation": {
            "selected_test_case": selected_test_case,
            "domain": selected_domain,
            "before": domain_before,
            "after": domain_after,
            "latest_business_data_date": domain_after.get("latest_business_data_date"),
            "freshness_instability": domain_after.get("freshness_instability"),
            "adgri": domain_after.get("adgri"),
            "top_reason": domain_after.get("top_reason"),
            "explanation": domain_after.get("explanation"),
            "comparison": {
                "latest_business_data_date_before": domain_before.get("latest_business_data_date"),
                "latest_business_data_date_after": domain_after.get("latest_business_data_date"),
                "freshness_instability_before": domain_before.get("freshness_instability"),
                "freshness_instability_after": domain_after.get("freshness_instability"),
                "adgri_before": domain_before.get("adgri"),
                "adgri_after": domain_after.get("adgri"),
                "top_reason_before": domain_before.get("top_reason"),
                "top_reason_after": domain_after.get("top_reason"),
            },
        },
    }


@app.post("/admin/governance-test-cases/upload-and-rerun")
def admin_upload_governance_test_case_and_rerun(
    upload_file: UploadFile = File(...),
    session_id: str = Form("admin-governance-upload"),
    user_id: str = Form("admin"),
    auth_token: str = Form(""),
    auth_username: str = Form(""),
    auth_password: str = Form(""),
):
    session_id = str(session_id or "admin-governance-upload").strip() or "admin-governance-upload"
    user_id = str(user_id or "admin").strip() or "admin"
    auth_token = str(auth_token or "").strip()
    auth_username = str(auth_username or "").strip()
    auth_password = str(auth_password or "").strip()

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for governance upload workflow.")

    incoming_file_name = Path(str(upload_file.filename or "").strip()).name
    mapping = _map_uploaded_file_to_silver_target(incoming_file_name)
    if not mapping.get("mapped"):
        raise HTTPException(status_code=400, detail=mapping.get("message") or "Unable to map uploaded file.")

    mapped_domain = str(mapping.get("mapped_domain"))
    target_file = mapping.get("target_file")
    if not isinstance(target_file, Path):
        raise HTTPException(status_code=400, detail="Mapped target file path is invalid.")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target_file.open("wb") as destination:
            shutil.copyfileobj(upload_file.file, destination)
    finally:
        upload_file.file.close()

    replaced_in_silver = target_file.exists() and target_file.stat().st_size > 0

    governance_before = _governance_score_snapshot()
    domain_before = _domain_governance_snapshot(mapped_domain)

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    domain_after = _domain_governance_snapshot(mapped_domain)
    governance_after = _governance_score_snapshot()
    scenario_comparison = _record_scenario_test_case_run(
        selected_domain=mapped_domain,
        baseline_score=domain_before.get("adgri"),
        scenario_score=domain_after.get("adgri"),
    )

    return {
        "workflow": "governance_upload_replace_rerun",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "uploaded_file_name": incoming_file_name,
        "mapped_domain": mapped_domain,
        "replaced_in_silver": replaced_in_silver,
        "silver_target_file": str(target_file),
        "mapping_method": mapping.get("mapped_by"),
        "pipeline_rerun": {
            "trigger": rerun_start,
            "final_status": rerun_state.get("status"),
            "succeeded": pipeline_rerun_succeeded,
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
        },
        "governance_refresh": {
            "latest_refresh_time": governance_after.get("as_of"),
            "score_before": governance_before.get("average_governance_score"),
            "score_after": governance_after.get("average_governance_score"),
        },
        "live_governance_trend": {
            "selected_domain": mapped_domain,
            "trend_label": "Live Governance Trend",
            "risk_trend": domain_before.get("risk_trend") or [],
        },
        "scenario_test_case_comparison": scenario_comparison,
        "domain_evaluation": {
            "before": domain_before,
            "after": domain_after,
        },
    }


@app.post("/admin/rebase-silver-rerun-governance")
def admin_rebase_silver_rerun_governance(payload: dict = Body(default={})):
    """Admin-only maintenance utility: rebase Silver dates, rerun pipeline, refresh governance outputs."""
    session_id = str(payload.get("session_id") or "admin-maintenance").strip() or "admin-maintenance"
    user_id = str(payload.get("user_id") or "admin").strip() or "admin"
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()
    simulation_days_offset_raw = payload.get("simulation_days_offset")
    simulation_domain = _normalize_domain_name(
        payload.get("simulation_domain") or payload.get("selected_domain") or ""
    )

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for maintenance action.")

    if not simulation_domain:
        raise HTTPException(status_code=400, detail="simulation_domain is required for domain-specific stale-date simulation.")

    available_domains = {item.get("domain") for item in _domain_simulation_options()}
    if simulation_domain not in available_domains:
        raise HTTPException(status_code=400, detail=f"Unsupported simulation_domain: {simulation_domain}")

    simulation_days_offset = 0
    if simulation_days_offset_raw not in (None, ""):
        try:
            simulation_days_offset = int(simulation_days_offset_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="simulation_days_offset must be an integer.")
        if abs(simulation_days_offset) > 3650:
            raise HTTPException(status_code=400, detail="simulation_days_offset is out of allowed range (±3650).")

    governance_before = _governance_score_snapshot()
    domain_governance_before = _domain_governance_snapshot(simulation_domain)
    stale_inspection = _inspect_domain_silver_stale_dates(simulation_domain)

    if not stale_inspection.get("supported"):
        return {
            "workflow": "rebase_silver_then_rerun_then_refresh_governance",
            "executed_at": datetime.now().isoformat(timespec="seconds"),
            "simulation_domain": simulation_domain,
            "simulation_supported": False,
            "message": "Stale-date simulation is not supported for this domain because no business-date field is available.",
            "silver_inspection": stale_inspection,
            "domain_simulation": {
                "domain": simulation_domain,
                "supported": False,
                "before": domain_governance_before,
                "after": domain_governance_before,
            },
        }

    rebase_result = _run_domain_silver_rebase(simulation_domain, simulation_days_offset)
    rebase_mode = "manual_shift" if simulation_days_offset != 0 else "normalize_to_today"
    rebased_files = [item.get("file") for item in rebase_result.get("results", []) if item.get("file")]

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    domain_governance_after = _domain_governance_snapshot(simulation_domain)
    governance_after = _governance_score_snapshot()

    return {
        "workflow": "rebase_silver_then_rerun_then_refresh_governance",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "simulation_domain": simulation_domain,
        "simulation_supported": True,
        "silver_inspection": stale_inspection,
        "silver_rebase": {
            "mode": rebase_mode,
            "domain": simulation_domain,
            "requested_offset_days": simulation_days_offset,
            "status": rebase_result.get("status"),
            "files_scanned": rebase_result.get("files_scanned"),
            "files_changed": rebase_result.get("files_changed"),
            "rebased_files": rebased_files,
            "latest_business_data_date_before": rebase_result.get("old_latest_business_date"),
            "latest_business_data_date_after": rebase_result.get("new_latest_business_date"),
        },
        "pipeline_rerun": {
            "trigger": rerun_start,
            "final_status": rerun_state.get("status"),
            "succeeded": pipeline_rerun_succeeded,
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
        },
        "governance_refresh": {
            "latest_refresh_time": governance_after.get("as_of"),
            "score_before": governance_before.get("average_governance_score"),
            "score_after": governance_after.get("average_governance_score"),
            "before": governance_before,
            "after": governance_after,
        },
        "domain_simulation": {
            "domain": simulation_domain,
            "supported": True,
            "before": domain_governance_before,
            "after": domain_governance_after,
            "latest_business_data_date_before": domain_governance_before.get("latest_business_data_date"),
            "latest_business_data_date_after": domain_governance_after.get("latest_business_data_date"),
            "adgri_before": domain_governance_before.get("adgri"),
            "adgri_after": domain_governance_after.get("adgri"),
            "freshness_instability_before": domain_governance_before.get("freshness_instability"),
            "freshness_instability_after": domain_governance_after.get("freshness_instability"),
            "top_reason_before": domain_governance_before.get("top_reason"),
            "top_reason_after": domain_governance_after.get("top_reason"),
        },
    }


@app.post("/admin/governance/apply-valid-corrections-rerun")
def admin_apply_valid_corrections_and_rerun(payload: dict = Body(default={})):
    session_id = str(payload.get("session_id") or "admin-governance-correction").strip() or "admin-governance-correction"
    user_id = str(payload.get("user_id") or "admin").strip() or "admin"
    auth_token = str(payload.get("auth_token") or "").strip()
    auth_username = str(payload.get("auth_username") or "").strip()
    auth_password = str(payload.get("auth_password") or "").strip()

    if not _is_rerun_authorized(session_id, user_id, auth_token, auth_username, auth_password):
        raise HTTPException(status_code=403, detail="Admin authorization failed for governance correction workflow.")

    target_domains = ["sales_domain", "product_domain", "users_domain"]
    before_by_domain = {domain: _domain_governance_snapshot(domain) for domain in target_domains}

    correction_actions = [correct_sales(), correct_product(), correct_users()]

    rerun_start = _trigger_pipeline_rerun()
    if rerun_start.get("status") == "already_running":
        raise HTTPException(status_code=409, detail="Pipeline rerun is already running. Try again once it completes.")

    rerun_state = _wait_for_rerun_completion(str(rerun_start.get("job_id") or ""), timeout_seconds=600)
    rerun_summary = rerun_state.get("summary") if isinstance(rerun_state, dict) else None
    pipeline_rerun_succeeded = bool(
        str(rerun_state.get("status") or "").lower() == "completed"
        and isinstance(rerun_summary, dict)
        and str(rerun_summary.get("status") or "").upper() == "SUCCESS"
    )

    after_by_domain = {domain: _domain_governance_snapshot(domain) for domain in target_domains}

    domain_comparison = []
    for domain in target_domains:
        before = before_by_domain.get(domain) or {}
        after = after_by_domain.get(domain) or {}
        domain_comparison.append(
            {
                "domain": domain,
                "adgri_before": before.get("adgri"),
                "adgri_after": after.get("adgri"),
                "freshness_instability_before": before.get("freshness_instability"),
                "freshness_instability_after": after.get("freshness_instability"),
                "distribution_instability_before": before.get("distribution_instability"),
                "distribution_instability_after": after.get("distribution_instability"),
                "volume_instability_before": before.get("volume_instability"),
                "volume_instability_after": after.get("volume_instability"),
                "top_reason_before": before.get("top_reason"),
                "top_reason_after": after.get("top_reason"),
                "low_score_reason_before": before.get("low_score_reason_label"),
                "low_score_reason_after": after.get("low_score_reason_label"),
                "note": next(
                    (item.get("note") for item in correction_actions if _normalize_domain_name(item.get("domain", "")) == domain),
                    None,
                ),
            }
        )

    return {
        "workflow": "apply_valid_silver_corrections_then_rerun",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "message": "Applied valid Silver data corrections (freshness/distribution), reran pipeline, and refreshed governance outputs.",
        "corrections": correction_actions,
        "pipeline_rerun": {
            "trigger": rerun_start,
            "final_status": rerun_state.get("status"),
            "succeeded": pipeline_rerun_succeeded,
            "summary": rerun_summary,
            "error": rerun_state.get("error"),
        },
        "domains": domain_comparison,
    }