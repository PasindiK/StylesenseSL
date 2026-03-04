import math
import numpy as np

# Feature builder for schema-drift ingestion events
# Exposes `build_feature_vector(event)` -> dict of numeric features

STORAGE_TIER_MAP = {"hot": 0.0, "warm": 1.0, "cold": 2.0}


def safe_get(d, key, default=0.0):
    return d.get(key, default) if isinstance(d, dict) else default


def build_feature_vector(drift_event: dict, dq_metrics: dict = None, pipeline_meta: dict = None):
    """Build a numeric feature vector from a drift event and optional DQ/pipeline metadata.

    Expected keys in `drift_event` (example):
      - diff: {"new_columns": [...], "missing_columns": [...], "dtype_changes": [...]}
      - table
      - source_file

    dq_metrics example keys:
      - null_ratio_delta
      - duplicate_ratio

    pipeline_meta example keys:
      - downstream_failure_count
      - avg_latency_ms
      - storage_move (hot/warm/cold)

    Returns a dict with flattened numeric features and a numpy array `vector` (for algorithm use).
    """
    diff = drift_event.get("diff", {}) if drift_event else {}

    new_cols = len(diff.get("new_columns", []))
    missing_cols = len(diff.get("missing_columns", []))
    dtype_changes = len(diff.get("dtype_changes", []))
    renames = diff.get("renames", [])
    rename_count = len(renames)
    
    # Calculate average rename confidence if renames exist
    avg_rename_similarity = 0.0
    rename_type_match_ratio = 0.0
    if renames:
        avg_rename_similarity = sum(r.get("similarity", 0.0) for r in renames) / rename_count
        rename_type_match_ratio = sum(1 for r in renames if r.get("type_match", False)) / rename_count

    # Ratios (guard divided-by-zero)
    total_known = max(new_cols + missing_cols + dtype_changes + rename_count, 1)
    new_col_ratio = new_cols / total_known
    missing_col_ratio = missing_cols / total_known
    dtype_change_ratio = dtype_changes / total_known
    rename_ratio = rename_count / total_known

    dq = dq_metrics or {}
    null_ratio_delta = float(safe_get(dq, "null_ratio_delta", 0.0))
    duplicate_ratio = float(safe_get(dq, "duplicate_ratio", 0.0))

    pm = pipeline_meta or {}
    downstream_failures = int(safe_get(pm, "downstream_failure_count", 0))
    avg_latency_ms = float(safe_get(pm, "avg_latency_ms", 0.0))
    storage_tier = pm.get("storage_move", None)
    storage_tier_imp = float(STORAGE_TIER_MAP.get(storage_tier, 0.0))

    # row count delta if present
    row_count_delta = float(safe_get(pm, "row_count_delta", 0.0))

    features = {
        "new_cols": float(new_cols),
        "missing_cols": float(missing_cols),
        "dtype_changes": float(dtype_changes),
        "rename_count": float(rename_count),
        "avg_rename_similarity": float(avg_rename_similarity),
        "rename_type_match_ratio": float(rename_type_match_ratio),
        "new_col_ratio": float(new_col_ratio),
        "missing_col_ratio": float(missing_col_ratio),
        "dtype_change_ratio": float(dtype_change_ratio),
        "rename_ratio": float(rename_ratio),
        "null_ratio_delta": float(null_ratio_delta),
        "duplicate_ratio": float(duplicate_ratio),
        "downstream_failures": float(downstream_failures),
        "avg_latency_ms": float(avg_latency_ms),
        "storage_tier_imp": float(storage_tier_imp),
        "row_count_delta": float(row_count_delta),
    }

    # Construct a feature vector (order must be stable)
    vector = np.array([
        features["new_cols"],
        features["missing_cols"],
        features["dtype_changes"],
        features["rename_count"],
        features["avg_rename_similarity"],
        features["rename_type_match_ratio"],
        features["new_col_ratio"],
        features["missing_col_ratio"],
        features["dtype_change_ratio"],
        features["rename_ratio"],
        features["null_ratio_delta"],
        features["duplicate_ratio"],
        features["downstream_failures"],
        features["avg_latency_ms"],
        features["storage_tier_imp"],
        features["row_count_delta"],
    ], dtype=float)

    # Basic normalization to avoid large numeric ranges (latency / row deltas)
    # Keep original values but scale latency and row_count_delta
    if vector[9] > 0:
        vector[9] = math.log1p(vector[9])
    if abs(vector[11]) > 0:
        vector[11] = math.copysign(math.log1p(abs(vector[11])), vector[11])

    return {"features": features, "vector": vector}
