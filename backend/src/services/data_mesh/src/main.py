from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
from pathlib import Path
import os
from datetime import datetime
import importlib.util
import json
import sys
from threading import Lock, Thread
import uuid
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

# Paths for Data Mesh assets (safe after folder relocation)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data"
DATA_PATH = DATA_ROOT / "Data_Mesh_Domains"
CONTRACTS_PATH = DATA_ROOT / "Contracts"
MONITORING_HISTORY_PATH = DATA_ROOT / "monitoring" / "domain_health_history.csv"
CREDENTIALS_PATH = DATA_ROOT / "monitoring" / "config" / "credentials.json"

# List of domains
DOMAINS = ["users_domain", "product_domain", "sales_domain", "shop_domain"]

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