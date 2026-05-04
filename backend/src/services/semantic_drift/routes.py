"""
FastAPI routes for semantic drift detection + Chroma-backed ingestion.

Mounted under `/api/semantic-drift` from the main app (see `app.py`).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.services.semantic_drift import baseline_service
from src.services.semantic_drift import chromadb_store
from src.services.semantic_drift import export_service
from src.services.semantic_drift import ingestion_service
from src.services.semantic_drift.healing_dashboard_service import (
    build_aggregate_dashboard,
    build_dashboard_for_run,
    featureops_registry_from_backend_src,
)

router = APIRouter()


@router.post(
    "/baseline/create",
    summary="Create semantic baseline from CSV",
    description="Reads CSV, builds rule-based semantic column profiles, stores baseline + columns in ChromaDB.",
)
async def create_baseline(
    dataset_name: str = Form(..., description="Logical dataset key, e.g. fashion_sales_demo"),
    created_by: str = Form("system"),
    file: UploadFile = File(..., description="Approved baseline CSV"),
) -> Dict[str, Any]:
    suffix = Path(file.filename or "baseline.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        summary = baseline_service.create_baseline_from_csv(dataset_name, tmp_path, created_by=created_by)
        return {"status": "ok", **summary}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post(
    "/baseline/approve-governance",
    summary="Approve a new baseline version (human governance)",
    description="Deactivates prior baselines for the dataset and registers this CSV as the new active version.",
)
async def approve_baseline_version(
    dataset_name: str = Form(...),
    created_by: str = Form("governance_user"),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    suffix = Path(file.filename or "baseline.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        summary = baseline_service.approve_new_baseline_version(dataset_name, tmp_path, created_by=created_by)
        return {"status": "ok", **summary}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get(
    "/baseline/{dataset_name}",
    summary="Get active baseline and column profiles",
)
def get_baseline(dataset_name: str) -> Dict[str, Any]:
    b = baseline_service.get_active_baseline(dataset_name)
    if not b:
        raise HTTPException(status_code=404, detail="No active baseline for this dataset_name.")
    cols = baseline_service.get_baseline_column_profiles(dataset_name)
    return {"status": "ok", "baseline": b, "column_profiles": cols}


@router.post(
    "/ingest",
    summary="Ingest a new CSV with drift detection + self-healing",
    description="Full workflow: profile, drift vs active baseline, heal if safe, append rows to Chroma or quarantine.",
)
async def ingest(dataset_name: str = Form(...), file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = Path(file.filename or "upload.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        result = ingestion_service.ingest_new_dataset(dataset_name, tmp_path)
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get(
    "/runs/{run_id}/healing-dashboard",
    summary="Simple healing dashboard for one drift run or all runs",
    description=(
        "Returns KPIs plus three lists: auto_healed, needs_review, quarantined. "
        "Stable READY+NONE columns are omitted from lists but counted in single-run KPI `stable_columns`. "
        "Use run_id `all` to merge every persisted FeatureOps drift run (newest wins per dataset+column)."
    ),
)
def healing_dashboard(run_id: str) -> Dict[str, Any]:
    reg = featureops_registry_from_backend_src()
    key = str(run_id or "").strip().lower()
    if key == "all":
        payload = build_aggregate_dashboard(reg)
        return {"status": "ok", **payload}
    for run in reg.list_drift_runs():
        if str(run.get("run_id")) == str(run_id):
            payload = build_dashboard_for_run(run)
            return {"status": "ok", **payload}
    raise HTTPException(status_code=404, detail=f"Unknown drift run_id: {run_id}")


@router.get("/results/{batch_id}", summary="Drift results for an ingestion batch")
def drift_results(batch_id: str) -> Dict[str, Any]:
    client = chromadb_store.get_chroma_client()
    rows = chromadb_store.list_drift_results_for_batch(client, batch_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No drift results for this batch_id.")
    return {"status": "ok", "batch_id": batch_id, "drift_results": rows}


@router.get("/quarantine", summary="List quarantined ingestion batches")
def quarantine_list() -> Dict[str, Any]:
    client = chromadb_store.get_chroma_client()
    rows = chromadb_store.list_quarantine(client)
    return {"status": "ok", "quarantined": rows}


@router.get("/sales", summary="Rows accepted into sales_transactions (ChromaDB)")
def sales_rows() -> Dict[str, Any]:
    client = chromadb_store.get_chroma_client()
    rows = chromadb_store.list_sales_transactions(client)
    return {"status": "ok", "rows": rows}


@router.get("/batches/{batch_id}", summary="Ingestion batch metadata")
def batch_meta(batch_id: str) -> Dict[str, Any]:
    client = chromadb_store.get_chroma_client()
    meta = chromadb_store.get_batch(client, batch_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown batch_id")
    return {"status": "ok", "batch": meta}


@router.get(
    "/export/sales",
    summary="Download Chroma sales_transactions as CSV (final rows after drift + repairs)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_sales_csv(
    batch_id: Optional[str] = Query(
        default=None,
        description="If set, only rows for this ingestion_batch_id (one ingest’s final table).",
    ),
) -> Response:
    client = chromadb_store.get_chroma_client()
    if batch_id:
        rows = chromadb_store.list_sales_transactions_for_batch(client, batch_id)
        filename = f"sales_transactions_batch_{batch_id}.csv"
    else:
        rows = chromadb_store.list_sales_transactions(client)
        filename = "sales_transactions_chroma_all.csv"
    if not rows:
        raise HTTPException(status_code=404, detail="No sales rows in Chroma for this query.")
    body = export_service.dict_rows_to_csv_bytes(rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/export/drift-results/{batch_id}",
    summary="Download drift / interpretation results for a batch as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_drift_results_csv(batch_id: str) -> Response:
    client = chromadb_store.get_chroma_client()
    rows = chromadb_store.list_drift_results_for_batch(client, batch_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No drift results for this batch_id.")
    flat = [export_service.flatten_drift_row(r) for r in rows]
    body = export_service.dict_rows_to_csv_bytes(flat)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="drift_results_{batch_id}.csv"'},
    )


@router.get(
    "/export/batches",
    summary="Download ingestion batch metadata as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_batches_csv() -> Response:
    client = chromadb_store.get_chroma_client()
    rows = chromadb_store.list_ingestion_batches(client)
    if not rows:
        raise HTTPException(status_code=404, detail="No ingestion batches in Chroma.")
    body = export_service.dict_rows_to_csv_bytes(rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ingestion_batches_chroma.csv"'},
    )
