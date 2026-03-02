from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
from pathlib import Path
import os
from datetime import datetime
from domains_metadata_loader import get_domains_metadata
from fastapi.responses import FileResponse
from threading import Thread
import time

# Path to your local Data Mesh domains
DATA_PATH = Path(__file__).parent.parent / "../Data_Mesh_Domains"
# NOTE: Make sure to run the backend from the dashboard/backend directory, or adjust DATA_PATH as needed.

# List of domains
DOMAINS = ["users_domain", "product_domain", "sales_domain", "shop_domain"]

app = FastAPI()

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
        history_path = os.path.join(os.path.dirname(__file__), "../../monitoring/domain_health_history.csv")
        history_path = os.path.abspath(history_path)
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
    import os
    import pandas as pd
    history_path = os.path.join(os.path.dirname(__file__), "../../monitoring/domain_health_history.csv")
    history_path = os.path.abspath(history_path)
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
    # Use absolute path to Contracts folder at the project root
    contracts_dir = Path(__file__).parent.parent.parent / "Contracts"
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

# --- Pipeline Monitoring Agent (Simulated) ---
pipeline_status = {
    "ETL_Ingest": {"last_run": None, "status": "unknown", "duration": None, "error": None},
    "Data_Cleaning": {"last_run": None, "status": "unknown", "duration": None, "error": None},
    "ML_Training": {"last_run": None, "status": "unknown", "duration": None, "error": None},
}

def simulate_pipeline_agent():
    while True:
        now = datetime.now().isoformat()
        # Simulate ETL job (always succeeds)
        pipeline_status["ETL_Ingest"].update({
            "last_run": now,
            "status": "success",
            "duration": 120,
            "error": None
        })
        # Simulate Data Cleaning (randomly fails)
        import random
        if random.random() < 0.8:
            pipeline_status["Data_Cleaning"].update({
                "last_run": now,
                "status": "success",
                "duration": 60,
                "error": None
            })
        else:
            pipeline_status["Data_Cleaning"].update({
                "last_run": now,
                "status": "failed",
                "duration": 65,
                "error": "Null value spike detected"
            })
        # Simulate ML Training (delayed every 3rd run)
        if int(datetime.now().second) % 3 == 0:
            pipeline_status["ML_Training"].update({
                "last_run": now,
                "status": "delayed",
                "duration": 300,
                "error": "Training not started on schedule"
            })
        else:
            pipeline_status["ML_Training"].update({
                "last_run": now,
                "status": "success",
                "duration": 250,
                "error": None
            })
        time.sleep(10)  # Simulate periodic check every 10 seconds

# Start the agent in a background thread
Thread(target=simulate_pipeline_agent, daemon=True).start()

@app.get("/pipeline-status")
def get_pipeline_status():
    """Return the current status of all monitored pipelines/jobs."""
    return pipeline_status