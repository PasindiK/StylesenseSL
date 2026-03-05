# scripts/s02_bronze_to_silver_cleaned.py
import os
import pandas as pd
from datetime import datetime

BRONZE_DIR = "bronze/raw"
SILVER_CLEANED_DIR = "silver/cleaned"
os.makedirs(SILVER_CLEANED_DIR, exist_ok=True)

def clean_file(input_path: str, output_path: str):
    """
    Clean a CSV file:
    - Remove duplicates
    - Handle nulls
    - Standardize string columns
    - Add quality score
    Returns structured summary.
    """
    df = pd.read_csv(input_path)
    original_count = len(df)
    
    print(f"\n{'='*60}")
    print(f"CLEANING: {os.path.basename(input_path)} | {original_count} records")
    print(f"{'='*60}")
    
    # 1. Remove duplicates
    df = df.drop_duplicates(keep='first')
    duplicates_removed = original_count - len(df)
    
    # 2. Count nulls
    null_counts = df.isnull().sum()
    null_summary = null_counts[null_counts > 0].to_dict()
    
    # 3. Standardize text columns
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip().str.lower()
        df[col] = df[col].replace({'nan': pd.NA})  # convert string "nan" back to NA
    
    # 4. Add cleaning metadata
    df['_cleaned_at'] = datetime.utcnow().isoformat()
    
    # 5. Compute simple DQ score
    total_cells = len(df) * len(df.columns)
    total_nulls = df.isnull().sum().sum()
    null_ratio = total_nulls / total_cells if total_cells > 0 else 0
    dq_score = int(100 * (1 - null_ratio))
    df['_dq_score'] = dq_score
    
    # Save cleaned CSV
    df.to_csv(output_path, index=False)
    print(f"Saved cleaned file to: {output_path}")
    
    summary = {
        "records_original": original_count,
        "records_cleaned": len(df),
        "duplicates_removed": duplicates_removed,
        "null_summary": null_summary,
        "dq_score": dq_score
    }
    
    return summary

# --------------------------------------------------
# Allow runpy integration from Bronze uploader
# --------------------------------------------------
if __name__ == "__main__":
    INPUT_FILE = globals().get("INPUT_FILE")
    TABLE_NAME = globals().get("TABLE_NAME", "unknown")
    
    if not INPUT_FILE or not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"INPUT_FILE not found: {INPUT_FILE}")
    
    silver_path = os.path.join(SILVER_CLEANED_DIR, os.path.basename(INPUT_FILE).replace('_raw.csv', '_cleaned.csv'))
    summary = clean_file(INPUT_FILE, silver_path)
    
    print(f"\n{'='*60}")
    print(f"SILVER CLEANING COMPLETE | Table: {TABLE_NAME}")
    print(f"Summary: {summary}")
    print(f"{'='*60}")
