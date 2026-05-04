"""
Baseline lifecycle: read approved CSV, attach rule-based semantic profiles, persist to ChromaDB.

baseline_version starts at v1; human-approved uploads can activate v2+ (see routes approve).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.services.semantic_drift import chromadb_store
from src.services.semantic_drift.models import demo_rules_baseline_columns


def _slug(s: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "_", s.strip().lower())
    return x.strip("_") or "col"


def _reference_stats_for_column(series: pd.Series) -> Dict[str, Any]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return {}
    arr = s.to_numpy(dtype=float)
    return {
        "ref_mean": float(np.mean(arr)),
        "ref_std": float(max(np.std(arr, ddof=0), 1e-9)),
        "ref_min": float(np.min(arr)),
        "ref_max": float(np.max(arr)),
        "ref_q25": float(np.quantile(arr, 0.25)),
        "ref_q50": float(np.quantile(arr, 0.50)),
        "ref_q75": float(np.quantile(arr, 0.75)),
        "ref_n": int(len(arr)),
    }


def create_baseline_from_csv(
    dataset_name: str,
    csv_path: str | Path,
    created_by: str = "system",
    deactivate_previous: bool = True,
) -> Dict[str, Any]:
    """
    Read CSV, build column profiles from demo rules (extendable for other datasets),
    store baseline + columns in ChromaDB.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Baseline CSV not found: {path}")

    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Baseline CSV has no rows")

    rules = demo_rules_baseline_columns()
    missing = [c for c in rules if c not in df.columns]
    if missing:
        raise ValueError(f"Baseline CSV missing required columns: {missing}")

    client = chromadb_store.get_chroma_client()
    if deactivate_previous:
        chromadb_store.deactivate_baselines_for_dataset(client, dataset_name)

    baseline_id = chromadb_store.new_id("bl")
    now = datetime.now(timezone.utc).isoformat()
    prior = chromadb_store.list_all_baselines_for_dataset(client, dataset_name)
    max_n = 0
    for row in prior:
        v = str(row.get("baseline_version") or "v0")
        if v.startswith("v") and v[1:].isdigit():
            max_n = max(max_n, int(v[1:]))
    version = f"v{max_n + 1}"

    chromadb_store.upsert_baseline_registry(
        client,
        baseline_id=baseline_id,
        dataset_name=dataset_name,
        baseline_version=version,
        status="active",
        created_at=now,
        created_by=created_by,
        active=True,
    )

    for col, semantics in rules.items():
        pid = f"cp_{baseline_id}__{_slug(col)}"
        ref_stats = _reference_stats_for_column(df[col])
        payload = {
            "id": pid,
            "baseline_id": baseline_id,
            "dataset_name": dataset_name,
            "column_name": col,
            **semantics,
            **ref_stats,
        }
        chromadb_store.upsert_column_profile(client, pid, baseline_id, payload)

    return {
        "baseline_id": baseline_id,
        "dataset_name": dataset_name,
        "baseline_version": version,
        "status": "active",
        "column_count": len(rules),
        "row_count": int(len(df)),
        "created_at": now,
        "message": "Baseline stored in ChromaDB (semantic_baseline_registry + baseline_column_profiles).",
    }


def approve_new_baseline_version(
    dataset_name: str,
    csv_path: str | Path,
    created_by: str = "human_governance",
) -> Dict[str, Any]:
    """Governance action: deactivate old baselines, create new version from CSV."""
    return create_baseline_from_csv(dataset_name, csv_path, created_by=created_by, deactivate_previous=True)


def get_active_baseline(dataset_name: str) -> Optional[Dict[str, Any]]:
    client = chromadb_store.get_chroma_client()
    return chromadb_store.get_active_baseline_record(client, dataset_name)


def get_baseline_column_profiles(dataset_name: str) -> List[Dict[str, Any]]:
    client = chromadb_store.get_chroma_client()
    rec = chromadb_store.get_active_baseline_record(client, dataset_name)
    if not rec:
        return []
    return chromadb_store.list_column_profiles_for_baseline(client, rec["id"])
