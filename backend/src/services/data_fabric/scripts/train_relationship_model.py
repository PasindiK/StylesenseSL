"""Train and evaluate relationship inference model on synthetic data.

Outputs:
- models/relationship_model_v1.pkl
- models/relationship_feature_importance_v1.csv
- models/relationship_metrics_v1.json
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integration.behavioral_features import BehavioralFeatureExtractor
from src.integration.feature_vector_builder import FeatureVectorBuilder
from src.integration.statistical_features import StatisticalFeatureExtractor
from src.integration.structural_features import StructuralFeatureExtractor
from src.scoring.model_training import RelationshipModelTrainer


def generate_customers(n: int = 600) -> pd.DataFrame:
    first_names = ["Alex", "Sam", "Jordan", "Taylor", "Casey", "Riley", "Jamie", "Morgan"]
    last_names = ["Perera", "Silva", "Fernando", "Jayasuriya", "Deen", "Mendis", "Norton", "Dias"]
    names = [f"{random.choice(first_names)} {random.choice(last_names)}" for _ in range(n)]
    emails = [f"user{i}@example.com" for i in range(1, n + 1)]
    return pd.DataFrame(
        {
            "customer_id": np.arange(1, n + 1),
            "name": names,
            "email": emails,
            "age": np.random.randint(18, 70, n),
        }
    )


def generate_orders(customers: pd.DataFrame, n: int = 1400) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": np.arange(1, n + 1),
            "customer_id": np.random.choice(customers["customer_id"], n),
            "amount": np.round(np.random.uniform(10, 500, n), 2),
        }
    )


def generate_payments(orders: pd.DataFrame, customers: pd.DataFrame, n: int = 1100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "payment_id": np.arange(1, n + 1),
            "order_ref": np.random.choice(orders["order_id"], n),
            "client_id": np.random.choice(customers["customer_id"], n),
            "payment_amount": np.round(np.random.uniform(10, 500, n), 2),
        }
    )


def generate_noise_dataset(n: int = 800) -> pd.DataFrame:
    vocabulary = ["alpha", "beta", "gamma", "delta", "omega", "vector", "mesh", "fabric"]
    return pd.DataFrame(
        {
            "random_id": np.arange(10000, 10000 + n),
            "description": [random.choice(vocabulary) for _ in range(n)],
            "value": np.random.randn(n),
            "client_code": np.random.randint(1, 1200, n),
        }
    )


def introduce_noise(df: pd.DataFrame, column: str, noise_ratio: float = 0.05) -> pd.DataFrame:
    out = df.copy()
    n_noise = int(len(out) * noise_ratio)
    if n_noise <= 0:
        return out
    indices = np.random.choice(out.index, n_noise, replace=False)
    out.loc[indices, column] = None
    return out


def reduce_overlap(df: pd.DataFrame, column: str, keep_ratio: float = 0.8) -> pd.DataFrame:
    out = df.copy()
    unique_vals = out[column].dropna().unique()
    if len(unique_vals) == 0:
        return out
    keep_count = max(1, int(len(unique_vals) * keep_ratio))
    keep_vals = np.random.choice(unique_vals, keep_count, replace=False)
    return out[out[column].isin(keep_vals)].copy()


def build_dataset() -> Dict[str, pd.DataFrame]:
    np.random.seed(42)
    random.seed(42)

    customers = generate_customers()
    orders = generate_orders(customers=customers)
    payments = generate_payments(orders=orders, customers=customers)
    noise = generate_noise_dataset()

    customers = introduce_noise(customers, "customer_id", 0.05)
    orders = introduce_noise(orders, "customer_id", 0.05)
    payments = reduce_overlap(payments, "client_id", 0.8)

    return {
        "Customers": customers,
        "Orders": orders,
        "Payments": payments,
        "Noise": noise,
    }


def build_ground_truth() -> Dict[Tuple[str, str], int]:
    truth = {
        ("Customers.customer_id", "Orders.customer_id"): 1,
        ("Customers.customer_id", "Payments.client_id"): 1,
        ("Orders.order_id", "Payments.order_ref"): 1,
    }
    return {tuple(sorted(k)): v for k, v in truth.items()}


def generate_labeled_vectors(datasets: Dict[str, pd.DataFrame]) -> Tuple[List[Dict[str, float]], List[int]]:
    structural = StructuralFeatureExtractor()
    statistical = StatisticalFeatureExtractor(sample_size=5000)
    behavioral = BehavioralFeatureExtractor()
    builder = FeatureVectorBuilder(
        structural_extractor=structural,
        statistical_extractor=statistical,
        behavioral_extractor=behavioral,
        version="v1.0",
    )

    ground_truth = build_ground_truth()

    feature_vectors: List[Dict[str, float]] = []
    labels: List[int] = []

    names = sorted(datasets.keys())
    for i, ds1_name in enumerate(names):
        for ds2_name in names[i + 1 :]:
            df1 = datasets[ds1_name]
            df2 = datasets[ds2_name]

            for col1 in df1.columns:
                for col2 in df2.columns:
                    key = tuple(sorted((f"{ds1_name}.{col1}", f"{ds2_name}.{col2}")))
                    label = 1 if key in ground_truth else 0

                    vector = builder.build(
                        left_dataset=ds1_name,
                        right_dataset=ds2_name,
                        left_column=col1,
                        right_column=col2,
                        left_series=df1[col1],
                        right_series=df2[col2],
                    )

                    feature_vectors.append(vector)
                    labels.append(label)

    return feature_vectors, labels


def main() -> int:
    datasets = build_dataset()
    feature_vectors, labels = generate_labeled_vectors(datasets)

    trainer = RelationshipModelTrainer(model_version="v1.0")
    X, y = trainer.prepare_dataset(feature_vectors, labels)
    _, X_test, _, y_test = trainer.train_model(
        X,
        y,
        test_size=0.2,
        model_type="random_forest",
        class_weight="balanced",
        positive_oversample_factor=3,
        hyperparameters={"n_estimators": 300, "min_samples_leaf": 2},
    )
    metrics = trainer.evaluate_model(X_test, y_test)

    base_dir = Path(__file__).resolve().parent.parent
    model_dir = base_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "relationship_model_v1.pkl"
    importance_path = model_dir / "relationship_feature_importance_v1.csv"
    metrics_path = model_dir / "relationship_metrics_v1.json"

    trainer.save_model(str(model_path))
    trainer.save_feature_importance(str(importance_path))
    trainer.save_metrics(metrics, str(metrics_path))

    print("Training completed")
    print(f"Total feature vectors: {len(feature_vectors)}")
    print(f"Positive labels: {sum(labels)}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"F1-score: {metrics['f1_score']:.4f}")
    print(f"ROC-AUC: {metrics['roc_auc']:.4f}")
    print(f"Model saved: {model_path}")
    print(f"Feature importance saved: {importance_path}")
    print(f"Metrics saved: {metrics_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
