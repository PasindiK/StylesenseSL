"""Train a lightweight PKL intent classifier for orchestrator fallback.

Usage:
  python -m src.services.agentic_ai.scripts.train_intent_pkl \
    --data src/services/agentic_ai/data/intent/intent_dataset_8400.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Train PKL intent classifier")
    parser.add_argument(
        "--data",
        default="src/services/agentic_ai/data/intent/intent_dataset_8400.csv",
        help="CSV with text,label columns",
    )
    parser.add_argument(
        "--output-dir",
        default="src/services/agentic_ai/agents/models/intent_pkl",
        help="Directory where PKL model files will be written",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    if "text" not in df.columns or "label" not in df.columns:
        raise ValueError("Dataset must include text,label columns")

    df = df.dropna(subset=["text", "label"]).copy()
    labels = sorted(df["label"].astype(str).unique().tolist())
    label_to_id = {label: idx for idx, label in enumerate(labels)}

    x = df["text"].astype(str).tolist()
    y = [label_to_id[str(label)] for label in df["label"].astype(str).tolist()]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    max_features=30000,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )

    pipeline.fit(x_train, y_train)
    score = float(pipeline.score(x_test, y_test))

    vectorizer = pipeline.named_steps["tfidf"]
    model = pipeline.named_steps["clf"]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, out_dir / "intent_classifier_model.pkl")
    joblib.dump(vectorizer, out_dir / "intent_classifier_vectorizer.pkl")
    (out_dir / "intent_classifier_labels.json").write_text(
        json.dumps(labels, indent=2), encoding="utf-8"
    )
    (out_dir / "intent_classifier_eval.json").write_text(
        json.dumps({"accuracy": score, "rows": int(len(df))}, indent=2), encoding="utf-8"
    )

    print(json.dumps({"status": "ok", "accuracy": score, "output_dir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    main()
