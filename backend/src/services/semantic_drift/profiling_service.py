"""
Semantic profiling for uploaded CSVs — rule-based for demo, uses nearby column context.

Viva point: quantity + order_id + sales_amount => sold quantity;
quantity + warehouse_id + stock_location => inventory stock.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def infer_role(column_name: str, series: pd.Series) -> str:
    c = column_name.lower()
    if "id" in c or c.endswith("_id"):
        return "identifier"
    if "date" in c or "time" in c:
        return "date"
    if any(k in c for k in ("amount", "price", "revenue", "discount", "total", "amt")):
        return "measure"
    if "qty" in c or c == "quantity" or "count" in c:
        return "measure"
    if pd.api.types.is_bool_dtype(series):
        return "binary_label"
    return "text_attribute"


def infer_domain(column_name: str, nearby_columns: List[str]) -> str:
    pool = " ".join([column_name.lower(), *[n.lower() for n in nearby_columns]])
    if any(x in pool for x in ("warehouse", "stock_location", "inventory", "shelf", "available_stock")):
        return "Inventory"
    if any(x in pool for x in ("order", "sale", "customer", "discount", "revenue")):
        return "Sales"
    return "Commerce"


def infer_business_meaning(column_name: str, nearby_columns: List[str]) -> str:
    c = column_name.lower()
    pool = " ".join([c, *[n.lower() for n in nearby_columns]])
    inv = any(x in pool for x in ("warehouse_id", "stock_location", "inventory_status", "available_stock", "shelf"))
    sales_ctx = any(x in pool for x in ("order_id", "customer_id", "sales_amount", "sales_amt", "discount"))

    if c in ("quantity", "qty") and inv:
        return "Available stock quantity in inventory (warehouse context)"
    if c in ("quantity", "qty") and sales_ctx:
        return "Number of products sold in the order"

    if c in ("sales_amount", "sales_amt", "revenue") or "amt" in c:
        return "Final sales revenue after applying discounts"
    if "discount" in c:
        return "Discount value applied to the order"
    if "customer" in c and "id" in c:
        return "Unique customer identifier"
    if "order" in c and "id" in c:
        return "Unique order transaction identifier"
    if "date" in c:
        return "Date when the customer order was placed"
    return f"Inferred business field for {column_name}"


def infer_unit_and_scale(column_name: str, series: pd.Series) -> Tuple[str, str]:
    c = column_name.lower()
    if "date" in c:
        return "date", "date"
    if any(x in c for x in ("amount", "discount", "price", "revenue", "amt")):
        return "LKR", "currency"
    if "qty" in c or c == "quantity" or "count" in c:
        if pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series):
            return "count", "integer"
        return "count", "unknown"
    if pd.api.types.is_integer_dtype(series):
        return "none", "integer"
    if pd.api.types.is_float_dtype(series):
        return "none", "decimal"
    return "none", "categorical"


def infer_value_direction(column_name: str, meaning: str) -> str:
    c = column_name.lower()
    if "discount" in c:
        return "higher means greater discount"
    if any(x in c for x in ("sales", "amount", "revenue", "amt")):
        return "higher means more revenue"
    if "quantity" in c and "inventory" in meaning.lower():
        return "higher means more units on hand"
    if "quantity" in c or c == "qty":
        return "higher means more sold items"
    if "date" in c:
        return "newer date means more recent order"
    return "neutral"


def profile_column(column_name: str, series: pd.Series, nearby_columns: List[str]) -> Dict[str, Any]:
    null_pct = float(series.isna().mean() * 100) if len(series) else 0.0
    unique_count = int(series.nunique(dropna=True))
    sample_values = [str(x) for x in series.dropna().head(5).tolist()]
    role = infer_role(column_name, series)
    domain = infer_domain(column_name, nearby_columns)
    meaning = infer_business_meaning(column_name, nearby_columns)
    unit, scale = infer_unit_and_scale(column_name, series)
    direction = infer_value_direction(column_name, meaning)

    dtype = "string"
    if pd.api.types.is_integer_dtype(series):
        dtype = "integer"
    elif pd.api.types.is_float_dtype(series):
        dtype = "decimal"
    elif pd.api.types.is_bool_dtype(series):
        dtype = "boolean"

    min_v = max_v = None
    if pd.api.types.is_numeric_dtype(series):
        with np.errstate(all="ignore"):
            min_v = float(np.nanmin(series.to_numpy(dtype=float))) if len(series) else None
            max_v = float(np.nanmax(series.to_numpy(dtype=float))) if len(series) else None

    confidence = 0.75
    if "inferred" in meaning.lower():
        confidence = 0.45

    return {
        "column_name": column_name,
        "data_type": dtype,
        "sample_values": sample_values,
        "null_percentage": round(null_pct, 2),
        "unique_count": unique_count,
        "min_value": min_v,
        "max_value": max_v,
        "role": role,
        "domain": domain,
        "unit": unit,
        "scale": scale,
        "detected_business_meaning": meaning,
        "value_direction": direction,
        "confidence_score": confidence,
    }


def profile_dataframe(df: pd.DataFrame, dataset_name: str) -> Dict[str, Any]:
    cols = list(df.columns)
    profiles: Dict[str, Any] = {}
    for name in cols:
        nearby = [c for c in cols if c != name]
        profiles[name] = profile_column(name, df[name], nearby)
    return {"dataset_name": dataset_name, "columns": profiles}
