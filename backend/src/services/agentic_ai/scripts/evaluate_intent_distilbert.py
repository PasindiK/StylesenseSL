"""Evaluate calibrated DistilBERT intent model and export research-style metrics.

Usage examples:
python -m src.services.agentic_ai.scripts.evaluate_intent_distilbert \
  --data src/services/agentic_ai/data/intent/intent_dataset_8400.csv \
  --model-dir src/services/agentic_ai/agents/models/intent_distilbert

python -m src.services.agentic_ai.scripts.evaluate_intent_distilbert \
  --data src/services/agentic_ai/data/intent/intent_dataset_8400.csv \
  --eval-csv path/to/heldout.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def stratified_split(df: pd.DataFrame, test_size: float = 0.2, seed: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    train_idx = []
    val_idx = []
    for _, grp in df.groupby("label"):
        idx = grp.index.to_numpy()
        rng.shuffle(idx)
        cut = max(1, int(len(idx) * (1 - test_size)))
        train_idx.extend(idx[:cut])
        val_idx.extend(idx[cut:])
    train_df = df.loc[train_idx].sample(frac=1.0, random_state=seed).reset_index(drop=True)
    val_df = df.loc[val_idx].sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return train_df, val_df


def per_class_metrics(true_labels: List[str], pred_labels: List[str], label_order: List[str]) -> pd.DataFrame:
    rows = []
    true_arr = np.array(true_labels)
    pred_arr = np.array(pred_labels)

    for label in label_order:
        tp = int(((pred_arr == label) & (true_arr == label)).sum())
        fp = int(((pred_arr == label) & (true_arr != label)).sum())
        fn = int(((pred_arr != label) & (true_arr == label)).sum())
        support = int((true_arr == label).sum())

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
        rows.append(
            {
                "intent": label,
                "support": support,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )

    return pd.DataFrame(rows)


def predict_batch(
    texts: List[str],
    tokenizer: AutoTokenizer,
    model: AutoModelForSequenceClassification,
    id2label: Dict[str, str],
    temperature: float,
    batch_size: int,
) -> Tuple[List[str], np.ndarray]:
    preds: List[str] = []
    confs: List[float] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        enc = tokenizer(batch, truncation=True, padding=True, max_length=64, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits
            probs = torch.softmax(logits / max(temperature, 1e-6), dim=-1).cpu().numpy()

        idxs = probs.argmax(axis=1)
        for row_idx, cls_idx in enumerate(idxs):
            preds.append(id2label.get(str(int(cls_idx)), "product_search"))
            confs.append(float(probs[row_idx, cls_idx]))

    return preds, np.array(confs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DistilBERT intent model")
    parser.add_argument("--data", required=True, help="CSV with text,label columns (source dataset)")
    parser.add_argument("--eval-csv", default="", help="Optional dedicated evaluation CSV")
    parser.add_argument("--model-dir", default="src/services/agentic_ai/agents/models/intent_distilbert", help="Trained model directory")
    parser.add_argument("--holdout-ratio", type=float, default=0.2, help="Holdout split ratio when --eval-csv not provided")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    config_path = model_dir / "intent_inference_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing inference config: {config_path}")

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    id2label = cfg.get("id2label", {})
    label_order = [id2label[str(i)] for i in sorted([int(k) for k in id2label.keys()])]
    temperature = float(cfg.get("temperature", 1.0))
    threshold = float(cfg.get("confidence_threshold", 0.65))

    source_df = pd.read_csv(args.data)
    if "text" not in source_df.columns or "label" not in source_df.columns:
        raise ValueError("Input CSV must have columns: text,label")

    if args.eval_csv:
        eval_df = pd.read_csv(args.eval_csv)
    else:
        _, eval_df = stratified_split(source_df, test_size=args.holdout_ratio, seed=args.seed)

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()

    texts = eval_df["text"].astype(str).tolist()
    true_labels = eval_df["label"].astype(str).tolist()

    pred_labels, confidences = predict_batch(
        texts=texts,
        tokenizer=tokenizer,
        model=model,
        id2label=id2label,
        temperature=temperature,
        batch_size=args.batch_size,
    )

    correct = np.array(pred_labels) == np.array(true_labels)
    overall_accuracy = float(correct.mean())

    accepted = confidences >= threshold
    accepted_count = int(accepted.sum())
    fallback_count = int((~accepted).sum())
    accepted_accuracy = float(correct[accepted].mean()) if accepted_count > 0 else 0.0
    coverage = float(accepted.mean()) if len(accepted) > 0 else 0.0

    class_df = per_class_metrics(true_labels, pred_labels, label_order=label_order)
    macro_precision = float(class_df["precision"].mean())
    macro_recall = float(class_df["recall"].mean())
    macro_f1 = float(class_df["f1"].mean())

    cm = pd.crosstab(
        pd.Series(true_labels, name="true"),
        pd.Series(pred_labels, name="pred"),
        dropna=False,
    )

    report = {
        "evaluation_rows": int(len(eval_df)),
        "overall_accuracy": overall_accuracy,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "confidence_threshold": threshold,
        "accepted_count": accepted_count,
        "accepted_accuracy": accepted_accuracy,
        "coverage": coverage,
        "fallback_count": fallback_count,
        "temperature": temperature,
    }

    out_dir = model_dir / "evaluation_reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    class_df.to_csv(out_dir / "per_intent_metrics.csv", index=False)
    cm.to_csv(out_dir / "confusion_matrix.csv")

    print(json.dumps(report, indent=2))
    print(f"per_intent_metrics={out_dir / 'per_intent_metrics.csv'}")
    print(f"confusion_matrix={out_dir / 'confusion_matrix.csv'}")


if __name__ == "__main__":
    main()
