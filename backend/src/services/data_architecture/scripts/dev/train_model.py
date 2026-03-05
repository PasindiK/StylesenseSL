import os
import json
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib

ML_READY_DIR = os.path.join("gold", "ml_ready")
MODELS_DIR = "models"
os.makedirs(MODELS_DIR, exist_ok=True)


def train_product_classifier(feature_path=None, test_size=0.2, random_state=42):
    if feature_path is None:
        feature_path = os.path.join(ML_READY_DIR, "product_features_latest.csv")

    if not os.path.exists(feature_path):
        raise FileNotFoundError(f"Feature file not found: {feature_path}")

    df = pd.read_csv(feature_path)

    if "sold" not in df.columns:
        raise ValueError("Label column `sold` not found in features. Run prepare_features first.")

    # Drop identifier
    ids = df.get("product_id")
    X = df.drop(columns=[c for c in ["product_id", "sold"] if c in df.columns])
    y = df["sold"].astype(int)

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y if y.nunique()>1 else None)

    # Train a RandomForest baseline
    clf = RandomForestClassifier(n_estimators=200, random_state=random_state, n_jobs=-1)
    clf.fit(X_train, y_train)

    # Predict + evaluate
    y_pred = clf.predict(X_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test))
    }

    model_path = os.path.join(MODELS_DIR, "rf_product_classifier.joblib")
    joblib.dump(clf, model_path)

    metrics_path = os.path.join(MODELS_DIR, "rf_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"Model saved: {model_path}")
    print(f"Metrics saved: {metrics_path}")
    print(metrics)

    return clf, metrics


if __name__ == "__main__":
    train_product_classifier()
