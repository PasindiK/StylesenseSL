"""
Medallion layers + Azure Blob Storage layout (v1).

**Containers (Azure):** one per layer — ``bronze``, ``silver``, ``gold`` (lowercase).

**Blob paths (inside the container):** never repeat the layer name (avoid ``bronze/bronze/raw/...``).
Use substage-first paths so other services (Data Fabric, Mesh, Agentic) can glob predictably:

- ``bronze``: ``raw/...``, ``quarantine/<yyyyMMdd>/...``
- ``silver``: ``cleaned/...``, ``enriched/...``
- ``gold``: ``curated/...``, ``ml_ready/...``, ``stakeholder_views/...``

**Blob metadata** on upload (for lifecycle / discovery):

- ``medallion_layer`` — ``bronze`` | ``silver`` | ``gold``
- ``substage`` — first path segment (e.g. ``raw``, ``cleaned``)
- ``tier_policy`` — target access tier label (``HOT``, ``COOL``, …)
- ``layout_version`` — ``medallion_layers_storage_v1``
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

LAYOUT_VERSION = "medallion_layers_storage_v1"


def layout_spec() -> Dict[str, Any]:
    """Stable JSON-serializable description for APIs and sibling components."""
    return {
        "layout_version": LAYOUT_VERSION,
        "description": "Medallion logical layers mapped to Azure Blob containers + substage prefixes + tier metadata.",
        "containers": {
            "bronze": {
                "azure_container": "bronze",
                "blob_prefixes": ["raw/", "quarantine/"],
                "default_access_tier": "Hot",
            },
            "silver": {
                "azure_container": "silver",
                "blob_prefixes": ["cleaned/", "enriched/"],
                "default_access_tier": "Cool",
            },
            "gold": {
                "azure_container": "gold",
                "blob_prefixes": ["curated/", "ml_ready/", "stakeholder_views/"],
                "default_access_tier": "Hot",
            },
        },
        "cross_component_resolution": (
            "Resolve a dataset as: https://<account>.blob.core.windows.net/"
            "<layer>/<substage>/<file> — e.g. .../bronze/raw/transactions_raw.csv"
        ),
        "notes": [
            "Legacy local folders (bronze/raw beside medallions/) map into the same virtual paths.",
            "Azure lifecycle rules can target container + prefix (e.g. cool bronze/raw after N days).",
        ],
    }


def roots_for_layer(layer: str, base_dir: str) -> List[Tuple[str, str]]:
    """(absolute_root_on_disk, blob_path_prefix) in scan order — first match wins."""
    b = os.path.abspath(base_dir)
    normalized = str(layer or "").strip().lower()
    if normalized == "bronze":
        return [
            (os.path.join(b, "medallions", "bronze"), ""),
            (os.path.join(b, "bronze", "raw"), "raw/"),
            (os.path.join(b, "bronze", "quarantine"), "quarantine/"),
        ]
    if normalized == "silver":
        return [
            (os.path.join(b, "medallions", "silver"), ""),
            (os.path.join(b, "silver", "cleaned"), "cleaned/"),
            (os.path.join(b, "silver", "enriched"), "enriched/"),
        ]
    if normalized == "gold":
        return [
            (os.path.join(b, "medallions", "gold"), ""),
            (os.path.join(b, "gold", "curated"), "curated/"),
            (os.path.join(b, "gold", "ml_ready"), "ml_ready/"),
            (os.path.join(b, "gold", "stakeholder_views"), "stakeholder_views/"),
        ]
    return []


def canonical_blob_path_for_upload(local_file_path: str, layer: str, base_dir: str) -> str:
    """Map a local medallion file to the blob path inside the layer container (no duplicate layer prefix)."""
    local_abs = os.path.abspath(local_file_path)
    for root, prefix in roots_for_layer(layer, base_dir):
        root_abs = os.path.abspath(root)
        try:
            common = os.path.commonpath([root_abs, local_abs])
        except ValueError:
            continue
        if common != root_abs:
            continue
        rel = os.path.relpath(local_abs, root_abs).replace("\\", "/")
        if rel in (".", "..") or rel.startswith("../"):
            continue
        blob = f"{prefix}{rel}".replace("//", "/")
        while blob.startswith("./"):
            blob = blob[2:]
        return blob
    return os.path.basename(local_abs)


def substage_from_blob_path(blob_path: str) -> str:
    seg = str(blob_path or "").strip("/").split("/", 1)[0]
    return seg or "unknown"


def parquet_stream_blob_path(layer: str, batch_id: int, batch_date: str, timestamp: str) -> str:
    """Virtual path for parquet batches uploaded without a local medallion tree."""
    lid = int(batch_id)
    l = str(layer or "").strip().lower()
    if l == "bronze":
        return f"raw/ingestion/batch_{lid:05d}_{batch_date}_{timestamp}.parquet"
    if l == "silver":
        return f"enriched/ingestion/batch_{lid:05d}_{batch_date}_{timestamp}.parquet"
    return f"curated/ingestion/batch_{lid:05d}_{batch_date}_{timestamp}.parquet"


def _ascii_meta(value: str, max_len: int = 512) -> str:
    """Azure blob metadata values should be ASCII-only for broad SDK compatibility."""
    return str(value or "")[:max_len].encode("ascii", errors="replace").decode("ascii")


def blob_metadata_for_medallion_upload(
    layer: str,
    blob_path: str,
    repo_relative_path: str,
    tier_policy: str,
    record_count: Optional[int] = None,
) -> Dict[str, str]:
    """Metadata keys use letters and underscores (valid as blob metadata names).

    When ``record_count`` is set, dashboard Azure scans use it as the real row total
    instead of estimating from blob size.
    """
    meta: Dict[str, str] = {
        "medallion_layer": _ascii_meta(str(layer or "").lower(), 32),
        "substage": _ascii_meta(substage_from_blob_path(blob_path), 64),
        "tier_policy": _ascii_meta(str(tier_policy or "HOT").upper().replace(" ", "_"), 32),
        "layout_version": _ascii_meta(LAYOUT_VERSION, 64),
        "repo_relative_path": _ascii_meta(repo_relative_path, 1024),
    }
    if record_count is not None:
        try:
            rc = max(0, int(record_count))
        except (TypeError, ValueError):
            rc = 0
        meta["record_count"] = _ascii_meta(str(rc), 32)
    return meta
