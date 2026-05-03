"""
University demo runner: baseline -> three uploads -> print Chroma-backed outcomes.

Run from repo root:
  cd backend
  python scripts/run_semantic_drift_demo.py

Uses a fresh Chroma directory if SEMANTIC_DRIFT_CHROMA_DEMO_DIR is set; otherwise default module path.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Ensure `src` is on path when executed as `python scripts/run_semantic_drift_demo.py`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

DEMO_DIR = BACKEND_ROOT / "src" / "services" / "semantic_drift" / "demo_data"


def main() -> None:
    demo_chroma = os.environ.get("SEMANTIC_DRIFT_CHROMA_DEMO_DIR")
    if demo_chroma:
        p = Path(demo_chroma)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)
        import src.services.semantic_drift.chromadb_store as cs

        cs.CHROMA_PERSIST_DIR = p

    from src.services.semantic_drift import baseline_service, ingestion_service
    from src.services.semantic_drift import chromadb_store

    ds = "fashion_sales_demo"
    print("=== 1) Create baseline (baseline_sales.csv) ===")
    r0 = baseline_service.create_baseline_from_csv(ds, DEMO_DIR / "baseline_sales.csv", created_by="demo")
    print(r0)

    print("\n=== 2) Ingest no_drift_upload.csv (expect: accepted) ===")
    r1 = ingestion_service.ingest_new_dataset(ds, DEMO_DIR / "no_drift_upload.csv")
    print({k: r1[k] for k in ("batch_id", "status", "accepted_rows", "message")})

    print("\n=== 3) Ingest column_rename_upload.csv (expect: accepted_after_repair) ===")
    r2 = ingestion_service.ingest_new_dataset(ds, DEMO_DIR / "column_rename_upload.csv")
    print({k: r2[k] for k in ("batch_id", "status", "accepted_rows", "repair_actions", "message")})

    print("\n=== 4) Ingest semantic_drift_upload.csv (expect: quarantined) ===")
    r3 = ingestion_service.ingest_new_dataset(ds, DEMO_DIR / "semantic_drift_upload.csv")
    print({k: r3[k] for k in ("batch_id", "status", "accepted_rows", "rejected_rows", "message")})

    client = chromadb_store.get_chroma_client()
    print("\n=== Final sales_transactions (Chroma) ===")
    for row in chromadb_store.list_sales_transactions(client):
        print(row)

    print("\n=== Quarantine records ===")
    for row in chromadb_store.list_quarantine(client):
        print(row)

    print("\n=== Last batch drift (column-level) ===")
    for row in chromadb_store.list_drift_results_for_batch(client, r3["batch_id"]):
        print(row.get("column_name"), row.get("decision"), row.get("similarity_score"), row.get("explanation"))


if __name__ == "__main__":
    main()
