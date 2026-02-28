"""
Lightweight data validation for CSV files placed in data/raw.
Generates a JSON manifest with row counts, missing value counts, and inferred dtypes.

Usage: python scripts/validate_data.py
"""
import os
import json
import pandas as pd
from pathlib import Path

RAW_DIR = Path("C:/TEST_RP/data/raw")
MANIFEST_DIR = Path("C:/TEST_RP/data/manifests")
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

manifest = {}
for csv_file in RAW_DIR.glob('*.csv'):
    name = csv_file.stem
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        manifest[name] = {"error": str(e)}
        continue
    info = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "columns_list": list(df.columns.astype(str)),
        "missing_per_column": df.isna().sum().astype(int).to_dict(),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "sample": df.head(3).to_dict(orient='records')
    }
    manifest[name] = info

out_path = MANIFEST_DIR / 'data_manifest.json'
with out_path.open('w', encoding='utf8') as f:
    json.dump(manifest, f, indent=2)

print(f"Manifest written to {out_path}")
