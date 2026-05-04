"""
End-to-end ingestion: profile -> drift -> (self-heal loop) -> ChromaDB append or quarantine.

Accepted / repaired rows receive unique `record_id` values in the `sales_transactions` collection.
Quarantined uploads are recorded in `quarantined_datasets` without sales inserts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.services.semantic_drift import chromadb_store
from src.services.semantic_drift import baseline_service
from src.services.semantic_drift import profiling_service
from src.services.semantic_drift import drift_detection_service
from src.services.semantic_drift import self_healing_service


def create_ingestion_batch(
    client,
    dataset_name: str,
    total_rows: int,
    baseline_version: str,
    status: str,
    accepted_rows: int,
    rejected_rows: int,
) -> str:
    batch_id = chromadb_store.new_id("bat")
    now = datetime.now(timezone.utc).isoformat()
    chromadb_store.upsert_batch(
        client,
        batch_id=batch_id,
        dataset_name=dataset_name,
        baseline_version=baseline_version,
        uploaded_at=now,
        status=status,
        total_rows=total_rows,
        accepted_rows=accepted_rows,
        rejected_rows=rejected_rows,
    )
    return batch_id


def save_drift_results(client, batch_id: str, baseline_version: str, drift_results: List[Dict[str, Any]]) -> None:
    chromadb_store.save_drift_results(client, batch_id, baseline_version, drift_results)


def quarantine_dataset(client, batch_id: str, dataset_name: str, reason: str, suggested_action: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    chromadb_store.upsert_quarantine(client, batch_id, dataset_name, reason, suggested_action, now)


def append_to_sales_transactions(
    client,
    df: pd.DataFrame,
    batch_id: str,
    baseline_version: str,
    drift_status: str,
    repair_action: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows_out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        rec = {
            "record_id": chromadb_store.new_id("rec"),
            "customer_id": str(row.get("customer_id", "")),
            "order_id": str(row.get("order_id", "")),
            "sales_amount": float(row.get("sales_amount", 0) or 0),
            "quantity": int(float(row.get("quantity", 0) or 0)),
            "discount_amount": float(row.get("discount_amount", 0) or 0) if pd.notna(row.get("discount_amount")) else 0.0,
            "order_date": str(row.get("order_date", "")),
            "ingestion_batch_id": batch_id,
            "baseline_version": baseline_version,
            "drift_status": drift_status,
            "repair_action": repair_action,
            "ingested_at": now,
        }
        rows_out.append(rec)
    chromadb_store.append_sales_rows(client, rows_out)
    return len(rows_out)


def ingest_new_dataset(dataset_name: str, csv_path: str | Path) -> Dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    client = chromadb_store.get_chroma_client()
    baseline = baseline_service.get_active_baseline(dataset_name)
    if not baseline:
        raise ValueError(f"No active baseline for dataset_name={dataset_name!r}. Create baseline first.")

    baseline_profiles = baseline_service.get_baseline_column_profiles(dataset_name)
    baseline_version = str(baseline.get("baseline_version") or "v1")

    df = pd.read_csv(path)
    total_rows = int(len(df))
    batch_id = create_ingestion_batch(
        client, dataset_name, total_rows, baseline_version, status="processing", accepted_rows=0, rejected_rows=0
    )

    repair_actions: List[str] = []

    def export_download_paths() -> Dict[str, str]:
        """Relative API paths to download Chroma tables for this batch (GET, CSV attachment)."""
        root = "/api/semantic-drift/export"
        return {
            "sales_final_csv": f"{root}/sales?batch_id={batch_id}",
            "drift_results_csv": f"{root}/drift-results/{batch_id}",
            "all_sales_csv": f"{root}/sales",
            "ingestion_batches_csv": f"{root}/batches",
        }

    def finalize(
        status: str,
        accepted: int,
        rejected: int,
        msg: str,
        drift: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        chromadb_store.upsert_batch(
            client,
            batch_id=batch_id,
            dataset_name=dataset_name,
            baseline_version=baseline_version,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            total_rows=total_rows,
            accepted_rows=accepted,
            rejected_rows=rejected,
        )
        save_drift_results(client, batch_id, baseline_version, drift)
        return {
            "batch_id": batch_id,
            "dataset_name": dataset_name,
            "status": status,
            "total_rows": total_rows,
            "accepted_rows": accepted,
            "rejected_rows": rejected,
            "baseline_version": baseline_version,
            "drift_results": drift,
            "repair_actions": repair_actions,
            "message": msg,
            "export_download_paths": export_download_paths(),
        }

    _, rename_probe = self_healing_service.rename_known_columns(df)
    needs_safe_rename = len(rename_probe) > 0

    profile1 = profiling_service.profile_dataframe(df, dataset_name)
    drift1 = drift_detection_service.detect_dataset_drift(baseline_profiles, profile1, upload_df=df)
    agg1 = drift_detection_service.aggregate_decision(drift1)

    if agg1 == "HUMAN_REVIEW":
        return finalize(
            "pending_human_review",
            0,
            total_rows,
            "Interpretation drift: human review required before ingestion (see drift_results[].interpretation).",
            drift1,
        )

    if agg1 == "QUARANTINE":
        reason = "; ".join(
            f"{r.get('column_name')}: {r.get('explanation')}" for r in drift1 if r.get("decision") == "QUARANTINE"
        )[:1800]
        quarantine_dataset(
            client,
            batch_id,
            dataset_name,
            reason or "Semantic drift or unknown columns.",
            "Review with data owner; update baseline if change is intentional.",
        )
        return finalize("quarantined", 0, total_rows, "Quarantined: semantic drift or unsafe columns.", drift1)

    # Self-heal path: drift asks for it, OR we still have safe synonym renames to apply for schema alignment.
    if agg1 == "SELF_HEAL" or needs_safe_rename:
        df2, actions, _ok = self_healing_service.apply_self_healing(df, baseline_profiles, drift_results=drift1)
        repair_actions.extend(actions)
        profile2 = profiling_service.profile_dataframe(df2, dataset_name)
        drift2 = drift_detection_service.detect_dataset_drift(baseline_profiles, profile2, upload_df=df2)
        agg2 = drift_detection_service.aggregate_decision(drift2)

        if agg2 == "QUARANTINE":
            quarantine_dataset(
                client,
                batch_id,
                dataset_name,
                "Drift remained after self-healing (or unsafe semantic shift).",
                "Inspect upload; quarantine prevents poisoned analytics.",
            )
            return finalize("quarantined", 0, total_rows, "Quarantined after self-heal attempt.", drift2)

        drift_status = "repaired" if repair_actions else "no_drift"
        repair_tag = ";".join(repair_actions) if repair_actions else "none"
        accepted = append_to_sales_transactions(client, df2, batch_id, baseline_version, drift_status, repair_tag)
        status = "accepted_after_repair" if repair_actions else "accepted"
        msg = (
            "Self-healing applied; rows appended to ChromaDB with drift_status=repaired."
            if repair_actions
            else "Rows appended; no repairs required after normalization."
        )
        return finalize(status, accepted, 0, msg, drift2)

    # Pure APPEND (no synonym renames needed)
    accepted = append_to_sales_transactions(client, df, batch_id, baseline_version, "no_drift", "none")
    return finalize("accepted", accepted, 0, "All columns aligned with baseline; rows appended to ChromaDB.", drift1)
