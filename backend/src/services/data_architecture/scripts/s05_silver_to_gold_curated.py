# scripts/s04_gold_curation.py
import os
import pandas as pd
from datetime import datetime

SILVER_ENRICHED_DIR = "medallions/silver/enriched"
GOLD_DIR = "medallions/gold/curated"
os.makedirs(GOLD_DIR, exist_ok=True)

# ------------------------
# --- Helper Functions ---
# ------------------------

def find_enriched_file(prefix: str):
    """Find the latest enriched file that starts with the given prefix."""
    for fname in os.listdir(SILVER_ENRICHED_DIR):
        if fname.lower().startswith(prefix.lower()) and fname.lower().endswith("_enriched.csv"):
            return os.path.join(SILVER_ENRICHED_DIR, fname)
    raise FileNotFoundError(f"No enriched file found for prefix '{prefix}' in {SILVER_ENRICHED_DIR}")

def _curate_dataset(df: pd.DataFrame, dataset_type: str):
    """Add standard curated metadata"""
    df['_curated_at'] = datetime.now(datetime.utcnow().astimezone().tzinfo).isoformat()
    df['_dataset_type'] = dataset_type
    return df

# ------------------------
# --- Gold Curation ---
# ------------------------

def create_search_index():
    """Create search index for Search Agent"""
    print("\nCreating Search Index...")
    df = pd.read_csv(find_enriched_file("products"))

    search_index = df[[
        'product_id', 'name', 'category_standardized', 'color_standardized',
        'fabric_standardized', 'price_lkr', 'price_category', 'stock_status',
        'semantic_tags', '_enriched_at'
    ]].copy()

    search_index.rename(columns={
        'category_standardized': 'category',
        'color_standardized': 'color',
        'fabric_standardized': 'fabric',
        'price_lkr': 'price'
    }, inplace=True)

    search_index = _curate_dataset(search_index, 'search_index')

    path = os.path.join(GOLD_DIR, "search_index_gold.csv")
    search_index.to_csv(path, index=False)
    print(f" Search Index: {len(search_index)} products")
    return search_index

def create_inventory_snapshot():
    """Create inventory snapshot for Shop Agent"""
    print("\nCreating Inventory Snapshot...")
    df = pd.read_csv(find_enriched_file("products"))

    inventory = df[[
        'product_id', 'name', 'category_standardized', 'stock_count',
        'stock_status', 'price_lkr'
    ]].copy()

    inventory.rename(columns={
        'category_standardized': 'category',
        'price_lkr': 'price'
    }, inplace=True)

    inventory = _curate_dataset(inventory, 'inventory_snapshot')

    path = os.path.join(GOLD_DIR, "inventory_snapshot_gold.csv")
    inventory.to_csv(path, index=False)
    print(f" Inventory Snapshot: {len(inventory)} products")
    return inventory

def create_customer_profiles():
    """Create customer profiles for Data Fabric"""
    print("\nCreating Customer Profiles...")
    df = pd.read_csv(find_enriched_file("users"))

    profiles = df[[
        'user_id', 'name', 'email', 'email_domain', 'user_created_year'
    ]].copy()

    profiles = _curate_dataset(profiles, 'customer_profiles')

    path = os.path.join(GOLD_DIR, "customer_profiles_gold.csv")
    profiles.to_csv(path, index=False)
    print(f" Customer Profiles: {len(profiles)} users")
    return profiles

def create_ml_ready_features():
    """Create ML-ready feature set"""
    print("\nCreating ML-Ready Features...")
    products_df = pd.read_csv(find_enriched_file("products"))
    transactions_df = pd.read_csv(find_enriched_file("transactions"))

    # Aggregate transaction data by product
    product_stats = transactions_df.groupby('product_id').agg({
        'quantity': ['sum', 'mean', 'count'],
        'final_amount': ['sum', 'mean']
    }).reset_index()

    # Flatten MultiIndex columns
    product_stats.columns = [
        'product_id', 'total_quantity', 'avg_quantity',
        'transaction_count', 'total_revenue', 'avg_transaction_value'
    ]

    # Merge with product info
    features = products_df[[
        'product_id', 'category_standardized', 'price_lkr',
        'stock_count', 'price_category'
    ]].merge(product_stats, on='product_id', how='left').fillna(0)

    features = _curate_dataset(features, 'ml_features')

    path = os.path.join(GOLD_DIR, "ml_features_gold.csv")
    features.to_csv(path, index=False)
    print(f"  ML Features: {len(features)} products with {len(features.columns)} features")
    return features

# ------------------------
# --- Main Execution ---
# ------------------------

if __name__ == "__main__":
    print("\n" + "="*70)
    print("GOLD LAYER CURATION")
    print("="*70)

    create_search_index()
    create_inventory_snapshot()
    create_customer_profiles()
    create_ml_ready_features()

    print("\n" + "="*70)
    print("GOLD CURATION COMPLETE")
    print("="*70 + "\n")
