import os
import pandas as pd
from sklearn.model_selection import train_test_split

GOLD_CURATED = os.path.join("gold", "curated")
ML_READY_DIR = os.path.join("gold", "ml_ready")
os.makedirs(ML_READY_DIR, exist_ok=True)


def prepare_product_features(source_path=None, output_baseline=True):
    """Load `ml_features_gold.csv`, create a binary label `sold` (transaction_count > 0),
    simple preprocessing (fillna, one-hot category), and save processed features.

    Returns: DataFrame of processed features
    """
    if source_path is None:
        source_path = os.path.join(GOLD_CURATED, "ml_features_gold.csv")

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"ML features not found: {source_path}")

    df = pd.read_csv(source_path)

    # Basic label: whether product had any transactions
    df["sold"] = (df["transaction_count"].fillna(0) > 0).astype(int)

    # Keep useful numeric columns and category
    keep_cols = ["product_id", "category_standardized", "price_lkr", "stock_count", "total_quantity", "transaction_count", "total_revenue", "sold"]
    df = df[[c for c in keep_cols if c in df.columns]]

    # Fill numeric missing values
    num_cols = [c for c in df.columns if c not in ["product_id", "category_standardized", "sold"]]
    df[num_cols] = df[num_cols].fillna(0)

    # Simple one-hot encode category (limits columns to top 20 categories)
    if "category_standardized" in df.columns:
        top_cats = df["category_standardized"].fillna("__NA__").value_counts().nlargest(20).index.tolist()
        df["category_standardized"] = df["category_standardized"].fillna("__NA__")
        for c in top_cats:
            df[f"cat_{c}"] = (df["category_standardized"] == c).astype(int)
        df = df.drop(columns=["category_standardized"])

    # Save baseline and latest
    timestamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    baseline_path = os.path.join(ML_READY_DIR, f"product_features_{timestamp}.csv")
    latest_path = os.path.join(ML_READY_DIR, "product_features_latest.csv")

    if output_baseline:
        df.to_csv(baseline_path, index=False)
    df.to_csv(latest_path, index=False)

    print(f"Saved features: {latest_path} (baseline: {baseline_path}) | rows: {len(df)}, cols: {len(df.columns)}")

    return df


if __name__ == "__main__":
    prepare_product_features()
