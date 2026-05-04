"""
ChromaDB persistence layer for semantic drift demo/production-lite storage.

Each entity type maps to a dedicated collection. Unique IDs:
- baselines: bl_<uuid>
- column profiles: cp_<baseline_id>__<column_slug>
- batches: bat_<uuid>
- drift rows: dr_<batch_id>__<column_slug>
- quarantine: qu_<batch_id>
- sales rows: rec_<uuid>

Metadata is JSON-friendly strings where needed for Chroma filtering.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

_MODULE_DIR = Path(__file__).resolve().parent
CHROMA_PERSIST_DIR = _MODULE_DIR / "chroma_data"

COL_BASELINES = "semantic_baseline_registry"
COL_COLUMNS = "baseline_column_profiles"
COL_BATCHES = "ingestion_batches"
COL_DRIFT = "semantic_drift_results"
COL_QUARANTINE = "quarantined_datasets"
COL_SALES = "sales_transactions"


class _ZeroEmbeddingFunction(EmbeddingFunction):
    """
    Chroma 1.x defaults to downloading ONNX MiniLM for embeddings.
    This module stores JSON in `documents` and uses metadata filters — we disable
    remote model download by supplying a fixed-dimension zero embedding.
    """

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        return [[0.0] * 384 for _ in input]

    @staticmethod
    def name() -> str:
        return "semantic_drift_zero"

    def get_config(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "_ZeroEmbeddingFunction":
        return _ZeroEmbeddingFunction()

    @staticmethod
    def validate_config(config: dict[str, Any]) -> None:
        return


_ZERO_EF = _ZeroEmbeddingFunction()


def get_chroma_client() -> ClientAPI:
    """Single persistent Chroma client for this module (thread-safe enough for demo API)."""
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))


def _collection(client: ClientAPI, name: str):
    return client.get_or_create_collection(
        name=name,
        metadata={"module": "semantic_drift"},
        embedding_function=_ZERO_EF,
    )


def upsert_baseline_registry(
    client: ClientAPI,
    baseline_id: str,
    dataset_name: str,
    baseline_version: str,
    status: str,
    created_at: str,
    created_by: str,
    active: bool,
) -> None:
    col = _collection(client, COL_BASELINES)
    col.upsert(
        ids=[baseline_id],
        documents=[json.dumps({"dataset_name": dataset_name, "baseline_version": baseline_version})],
        metadatas=[
            {
                "dataset_name": dataset_name,
                "baseline_version": baseline_version,
                "status": status,
                "created_at": created_at,
                "created_by": created_by,
                "active": str(active).lower(),
            }
        ],
    )


def deactivate_baselines_for_dataset(client: ClientAPI, dataset_name: str) -> None:
    col = _collection(client, COL_BASELINES)
    rows = col.get(where={"dataset_name": dataset_name})
    if not rows["ids"]:
        return
    metas = []
    docs = []
    for i, bid in enumerate(rows["ids"]):
        m = dict(rows["metadatas"][i] or {})
        m["active"] = "false"
        m["status"] = "inactive"
        metas.append(m)
        docs.append(rows["documents"][i] if rows["documents"] else "{}")
    col.upsert(ids=list(rows["ids"]), metadatas=metas, documents=docs)


def list_all_baselines_for_dataset(client: ClientAPI, dataset_name: str) -> List[Dict[str, Any]]:
    col = _collection(client, COL_BASELINES)
    res = col.get(where={"dataset_name": dataset_name})
    out: List[Dict[str, Any]] = []
    for i, bid in enumerate(res.get("ids") or []):
        m = res["metadatas"][i] or {}
        out.append(
            {
                "id": bid,
                "dataset_name": m.get("dataset_name"),
                "baseline_version": m.get("baseline_version"),
                "status": m.get("status"),
                "created_at": m.get("created_at"),
                "created_by": m.get("created_by"),
                "active": str(m.get("active", "")).lower() == "true",
            }
        )
    return out


def get_active_baseline_record(client: ClientAPI, dataset_name: str) -> Optional[Dict[str, Any]]:
    col = _collection(client, COL_BASELINES)
    res = col.get(where={"dataset_name": dataset_name})
    if not res["ids"]:
        return None
    for i, bid in enumerate(res["ids"]):
        m = res["metadatas"][i] or {}
        if str(m.get("active", "")).lower() != "true":
            continue
        return {
            "id": bid,
            "dataset_name": m.get("dataset_name"),
            "baseline_version": m.get("baseline_version"),
            "status": m.get("status"),
            "created_at": m.get("created_at"),
            "created_by": m.get("created_by"),
            "active": True,
        }
    return None


def upsert_column_profile(client: ClientAPI, profile_id: str, baseline_id: str, column_payload: Dict[str, Any]) -> None:
    col = _collection(client, COL_COLUMNS)
    col.upsert(
        ids=[profile_id],
        documents=[json.dumps(column_payload, default=str)],
        metadatas=[
            {
                "baseline_id": baseline_id,
                "column_name": column_payload.get("column_name", ""),
                "dataset_name": column_payload.get("dataset_name", ""),
            }
        ],
    )


def list_column_profiles_for_baseline(client: ClientAPI, baseline_id: str) -> List[Dict[str, Any]]:
    col = _collection(client, COL_COLUMNS)
    res = col.get(where={"baseline_id": baseline_id})
    out: List[Dict[str, Any]] = []
    for doc in res.get("documents") or []:
        if doc:
            out.append(json.loads(doc))
    return out


def upsert_batch(
    client: ClientAPI,
    batch_id: str,
    dataset_name: str,
    baseline_version: str,
    uploaded_at: str,
    status: str,
    total_rows: int,
    accepted_rows: int,
    rejected_rows: int,
) -> None:
    col = _collection(client, COL_BATCHES)
    col.upsert(
        ids=[batch_id],
        documents=[json.dumps({"batch_id": batch_id, "dataset_name": dataset_name})],
        metadatas=[
            {
                "dataset_name": dataset_name,
                "baseline_version": baseline_version,
                "uploaded_at": uploaded_at,
                "status": status,
                "total_rows": str(total_rows),
                "accepted_rows": str(accepted_rows),
                "rejected_rows": str(rejected_rows),
            }
        ],
    )


def get_batch(client: ClientAPI, batch_id: str) -> Optional[Dict[str, Any]]:
    col = _collection(client, COL_BATCHES)
    try:
        res = col.get(ids=[batch_id])
    except Exception:
        return None
    if not res["ids"]:
        return None
    m = res["metadatas"][0]
    return {
        "id": res["ids"][0],
        "dataset_name": m.get("dataset_name"),
        "baseline_version": m.get("baseline_version"),
        "uploaded_at": m.get("uploaded_at"),
        "status": m.get("status"),
        "total_rows": int(m.get("total_rows", 0)),
        "accepted_rows": int(m.get("accepted_rows", 0)),
        "rejected_rows": int(m.get("rejected_rows", 0)),
    }


def list_ingestion_batches(client: ClientAPI) -> List[Dict[str, Any]]:
    col = _collection(client, COL_BATCHES)
    res = col.get()
    out: List[Dict[str, Any]] = []
    for i, bid in enumerate(res.get("ids") or []):
        m = res["metadatas"][i] or {}
        out.append(
            {
                "batch_id": bid,
                "dataset_name": m.get("dataset_name"),
                "baseline_version": m.get("baseline_version"),
                "uploaded_at": m.get("uploaded_at"),
                "status": m.get("status"),
                "total_rows": int(m.get("total_rows", 0)),
                "accepted_rows": int(m.get("accepted_rows", 0)),
                "rejected_rows": int(m.get("rejected_rows", 0)),
            }
        )
    return sorted(out, key=lambda x: str(x.get("uploaded_at", "")), reverse=True)


def save_drift_results(
    client: ClientAPI,
    batch_id: str,
    baseline_version: str,
    results: List[Dict[str, Any]],
) -> None:
    col = _collection(client, COL_DRIFT)
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, str]] = []
    for r in results:
        cname = str(r.get("column_name", "unknown"))
        rid = f"dr_{batch_id}__{cname.replace(' ', '_')}"
        payload = dict(r)
        payload["batch_id"] = batch_id
        payload["baseline_version"] = baseline_version
        ids.append(rid)
        docs.append(json.dumps(payload, default=str))
        metas.append({"batch_id": batch_id, "column_name": cname, "baseline_version": baseline_version})
    if ids:
        col.upsert(ids=ids, documents=docs, metadatas=metas)


def list_drift_results_for_batch(client: ClientAPI, batch_id: str) -> List[Dict[str, Any]]:
    col = _collection(client, COL_DRIFT)
    res = col.get(where={"batch_id": batch_id})
    out: List[Dict[str, Any]] = []
    for doc in res.get("documents") or []:
        if doc:
            out.append(json.loads(doc))
    return sorted(out, key=lambda x: str(x.get("column_name", "")))


def upsert_quarantine(
    client: ClientAPI,
    batch_id: str,
    dataset_name: str,
    reason: str,
    suggested_action: str,
    created_at: str,
) -> None:
    col = _collection(client, COL_QUARANTINE)
    qid = f"qu_{batch_id}"
    col.upsert(
        ids=[qid],
        documents=[json.dumps({"batch_id": batch_id, "reason": reason})],
        metadatas=[
            {
                "batch_id": batch_id,
                "dataset_name": dataset_name,
                "reason": reason[:2000],
                "suggested_action": suggested_action[:2000],
                "created_at": created_at,
            }
        ],
    )


def list_quarantine(client: ClientAPI) -> List[Dict[str, Any]]:
    col = _collection(client, COL_QUARANTINE)
    res = col.get()
    out: List[Dict[str, Any]] = []
    for i, qid in enumerate(res.get("ids") or []):
        m = res["metadatas"][i] or {}
        out.append(
            {
                "id": qid,
                "batch_id": m.get("batch_id"),
                "dataset_name": m.get("dataset_name"),
                "reason": m.get("reason"),
                "suggested_action": m.get("suggested_action"),
                "created_at": m.get("created_at"),
            }
        )
    return sorted(out, key=lambda x: str(x.get("created_at", "")), reverse=True)


def append_sales_rows(
    client: ClientAPI,
    rows: List[Dict[str, Any]],
) -> List[str]:
    """Each row must include record_id; returns ids written."""
    col = _collection(client, COL_SALES)
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, str]] = []
    for row in rows:
        rid = row.get("record_id") or f"rec_{uuid.uuid4().hex}"
        row = {**row, "record_id": rid}
        ids.append(str(rid))
        docs.append(json.dumps(row, default=str))
        metas.append(
            {
                "ingestion_batch_id": str(row.get("ingestion_batch_id", "")),
                "baseline_version": str(row.get("baseline_version", "")),
                "drift_status": str(row.get("drift_status", "")),
                "repair_action": str(row.get("repair_action", "")),
            }
        )
    if ids:
        col.upsert(ids=ids, documents=docs, metadatas=metas)
    return ids


def list_sales_transactions(client: ClientAPI) -> List[Dict[str, Any]]:
    col = _collection(client, COL_SALES)
    res = col.get()
    out: List[Dict[str, Any]] = []
    for doc in res.get("documents") or []:
        if doc:
            out.append(json.loads(doc))
    return sorted(out, key=lambda x: str(x.get("ingested_at", "")))


def list_sales_transactions_for_batch(client: ClientAPI, batch_id: str) -> List[Dict[str, Any]]:
    """Accepted / repaired rows for a single ingestion batch (final table slice in Chroma)."""
    col = _collection(client, COL_SALES)
    res = col.get(where={"ingestion_batch_id": batch_id})
    out: List[Dict[str, Any]] = []
    for doc in res.get("documents") or []:
        if doc:
            out.append(json.loads(doc))
    return sorted(out, key=lambda x: str(x.get("ingested_at", "")))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
