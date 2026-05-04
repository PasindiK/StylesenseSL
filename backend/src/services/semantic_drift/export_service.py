"""Serialize Chroma-backed semantic drift tables to CSV for download."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Dict, List

import pandas as pd


def dict_rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    df = pd.DataFrame(rows)
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def flatten_drift_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Spread nested interpretation / transform blobs as JSON strings for CSV."""
    flat = dict(row)
    interp = flat.pop("interpretation", None)
    if interp is not None:
        flat["interpretation_json"] = json.dumps(interp, default=str)
    tp = flat.pop("transform_proposal", None)
    if tp is not None:
        flat["transform_proposal_json"] = json.dumps(tp, default=str)
    return flat
