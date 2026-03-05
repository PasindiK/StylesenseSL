# scripts/s06_gold_ml_ready.py
import os
import pandas as pd
from datetime import datetime

GOLD_DIR = "gold/curated"
ML_READY_DIR = "gold/ml_ready"

os.makedirs(ML_READY_DIR, exist_ok=True)

def prepare_drift_training_data():
    """
    Prepare ML-ready features for schema drift detection.
    Stores a timestamped baseline and updates a 'latest' copy for easy access.
    """
    print("\nPreparing ML-Ready Features for Drift Detection...")

    # Load ML features from GOLD
    ml_features_path = os.path.join(GOLD_DIR, "ml_features_gold.csv")

    if not os.path.exists(ml_features_path):
        print("ML features not found in GOLD directory")
        return None

    df_features = pd.read_csv(ml_features_path)

    # Save timestamped baseline
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    baseline_path = os.path.join(ML_READY_DIR, f"drift_baseline_features_{timestamp}.csv")
    df_features.to_csv(baseline_path, index=False)
    print(f"Timestamped baseline saved: {baseline_path} | Records: {len(df_features)}, Features: {len(df_features.columns)}")

    # Update latest baseline (always points to most recent)
    latest_baseline_path = os.path.join(ML_READY_DIR, "drift_baseline_features_latest.csv")
    df_features.to_csv(latest_baseline_path, index=False)
    print(f"Latest baseline updated: {latest_baseline_path}")

    return df_features


if __name__ == "__main__":
    print("\n" + "="*70)
    print("ML FEATURE PREPARATION")
    print("="*70)

    prepare_drift_training_data()

    print("\n" + "="*70)
    print("ML PREPARATION COMPLETE")
    print("="*70 + "\n")
