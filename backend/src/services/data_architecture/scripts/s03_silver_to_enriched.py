# scripts/s03_silver_to_enriched.py
import os
import pandas as pd
from datetime import datetime

SILVER_CLEANED_DIR = "medallions/silver/cleaned"
SILVER_ENRICHED_DIR = "medallions/silver/enriched"
os.makedirs(SILVER_ENRICHED_DIR, exist_ok=True)

# --- Enrichment functions --- #

def enrich_products(df):
    df.columns = df.columns.str.strip().str.lower()
    
    df['category_standardized'] = df.get('category', pd.Series('Unknown')).astype(str).str.upper()
    
    color_map = {'red': 'Red', 'blue': 'Blue', 'black': 'Black', 'white': 'White',
                 'green': 'Green', 'yellow': 'Yellow'}
    df['color_standardized'] = df.get('color', pd.Series('Unknown')).apply(
        lambda x: color_map.get(str(x).lower(), str(x).title()) if pd.notna(x) else 'Unknown'
    )
    
    fabric_map = {'cotton': 'Cotton', 'wool': 'Wool', 'silk': 'Silk',
                  'denim': 'Denim', 'polyester': 'Polyester'}
    df['fabric_standardized'] = df.get('fabric', pd.Series('Unknown')).apply(
        lambda x: fabric_map.get(str(x).lower(), str(x).title()) if pd.notna(x) else 'Unknown'
    )
    
    def price_category(price):
        try:
            price = float(price)
            if price < 2000: return 'Budget'
            elif price < 5000: return 'Mid-Range'
            else: return 'Premium'
        except: return 'Unknown'
    
    df['price_category'] = df.get('price_lkr', pd.Series('Unknown')).apply(price_category)
    
    def stock_status(count):
        try:
            count = float(count)
            if count == 0: return 'Out of Stock'
            elif count < 5: return 'Low Stock'
            else: return 'In Stock'
        except: return 'Unknown'
    
    df['stock_status'] = df.get('stock_count', pd.Series('Unknown')).apply(stock_status)
    
    # Semantic tags
    tag_cols = ['category_standardized', 'color_standardized', 'fabric_standardized', 'price_category', 'stock_status']
    df['semantic_tags'] = df.apply(lambda row: ', '.join([str(row[c]).lower() for c in tag_cols if c in row]), axis=1)
    
    df['_enriched_at'] = datetime.utcnow().isoformat()
    return df


def enrich_users(df):
    df.columns = df.columns.str.strip().str.lower()
    
    df['email_domain'] = df.get('email', pd.Series('unknown')).apply(
        lambda x: str(x).split('@')[1] if pd.notna(x) and '@' in str(x) else 'unknown'
    )
    
    # Ensure we pass a Series to to_datetime (df.get may return scalar)
    created_series = df['created_at'] if 'created_at' in df.columns else pd.Series([pd.NaT] * len(df))
    df['user_created_year'] = pd.to_datetime(created_series, errors='coerce').dt.year
    
    df['_enriched_at'] = datetime.utcnow().isoformat()
    return df


def enrich_transactions(df):
    df.columns = df.columns.str.strip().str.lower()
    
    df['transaction_date'] = pd.to_datetime(df.get('transaction_date', pd.NaT), errors='coerce')
    df['transaction_year_month'] = df['transaction_date'].dt.to_period('M')
    
    df['_enriched_at'] = datetime.utcnow().isoformat()
    return df


# --- Dispatcher --- #

def enrich_file(input_path, output_path, table_name):
    print(f"\nEnriching: {os.path.basename(input_path)}")
    
    df = pd.read_csv(input_path)
    
    # Preserve cleaning metadata if exists
    dq_score = df.get('_dq_score', pd.NA).iloc[0] if '_dq_score' in df.columns else pd.NA
    cleaned_at = df.get('_cleaned_at', pd.NA).iloc[0] if '_cleaned_at' in df.columns else pd.NA
    
    # Dispatch
    table_name = table_name.lower()
    if 'products' in table_name:
        df = enrich_products(df)
    elif 'users' in table_name:
        df = enrich_users(df)
    elif 'transactions' in table_name:
        df = enrich_transactions(df)
    
    # Restore cleaning metadata
    df['_dq_score'] = dq_score
    df['_cleaned_at'] = cleaned_at
    
    df.to_csv(output_path, index=False)
    
    summary = {
        "records": len(df),
        "columns": len(df.columns),
        "table": table_name
    }
    print(f"Enrichment complete | Table: {table_name} | Records: {len(df)} | Columns: {len(df.columns)}")
    return summary


# --- Main --- #

if __name__ == "__main__":
    TABLE_NAME = globals().get("TABLE_NAME", "unknown")
    INPUT_FILE = globals().get("INPUT_FILE")
    
    if not INPUT_FILE or not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"INPUT_FILE not found: {INPUT_FILE}")
    
    enriched_path = os.path.join(SILVER_ENRICHED_DIR, os.path.basename(INPUT_FILE).replace('_cleaned.csv', '_enriched.csv'))
    summary = enrich_file(INPUT_FILE, enriched_path, TABLE_NAME)
    
    print(f"\nSILVER ENRICHMENT COMPLETE - {summary}")
