from __future__ import annotations

import argparse
from pathlib import Path
import sys

import joblib
import pandas as pd

try:
    from xgboost import XGBRanker
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"XGBoost is required to train the LambdaMART ranker: {exc}")

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.agentic_ai.agents.ltr_support import (  # noqa: E402
    FEATURE_ORDER,
    RankingDataset,
    build_bootstrap_ranking_dataset,
    evaluate_grouped_predictions,
    model_payload,
    split_by_query,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the Agentic AI LambdaMART ranker.")
    parser.add_argument(
        "--catalog",
        default=str(BACKEND_ROOT / "data" / "raw" / "final_products.csv"),
        help="Product catalog CSV used to bootstrap ranking data.",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_ROOT / "src" / "services" / "agentic_ai" / "agents" / "models" / "ltr" / "lambdamart_ranker.joblib"),
        help="Path to write the trained ranker artifact.",
    )
    parser.add_argument(
        "--dataset-out",
        default=str(BACKEND_ROOT / "data" / "processed" / "agentic_featureops" / "lambdamart_training_dataset.csv"),
        help="Optional path to save the generated grouped ranking dataset.",
    )
    parser.add_argument("--max-queries-per-category", type=int, default=20)
    parser.add_argument("--candidates-per-query", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_bootstrap_ranking_dataset(
        catalog_csv=args.catalog,
        max_queries_per_category=args.max_queries_per_category,
        candidates_per_query=args.candidates_per_query,
    )
    train_frame, test_frame = split_by_query(dataset.frame, train_ratio=0.8)
    train = RankingDataset(train_frame, FEATURE_ORDER)
    test = RankingDataset(test_frame, FEATURE_ORDER)
    X_train, y_train, group_train = train.to_xy_groups()
    X_test, y_test, group_test = test.to_xy_groups()

    ranker = XGBRanker(
        objective="rank:ndcg",
        n_estimators=140,
        learning_rate=0.08,
        max_depth=6,
        min_child_weight=2,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.2,
        random_state=42,
    )
    ranker.fit(
        X_train,
        y_train,
        group=group_train,
        eval_set=[(X_test, y_test)],
        eval_group=[group_test],
        verbose=False,
    )

    test_predictions = ranker.predict(X_test)
    metrics = evaluate_grouped_predictions(test_frame, test_predictions, k=6)

    dataset_out = Path(args.dataset_out)
    dataset_out.parent.mkdir(parents=True, exist_ok=True)
    dataset.frame.to_csv(dataset_out, index=False)

    artifact_path = Path(args.output)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = model_payload(
        model=ranker,
        metrics=metrics,
        dataset_rows=len(dataset.frame),
        dataset_queries=dataset.frame["query_id"].nunique(),
        source_catalog=str(Path(args.catalog).resolve()),
    )
    joblib.dump(payload, artifact_path)

    print(f"Training dataset saved to: {dataset_out}")
    print(f"Model artifact saved to: {artifact_path}")
    print("Offline metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")


if __name__ == "__main__":
    main()
