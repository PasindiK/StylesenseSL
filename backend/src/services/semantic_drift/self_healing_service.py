"""
Safe self-healing only: renames, numeric casts, date standardization, optional columns.

Semantic safety (whether meaning stayed similar) is enforced upstream by the drift /
interpretation layer using a small sentence embedding model (for example
`sentence-transformers/all-MiniLM-L6-v2`) — this module only applies deterministic,
bounded transforms when drift rows are already classified as safe to heal.

Never converts stock meaning to sold meaning — ingestion blocks that at drift layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


RENAME_MAP = {
    "sales_amt": "sales_amount",
    "qty": "quantity",
}


def rename_known_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    actions: List[str] = []
    out = df.copy()
    for src, dst in RENAME_MAP.items():
        if src in out.columns and dst not in out.columns:
            out = out.rename(columns={src: dst})
            actions.append(f"renamed:{src}->{dst}")
    return out, actions


def cast_numeric_columns(df: pd.DataFrame, baseline_columns: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    actions: List[str] = []
    out = df.copy()
    for c in out.columns:
        if c not in baseline_columns and c not in ("sales_amount", "quantity", "discount_amount"):
            continue
        if c in ("sales_amount", "discount_amount"):
            coerced = pd.to_numeric(out[c], errors="coerce")
            if not coerced.equals(out[c]):
                actions.append(f"numeric_cast:{c}")
            out[c] = coerced
        if c == "quantity":
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).round().astype(int)
            actions.append("numeric_cast:quantity")
    return out, actions


def _try_parse_date(val: Any) -> Any:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return val
    s = str(val).strip()
    if not s:
        return val
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return val


def standardize_date_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    actions: List[str] = []
    out = df.copy()
    for c in out.columns:
        if "date" not in c.lower():
            continue
        new_col = out[c].map(_try_parse_date)
        if not new_col.equals(out[c]):
            actions.append(f"date_std:{c}")
        out[c] = new_col
    return out, actions


def add_missing_optional_columns(df: pd.DataFrame, baseline_profiles: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, List[str]]:
    actions: List[str] = []
    out = df.copy()
    names = set(out.columns)
    for p in baseline_profiles:
        col = p["column_name"]
        if col in names:
            continue
        if col == "discount_amount":
            out[col] = None
            actions.append("added_optional:discount_amount")
            names.add(col)
    return out, actions


def apply_interpretation_numeric_transforms(df: pd.DataFrame, drift_results: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, List[str]]:
    """Apply non-identity numeric proposals from interpretation drift (SELF_HEAL rows only)."""
    actions: List[str] = []
    out = df.copy()
    for row in drift_results:
        if row.get("decision") != "SELF_HEAL":
            continue
        prop = row.get("transform_proposal") or {}
        kind = str(prop.get("kind") or "identity")
        if kind == "identity":
            continue
        col = str(row.get("mapped_from") or row.get("column_name") or "")
        if not col or col not in out.columns:
            continue
        params = prop.get("params") or {}
        s = pd.to_numeric(out[col], errors="coerce").astype(float)
        if kind == "affine":
            a = float(params.get("a", 1.0))
            b = float(params.get("b", 0.0))
            out[col] = a * s + b
            actions.append(f"interpretation_affine:{col}")
        elif kind == "minmax":
            smin = float(params.get("src_min", np.nanmin(s.to_numpy())))
            smax = float(params.get("src_max", np.nanmax(s.to_numpy())))
            dmin = float(params.get("dst_min", 0.0))
            dmax = float(params.get("dst_max", 1.0))
            if smax - smin <= 1e-12 or dmax - dmin <= 1e-12:
                continue
            out[col] = (s - smin) / (smax - smin) * (dmax - dmin) + dmin
            actions.append(f"interpretation_minmax:{col}")
    return out, actions


def can_self_heal(drift_results: List[Dict[str, Any]]) -> bool:
    if any(r.get("decision") == "QUARANTINE" for r in drift_results):
        return False
    if any(r.get("decision") == "HUMAN_REVIEW" for r in drift_results):
        return False
    return any(r.get("decision") == "SELF_HEAL" for r in drift_results)


def apply_self_healing(
    df: pd.DataFrame,
    baseline_profiles: List[Dict[str, Any]],
    drift_results: List[Dict[str, Any]] | None = None,
) -> Tuple[pd.DataFrame, List[str], bool]:
    """Apply allowed transforms; returns (df, actions, success)."""
    actions: List[str] = []
    base_cols = [p["column_name"] for p in baseline_profiles]
    df, a1 = rename_known_columns(df)
    actions.extend(a1)
    df, a2 = cast_numeric_columns(df, base_cols)
    actions.extend(a2)
    df, a3 = standardize_date_columns(df)
    actions.extend(a3)
    df, a4 = add_missing_optional_columns(df, baseline_profiles)
    actions.extend(a4)
    if drift_results:
        df, a5 = apply_interpretation_numeric_transforms(df, drift_results)
        actions.extend(a5)
    return df, actions, True
