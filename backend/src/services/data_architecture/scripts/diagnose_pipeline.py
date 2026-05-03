#!/usr/bin/env python
"""
Diagnose medallion pipeline flow — record counts per layer (data architecture).

Run from repo root or from this package; paths resolve from the data_architecture directory.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def count_records_in_layer(layer: str):
    """Count total records in a medallion layer (medallions/ paths)."""
    if layer == "bronze":
        pattern = str(BASE_DIR / "medallions" / "bronze" / "raw" / "*.csv")
    elif layer == "silver":
        pattern = str(BASE_DIR / "medallions" / "silver" / "cleaned" / "*.csv")
    elif layer == "gold":
        pattern = str(BASE_DIR / "medallions" / "gold" / "curated" / "*.csv")
    else:
        return 0, 0, {}

    files = glob.glob(pattern)
    total_records = 0
    file_info = {}

    for f in files:
        try:
            import pandas as pd

            df = pd.read_csv(f)
            records = len(df)
            total_records += records
            file_info[os.path.basename(f)] = records
        except Exception as e:
            file_info[os.path.basename(f)] = f"ERROR: {str(e)[:50]}"

    return total_records, len(files), file_info


def main() -> None:
    print("=" * 70)
    print("MEDALLION PIPELINE DIAGNOSIS")
    print(f"BASE_DIR: {BASE_DIR}")
    print("=" * 70)

    bronze_records, bronze_files, bronze_info = count_records_in_layer("bronze")
    silver_records, silver_files, silver_info = count_records_in_layer("silver")
    gold_records, gold_files, gold_info = count_records_in_layer("gold")

    print(f"\nRECORD COUNTS:")
    print(f"  Bronze: {bronze_records:,} records in {bronze_files} files")
    print(f"  Silver: {silver_records:,} records in {silver_files} files (cleaned/*.csv only)")
    print(f"  Gold:   {gold_records:,} records in {gold_files} files")

    print(f"\nTRANSFORMATION RATES (heuristic; layers are not 1:1 row copies):")
    if bronze_records > 0:
        bronze_to_silver_rate = (silver_records / bronze_records) * 100
        print(f"  Bronze vs Silver (row sum ratio): {bronze_to_silver_rate:.1f}%")
    else:
        print("  Bronze: no data")

    if silver_records > 0:
        silver_to_gold_rate = (gold_records / silver_records) * 100
        print(f"  Silver vs Gold (row sum ratio):   {silver_to_gold_rate:.1f}%")
    else:
        print("  Silver: no cleaned data")

    print(f"\nTOP FILES BY RECORD COUNT:")
    print("\n  Bronze:")
    for fname, count in sorted(bronze_info.items(), key=lambda x: -x[1] if isinstance(x[1], int) else -1)[:3]:
        print(f"    - {fname}: {count if isinstance(count, str) else f'{count:,} records'}")

    print("\n  Silver:")
    if silver_info:
        for fname, count in sorted(silver_info.items(), key=lambda x: -x[1] if isinstance(x[1], int) else -1)[:3]:
            print(f"    - {fname}: {count if isinstance(count, str) else f'{count:,} records'}")
    else:
        print("    (no files)")

    print("\n  Gold:")
    if gold_info:
        for fname, count in sorted(gold_info.items(), key=lambda x: -x[1] if isinstance(x[1], int) else -1)[:3]:
            print(f"    - {fname}: {count if isinstance(count, str) else f'{count:,} records'}")
    else:
        print("    (no files)")

    print("\nHINTS:")
    if bronze_records > 0 and silver_records == 0:
        print("  Bronze has data but Silver cleaned is empty — run bronze-to-silver (e.g. POST /api/actions/bronze-to-silver).")
    elif bronze_records > silver_records and bronze_records > 0 and (bronze_records - silver_records) / bronze_records > 0.2:
        print("  Large gap Bronze vs Silver cleaned — some tables may not have been cleaned yet.")
    else:
        print("  Bronze vs Silver cleaned: looks consistent or not applicable.")

    if silver_records > 0 and gold_records == 0:
        print("  Silver cleaned exists but Gold curated empty — run silver-to-gold (e.g. POST /api/actions/silver-to-gold).")
    elif silver_records > gold_records and silver_records > 0 and (silver_records - gold_records) / silver_records > 0.2:
        print("  Large gap Silver vs Gold — curation may be partial or gold uses subset of columns.")
    else:
        print("  Silver vs Gold: OK or not applicable.")

    print("\nNEXT STEPS:")
    print("  - Trigger pipeline via API or run scripts/s02, s03, s05 under data_architecture.")
    print("=" * 70)


if __name__ == "__main__":
    main()
