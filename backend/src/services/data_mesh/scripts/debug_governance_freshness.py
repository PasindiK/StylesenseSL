#!/usr/bin/env python3
"""
Diagnostic: print freshness-related governance signals per domain (paths, CSV mtime,
detected date column, latest business date, lag hours, history row count, freshness risk).

Run from repo anywhere:
  python backend/src/services/data_mesh/scripts/debug_governance_freshness.py

Does not change production behavior.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SERVICE_SRC = THIS_DIR.parent / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from governance_intelligence import GovernanceIntelligenceEngine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug governance freshness metrics per domain.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=THIS_DIR.parent / "data",
        help="Data mesh root (contains Data_Mesh_Domains and monitoring/).",
    )
    args = parser.parse_args()

    data_path = args.data_root / "Data_Mesh_Domains"
    hist_path = args.data_root / "monitoring" / "domain_health_history.csv"

    eng = GovernanceIntelligenceEngine(data_path=data_path, monitoring_history_path=hist_path)

    domains = sorted({d.name for d in data_path.iterdir() if d.is_dir() and d.name.endswith("_domain")})
    now = datetime.now()

    print(f"evaluation_now_local: {now.isoformat(timespec='seconds')}")
    print(f"data_path: {data_path}")
    print(f"monitoring_history: {hist_path}")
    print("")

    for domain in domains:
        csv_path = data_path / domain / f"{domain}.csv"
        mtime = csv_path.stat().st_mtime if csv_path.exists() else None
        mtime_s = datetime.fromtimestamp(mtime).isoformat(sep=" ", timespec="seconds") if mtime else "N/A"

        try:
            g = eng.governance_domain(domain)
        except Exception as exc:  # noqa: BLE001
            print(f"--- {domain} (ERROR) ---\n  {exc}\n")
            continue

        fs = g.get("freshness_stability") or {}
        dist = g.get("distribution_stability") or {}
        hist_count = 0
        if hist_path.exists():
            import pandas as pd

            raw = pd.read_csv(hist_path)
            if "domain_name" in raw.columns:
                hist_count = int((raw["domain_name"].astype(str).str.strip().str.lower() == domain.lower()).sum())

        print(f"--- {domain} ---")
        print(f"  csv_path: {csv_path}")
        print(f"  csv_mtime: {mtime_s}")
        print(f"  date_column (distribution): {dist.get('date_column')}")
        print(f"  latest_business_data_date: {g.get('latest_business_data_date')}")
        print(f"  freshness_reference: {g.get('freshness_reference')}")
        print(f"  lag_hours (latest_value): {fs.get('latest_value')}")
        print(
            f"  freshness_baseline_mean/std: {fs.get('baseline_mean')} / {fs.get('baseline_std')} "
            f"(sample_size={fs.get('sample_size')})"
        )
        print(f"  freshness_risk: {fs.get('risk')}  z_score: {fs.get('z_score')}  confidence: {fs.get('confidence')}")
        print(f"  history_rows_for_domain (raw CSV count): {hist_count}")
        print("")


if __name__ == "__main__":
    main()
