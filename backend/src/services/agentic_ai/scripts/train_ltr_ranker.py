from __future__ import annotations

from pathlib import Path
import sys

import joblib
import numpy as np

try:
    from xgboost import XGBRanker
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"XGBoost is required to train the LambdaMART ranker: {exc}")

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


FEATURE_ORDER = [
    "semantic_similarity",
    "intent_match",
    "profile_affinity",
    "behavior_affinity",
    "collaborative_affinity",
    "price_fit",
    "popularity_signal",
    "context_signal",
    "trust_signal",
]


def build_synthetic_training_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    labels = []
    groups = []
    rng = np.random.default_rng(42)

    for _query_idx in range(60):
        group_size = 8
        groups.append(group_size)
        for rank_idx in range(group_size):
            semantic = float(max(0.0, min(1.0, 0.95 - (rank_idx * 0.08) + rng.normal(0, 0.03))))
            intent_match = float(max(0.0, min(1.0, 0.90 - (rank_idx * 0.09) + rng.normal(0, 0.04))))
            profile = float(max(0.0, min(1.0, 0.85 - (rank_idx * 0.06) + rng.normal(0, 0.05))))
            behavior = float(max(0.0, min(1.0, 0.75 - (rank_idx * 0.05) + rng.normal(0, 0.05))))
            collaborative = float(max(0.0, min(1.0, 0.70 - (rank_idx * 0.04) + rng.normal(0, 0.05))))
            price_fit = float(max(0.0, min(1.0, 0.88 - (rank_idx * 0.05) + rng.normal(0, 0.04))))
            popularity = float(max(0.0, min(1.0, 0.80 - (rank_idx * 0.03) + rng.normal(0, 0.06))))
            context = float(max(0.6, min(1.2, 1.05 - (rank_idx * 0.02) + rng.normal(0, 0.03))))
            trust = 1.0 if rank_idx < 6 else 0.75
            rows.append([semantic, intent_match, profile, behavior, collaborative, price_fit, popularity, context, trust])
            labels.append(max(0, 4 - min(rank_idx, 4)))

    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float), np.asarray(groups, dtype=int)


def main() -> None:
    X, y, group = build_synthetic_training_data()
    ranker = XGBRanker(
        objective="rank:ndcg",
        n_estimators=80,
        learning_rate=0.08,
        max_depth=5,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
    )
    ranker.fit(X, y, group=group)

    model_dir = BACKEND_ROOT / "src" / "services" / "agentic_ai" / "agents" / "models" / "ltr"
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(ranker, model_dir / "lambdamart_ranker.joblib")
    print(f"Saved ranker to {model_dir / 'lambdamart_ranker.joblib'}")


if __name__ == "__main__":
    main()
