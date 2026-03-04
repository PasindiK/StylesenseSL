import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = os.path.join("gold", "ml_decision_engine")
LOG_PATH = os.path.join(ROOT, "logs", "decisions.jsonl")
REPORT_DIR = os.path.join(ROOT, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

FEATURE_NAMES = [
    "new_cols",
    "missing_cols",
    "dtype_changes",
    "new_col_ratio",
    "missing_col_ratio",
    "dtype_change_ratio",
    "null_ratio_delta",
    "duplicate_ratio",
    "downstream_failures",
    "avg_latency_ms",
    "storage_tier_imp",
    "row_count_delta",
]


def _read_decisions(path=LOG_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            rows.append(obj)
    return rows


def extract_contrib(explain):
    # Returns a numpy array of length len(FEATURE_NAMES) or None
    if not explain:
        return None
    if isinstance(explain, dict):
        if "contrib" in explain and isinstance(explain["contrib"], list):
            arr = np.array(explain["contrib"], dtype=float)
            # if shorter/longer than expected, pad or trim
            if arr.size < len(FEATURE_NAMES):
                arr = np.pad(arr, (0, len(FEATURE_NAMES) - arr.size), constant_values=0.0)
            elif arr.size > len(FEATURE_NAMES):
                arr = arr[: len(FEATURE_NAMES)]
            return arr
        # fallback: if theta available multiply by features if provided
        if "theta" in explain and "contrib" not in explain:
            # cannot reconstruct without features; skip
            return None
    return None


def aggregate_feature_importance(decisions):
    records = []
    for d in decisions:
        action = d.get("action") or d.get("policy_action")
        explain = d.get("explain") or d.get("extra", {}).get("explain")
        contrib = extract_contrib(explain)
        if contrib is None:
            continue
        records.append({"action": action, **{f: float(contrib[i]) for i, f in enumerate(FEATURE_NAMES)}})

    if not records:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(records)

    # mean absolute contribution per action
    abs_df = df.copy()
    for c in FEATURE_NAMES:
        abs_df[c] = abs_df[c].abs()

    agg = abs_df.groupby("action")[FEATURE_NAMES].mean().reset_index()

    # long format for reporting
    long = agg.melt(id_vars=["action"], value_vars=FEATURE_NAMES, var_name="feature", value_name="mean_abs_contrib")
    return agg, long


def action_distribution(decisions):
    actions = [d.get("action") or d.get("policy_action") for d in decisions]
    s = pd.Series(actions)
    dist = s.value_counts().reset_index()
    dist.columns = ["action", "count"]
    return dist


def plot_feature_importance(agg_df):
    # agg_df: wide format with action row and feature columns
    for _, row in agg_df.iterrows():
        action = row["action"]
        values = row[FEATURE_NAMES].values
        # pick top 8 by absolute value
        idx = np.argsort(np.abs(values))[::-1][:8]
        names = [FEATURE_NAMES[i] for i in idx]
        vals = values[idx]
        plt.figure(figsize=(8, 4))
        plt.barh(names[::-1], vals[::-1])
        plt.title(f"Top feature contributions — {action}")
        plt.tight_layout()
        plt.savefig(os.path.join(REPORT_DIR, f"feature_importance_{action}.png"))
        plt.close()


def plot_action_distribution(dist_df):
    plt.figure(figsize=(6, 4))
    plt.bar(dist_df["action"], dist_df["count"])
    plt.xticks(rotation=45, ha="right")
    plt.title("Action distribution")
    plt.tight_layout()
    path = os.path.join(REPORT_DIR, "action_distribution.png")
    plt.savefig(path)
    plt.close()


def run_report(log_path=LOG_PATH):
    decisions = _read_decisions(log_path)
    agg_wide, agg_long = aggregate_feature_importance(decisions)
    dist = action_distribution(decisions)

    # Save CSVs
    agg_wide.to_csv(os.path.join(REPORT_DIR, "feature_importance_per_action_wide.csv"), index=False)
    agg_long.to_csv(os.path.join(REPORT_DIR, "feature_importance_per_action_long.csv"), index=False)
    dist.to_csv(os.path.join(REPORT_DIR, "action_distribution.csv"), index=False)

    # Plots
    if not agg_wide.empty:
        plot_feature_importance(agg_wide)
    plot_action_distribution(dist)

    print("Reports written to:", REPORT_DIR)
    return {
        "agg_wide": os.path.join(REPORT_DIR, "feature_importance_per_action_wide.csv"),
        "agg_long": os.path.join(REPORT_DIR, "feature_importance_per_action_long.csv"),
        "dist": os.path.join(REPORT_DIR, "action_distribution.csv"),
        "plots_dir": REPORT_DIR,
    }


if __name__ == "__main__":
    run_report()
