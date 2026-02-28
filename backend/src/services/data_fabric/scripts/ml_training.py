"""ML model training automation script.

Usage:
    python scripts/ml_training.py --dataset data/train.csv --model logistic_regression --config config.json
"""

import argparse
import logging
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.logging_config import setup_logging, get_logger
from src.ml_engine import ModelTrainer, SklearnTrainer, TrainingConfig
import pandas as pd

logger = get_logger(__name__)


def train_model(
    dataset_path: str, model_type: str, hyperparameters: dict = None
) -> None:
    """Train an ML model.

    Args:
        dataset_path: Path to training dataset
        model_type: Type of model to train
        hyperparameters: Model hyperparameters
    """
    logger.info(f"Starting ML model training: {model_type}")

    # Load data
    df = pd.read_csv(dataset_path)
    logger.info(f"Loaded dataset: {len(df)} rows, {len(df.columns)} columns")

    # Prepare features and target
    X = df.drop("target", axis=1) if "target" in df.columns else df.iloc[:, :-1]
    y = df["target"] if "target" in df.columns else df.iloc[:, -1]

    # Create training config
    config = TrainingConfig(
        model_type=model_type,
        hyperparameters=hyperparameters or {},
    )

    # Train model
    trainer = SklearnTrainer(config)
    results = trainer.train_and_evaluate(X, y)

    print("\n" + "=" * 50)
    print("MODEL TRAINING RESULTS")
    print("=" * 50)
    print(f"Model Type: {results['model_type']}")
    print(f"Train Size: {results['train_size']}")
    print(f"Test Size: {results['test_size']}")
    print(f"\nEvaluation Metrics:")
    for metric, value in results["evaluation_results"].items():
        print(f"  {metric}: {value:.4f}")

    logger.info("Model training completed successfully")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Data Fabric ML Training Script")
    parser.add_argument("--dataset", required=True, help="Path to training dataset")
    parser.add_argument(
        "--model",
        default="logistic_regression",
        choices=["logistic_regression", "random_forest", "svm"],
        help="Model type",
    )
    parser.add_argument("--config", help="Path to hyperparameters JSON")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    setup_logging()
    logging.getLogger().setLevel(args.log_level)

    logger.info("ML training script started")

    try:
        # Load hyperparameters if provided
        hyperparameters = {}
        if args.config and Path(args.config).exists():
            with open(args.config, "r") as f:
                hyperparameters = json.load(f)

        train_model(args.dataset, args.model, hyperparameters)
        logger.info("ML training completed")

    except Exception as e:
        logger.error(f"ML training failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
