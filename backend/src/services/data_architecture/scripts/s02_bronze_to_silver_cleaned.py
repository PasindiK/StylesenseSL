# scripts/s02_bronze_to_silver_cleaned.py
import os
import pandas as pd
from datetime import datetime

BRONZE_DIR = "medallions/bronze/raw"
SILVER_CLEANED_DIR = "medallions/silver/cleaned"
os.makedirs(SILVER_CLEANED_DIR, exist_ok=True)

# Map dataset/table names to their unique identifier columns
UNIQUE_ID_COLUMNS = {
    'users': 'user_id',
    'products': 'product_id',
    'transactions': 'item_id',
    'shops': 'shop_id',
    'trends': 'trend_id',
    'interactions': 'interaction_id',
    'user_preferences': 'preference_id',
}

def _extract_table_type_from_name(table_name: str) -> str:
    """Extract the table type from table name for ID column lookup."""
    table_lower = table_name.lower()
    for key in UNIQUE_ID_COLUMNS.keys():
        if key in table_lower:
            return key
    return None

def clean_file(input_path: str, output_path: str, table_name: str = None):
    """
    Clean a CSV file:
    - Remove duplicates based on unique ID column
    - Handle nulls
    - Standardize string columns
    - Add quality score
    Returns structured summary.
    """
    df = pd.read_csv(input_path)
    original_count = len(df)
    
    print(f"\n{'='*60}")
    print(f"CLEANING: {os.path.basename(input_path)} | {original_count} records")
    print(f"Table: {table_name}")
    print(f"{'='*60}")
    
    # 1. Remove duplicates based on unique ID column
    unique_id_col = None
    if table_name:
        table_type = _extract_table_type_from_name(table_name)
        if table_type and table_type in UNIQUE_ID_COLUMNS:
            unique_id_col = UNIQUE_ID_COLUMNS[table_type]
    
    # Check if the unique ID column exists in the dataframe
    if unique_id_col and unique_id_col in df.columns:
        df = df.drop_duplicates(subset=[unique_id_col], keep='first')
        duplicates_removed = original_count - len(df)
        print(f"✓ Deduplicated by '{unique_id_col}': removed {duplicates_removed} duplicate records")
    else:
        if unique_id_col:
            print(f"⚠ Expected unique ID column '{unique_id_col}' not found. Available columns: {list(df.columns)}")
        # Fallback: no deduplication if ID column not found
        duplicates_removed = 0
        print(f"⚠ No deduplication performed - cannot identify unique ID column")
    
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
    summary = clean_file(INPUT_FILE, silver_path, table_name=TABLE_NAME)
    
    print(f"\n{'='*60}")
    print(f"SILVER CLEANING COMPLETE | Table: {TABLE_NAME}")
    print(f"Summary: {summary}")
    print(f"{'='*60}")
