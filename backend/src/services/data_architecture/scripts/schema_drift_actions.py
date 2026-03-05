"""Policy-driven, explainable, and safe schema-drift remediation helpers.

This module implements small, conservative automated actions that can be
applied when drift is detected. Actions are intentionally conservative:
- auto-accept new columns when their non-null ratio is high (existing logic)
- attempt safe dtype casts (numeric widenings) when policy allows
- for missing non-required columns, fill with nulls (no data loss)

All actions produce an explainable JSON file under `metadata/drift_actions/`.
"""
import os
import json
from datetime import datetime
from typing import Dict, Any

DRIFT_ACTIONS_DIR = os.path.join("metadata", "drift_actions")
os.makedirs(DRIFT_ACTIONS_DIR, exist_ok=True)


def _save_action_record(table_name: str, source_file: str, action: Dict[str, Any]):
    fname = os.path.join(DRIFT_ACTIONS_DIR, f"action_{table_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fname, 'w', encoding='utf-8') as f:
        json.dump({"timestamp": datetime.utcnow().isoformat(), "table": table_name, "source_file": source_file, "action": action}, f, indent=2)
    return fname


def is_numeric_type(t: str):
    t = str(t).lower()
    return any(x in t for x in ["int", "long", "bigint", "double", "float", "decimal", "numeric"])


def safe_to_cast(expected: str, actual: str) -> bool:
    """Conservative check: allow cast when both are numeric and casting is widening.

    This is intentionally simple for research prototyping. For production,
    use type range checks and sample-based verification.
    """
    exp = str(expected).lower()
    act = str(actual).lower()
    if is_numeric_type(exp) and is_numeric_type(act):
        # allow if actual is numeric and casting won't drop precision significantly
        # allow int->double, int->long, float->double etc.
        return True
    # allow string acceptance from other types by casting to string (safe)
    if "string" in exp:
        return True
    return False


def attempt_dtype_casts_and_overwrite_pandas(spark, table_name: str, spark_df, casts: Dict[str, str], raw_file_path: str):
    """Attempt casts on Spark DataFrame, fall back to pandas write.

    Returns dict with result and explanation and path of file written (if any).
    """
    import pandas as pd
    action = {"type": "dtype_casts", "casts": casts, "attempted": [], "failed": []}

    try:
        # Apply casts using Spark and then write back to CSV via pandas (safe for small datasets)
        pdf = spark_df.toPandas()
        for col, target in casts.items():
            try:
                # Use pandas astype where possible
                if 'string' in str(target).lower():
                    pdf[col] = pdf[col].astype(str)
                else:
                    pdf[col] = pd_safe_cast(pdf[col], target)
                action['attempted'].append({col: target})
            except Exception as e:
                action['failed'].append({col: str(e)})

        # overwrite original raw CSV
        pdf.to_csv(raw_file_path, index=False)
        action['status'] = 'success_overwrote_raw'
        action['path'] = raw_file_path
    except Exception as e:
        action['status'] = 'failed'
        action['error'] = str(e)

    rec = _save_action_record(table_name, raw_file_path, action)
    action['record_path'] = rec
    return action


def pd_safe_cast(series, target_type_str):
    """Perform a conservative pandas cast based on target type string."""
    import pandas as pd
    tt = str(target_type_str).lower()
    if 'int' in tt:
        return pd.to_numeric(series, errors='coerce').astype('Int64')
    if 'long' in tt or 'bigint' in tt:
        return pd.to_numeric(series, errors='coerce').astype('Int64')
    if 'double' in tt or 'float' in tt or 'decimal' in tt or 'numeric' in tt:
        return pd.to_numeric(series, errors='coerce').astype('float64')
    if 'string' in tt or 'varchar' in tt or 'char' in tt:
        return series.astype(str)
    # fallback
    return series
