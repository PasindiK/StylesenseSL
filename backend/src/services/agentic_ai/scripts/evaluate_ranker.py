from __future__ import annotations

import argparse
from pathlib import Path
import sys

import joblib
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.agentic_ai.agents.ltr_support import (  # noqa: E402
    FEATURE_ORDER,
    RankingDataset,
    build_bootstrap_ranking_dataset,
    evaluate_grouped_predictions,
    split_by_query,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Agentic AI LambdaMART ranker.")
    parser.add_argument(
        "--model",
        default=str(BACKEND_ROOT / "src" / "services" / "agentic_ai" / "agents" / "models" / "ltr" / "lambdamart_ranker.joblib"),
        help="Path to the saved LambdaMART artifact.",
    )
    parser.add_argument(
        "--dataset",
        default="",
        help="Optional prebuilt grouped ranking dataset CSV. If omitted, a bootstrap dataset is generated from the catalog.",
    )
    parser.add_argument(
        "--catalog",
        default=str(BACKEND_ROOT / "data" / "raw" / "final_products.csv"),
        help="Catalog CSV used when auto-generating the evaluation dataset.",
    )
    return parser.parse_args()


def load_dataset(args: argparse.Namespace) -> pd.DataFrame:
    if args.dataset:
        return pd.read_csv(args.dataset)
    dataset = build_bootstrap_ranking_dataset(args.catalog)
    return dataset.frame


def main() -> None:
    args = parse_args()
    artifact = joblib.load(args.model)
    model = artifact["model"] if isinstance(artifact, dict) and "model" in artifact else artifact

    frame = load_dataset(args)
    _, test_frame = split_by_query(frame, train_ratio=0.8)
    test = RankingDataset(test_frame, FEATURE_ORDER)
    X_test, _, _ = test.to_xy_groups()
    predictions = model.predict(X_test)
    metrics = evaluate_grouped_predictions(test_frame, predictions, k=6)

    print("Evaluation metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")


if __name__ == "__main__":
    main()
