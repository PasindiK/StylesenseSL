from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import math

import pandas as pd


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


@dataclass
class RankingDataset:
    frame: pd.DataFrame
    feature_order: Sequence[str]

    def to_xy_groups(self):
        import numpy as np

        X = self.frame[list(self.feature_order)].astype(float).to_numpy()
        y = self.frame["label"].astype(float).to_numpy()
        groups = self.frame.groupby("query_id").size().astype(int).to_numpy()
        return X, y, groups


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _tokenize(value: Any) -> List[str]:
    return [part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split() if part]


def _parse_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if "|" in raw:
        parts = raw.split("|")
    elif ";" in raw:
        parts = raw.split(";")
    else:
        parts = raw.split(",")
    return [str(item).strip().lower() for item in parts if str(item).strip()]


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _overlap_score(query: str, candidate_text: str) -> float:
    query_tokens = _tokenize(query)
    candidate_tokens = set(_tokenize(candidate_text))
    if not query_tokens or not candidate_tokens:
        return 0.35
    matches = sum(1 for token in query_tokens if token in candidate_tokens)
    return _clamp(matches / max(len(query_tokens), len(candidate_tokens)))


def _price_fit(price: float, budget: float) -> float:
    if budget <= 0:
        return 0.65
    if price <= budget:
        return 1.0
    return _clamp(1.0 - ((price - budget) / max(budget, 1.0)))


def _trust_signal(row: pd.Series) -> float:
    completeness = 0
    required = ["name", "category", "color", "fabric", "price", "style_tags", "product_url"]
    for field in required:
        if str(row.get(field, "")).strip():
            completeness += 1
    popularity = float(row.get("popularity_score") or 0.0)
    stock = float(row.get("stock_count") or 0.0)
    score = (completeness / len(required)) * 0.7
    score += 0.2 if popularity >= 3.0 else 0.1
    score += 0.1 if stock > 0 else 0.0
    return _clamp(score)


def _build_query_text(category: str, color: str, tags: Sequence[str], idx: int) -> Tuple[str, str]:
    occasion_candidates = [tag for tag in tags if tag in {"office", "formal", "casual", "summer", "winter", "party", "sporty", "beach wear"}]
    occasion = occasion_candidates[0] if occasion_candidates else ""
    templates = [
        f"{color} {category}",
        f"{occasion} {category}".strip(),
        f"{color} {occasion} {category}".strip(),
        f"best {category} under budget",
    ]
    query = " ".join(templates[idx % len(templates)].split())
    return query, occasion


def build_bootstrap_ranking_dataset(
    catalog_csv: str | Path,
    max_queries_per_category: int = 20,
    candidates_per_query: int = 12,
) -> RankingDataset:
    df = pd.read_csv(catalog_csv).copy()
    if "price" not in df.columns and "price_LKR" in df.columns:
        df["price"] = pd.to_numeric(df["price_LKR"], errors="coerce")
    else:
        df["price"] = pd.to_numeric(df.get("price"), errors="coerce")
    df["popularity_score"] = pd.to_numeric(df.get("popularity_score"), errors="coerce").fillna(2.5)
    df["stock_count"] = pd.to_numeric(df.get("stock_count"), errors="coerce").fillna(0)
    df["style_tags"] = df.get("style_tags", "").apply(_parse_tags)
    df["category"] = df.get("category", "").astype(str)
    df["color"] = df.get("color", "").astype(str)
    df["fabric"] = df.get("fabric", "").astype(str)
    df["name"] = df.get("name", "").astype(str)

    rows: List[Dict[str, Any]] = []
    query_id = 1

    for category, category_df in df.groupby("category", sort=True):
        if not str(category).strip():
            continue
        category_sorted = category_df.sort_values(["popularity_score", "stock_count"], ascending=[False, False]).reset_index(drop=True)
        anchor_count = min(max_queries_per_category, len(category_sorted))
        negatives = df[df["category"] != category].sort_values(["popularity_score", "stock_count"], ascending=[False, False]).reset_index(drop=True)

        for idx in range(anchor_count):
            anchor = category_sorted.iloc[idx]
            query_text, occasion = _build_query_text(str(anchor["category"]), str(anchor["color"]), anchor["style_tags"], idx)
            budget = float(anchor["price"]) * (1.08 if idx % 2 == 0 else 0.95)

            positive_pool = category_sorted.head(max(candidates_per_query, 8))
            negative_slice = negatives.iloc[(idx * 3) % max(len(negatives), 1):(idx * 3) % max(len(negatives), 1) + max(4, candidates_per_query // 3)]
            candidate_pool = pd.concat([positive_pool, negative_slice], ignore_index=True).drop_duplicates(subset=["product_id"]).head(candidates_per_query)

            for _, candidate in candidate_pool.iterrows():
                tags = candidate["style_tags"]
                semantic_similarity = _overlap_score(query_text, f"{candidate['name']} {candidate['category']} {candidate['color']} {' '.join(tags)}")

                intent_match = 0.0
                if _lower(candidate["category"]) == _lower(category):
                    intent_match += 0.55
                if _lower(candidate["color"]) == _lower(anchor["color"]):
                    intent_match += 0.25
                if occasion and occasion in tags:
                    intent_match += 0.20
                intent_match = _clamp(intent_match)

                tag_overlap = len(set(tags) & set(anchor["style_tags"]))
                profile_affinity = _clamp(0.35 + (tag_overlap * 0.18) + (0.12 if _lower(candidate["fabric"]) == _lower(anchor["fabric"]) else 0.0))
                popularity_signal = _clamp(float(candidate["popularity_score"]) / 5.0)
                behavior_affinity = _clamp((popularity_signal * 0.75) + (0.25 if float(candidate["stock_count"]) > 0 else 0.0))
                collaborative_affinity = _clamp((popularity_signal * 0.6) + (0.25 if _lower(candidate["color"]) == _lower(anchor["color"]) else 0.05))
                price_fit = _price_fit(float(candidate["price"]), budget)
                context_signal = _clamp(1.0 + (0.08 if occasion and occasion in tags else 0.0) + (0.04 if "travel friendly" in tags else 0.0), 0.6, 1.2)
                trust_signal = _trust_signal(candidate)

                label = 0
                if _lower(candidate["category"]) == _lower(category):
                    label = 2
                    if _lower(candidate["color"]) == _lower(anchor["color"]):
                        label += 1
                    if price_fit >= 0.9:
                        label += 1
                    if occasion and occasion in tags:
                        label = min(4, label + 1)
                elif tag_overlap > 0 or semantic_similarity >= 0.45:
                    label = 1

                rows.append(
                    {
                        "query_id": query_id,
                        "query": query_text,
                        "occasion": occasion,
                        "budget": round(budget, 2),
                        "product_id": str(candidate["product_id"]),
                        "product_name": candidate["name"],
                        "category": candidate["category"],
                        "color": candidate["color"],
                        "label": label,
                        "semantic_similarity": semantic_similarity,
                        "intent_match": intent_match,
                        "profile_affinity": profile_affinity,
                        "behavior_affinity": behavior_affinity,
                        "collaborative_affinity": collaborative_affinity,
                        "price_fit": price_fit,
                        "popularity_signal": popularity_signal,
                        "context_signal": context_signal,
                        "trust_signal": trust_signal,
                    }
                )
            query_id += 1

    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["query_id", "label"], ascending=[True, False]).reset_index(drop=True)
    return RankingDataset(frame=frame, feature_order=FEATURE_ORDER)


def split_by_query(frame: pd.DataFrame, train_ratio: float = 0.8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    query_ids = sorted(frame["query_id"].unique().tolist())
    cutoff = max(1, int(len(query_ids) * train_ratio))
    train_ids = set(query_ids[:cutoff])
    train = frame[frame["query_id"].isin(train_ids)].copy()
    test = frame[~frame["query_id"].isin(train_ids)].copy()
    return train, test


def dcg_at_k(relevances: Iterable[float], k: int) -> float:
    values = list(relevances)[:k]
    total = 0.0
    for idx, rel in enumerate(values, start=1):
        total += (2**rel - 1) / math.log2(idx + 1)
    return total


def ndcg_at_k(relevances: Sequence[float], k: int) -> float:
    values = list(relevances)
    ideal = sorted(values, reverse=True)
    denom = dcg_at_k(ideal, k)
    if denom == 0:
        return 0.0
    return dcg_at_k(values, k) / denom


def precision_at_k(relevances: Sequence[float], k: int, positive_threshold: float = 2.0) -> float:
    values = list(relevances)[:k]
    if not values:
        return 0.0
    positives = sum(1 for value in values if value >= positive_threshold)
    return positives / len(values)


def average_precision_at_k(relevances: Sequence[float], k: int, positive_threshold: float = 2.0) -> float:
    values = list(relevances)[:k]
    positive_count = 0
    precision_sum = 0.0
    for idx, value in enumerate(values, start=1):
        if value >= positive_threshold:
            positive_count += 1
            precision_sum += positive_count / idx
    if positive_count == 0:
        return 0.0
    return precision_sum / positive_count


def evaluate_grouped_predictions(frame: pd.DataFrame, predictions: Sequence[float], k: int = 6) -> Dict[str, float]:
    scored = frame.copy()
    scored["prediction"] = list(predictions)
    ndcgs: List[float] = []
    precisions: List[float] = []
    maps: List[float] = []

    for _, group in scored.groupby("query_id", sort=True):
        ordered = group.sort_values("prediction", ascending=False)
        labels = ordered["label"].astype(float).tolist()
        ndcgs.append(ndcg_at_k(labels, k))
        precisions.append(precision_at_k(labels, min(3, k)))
        maps.append(average_precision_at_k(labels, k))

    return {
        f"ndcg@{k}": sum(ndcgs) / max(len(ndcgs), 1),
        "precision@3": sum(precisions) / max(len(precisions), 1),
        f"map@{k}": sum(maps) / max(len(maps), 1),
    }


def model_payload(model: Any, metrics: Dict[str, float], dataset_rows: int, dataset_queries: int, source_catalog: str) -> Dict[str, Any]:
    return {
        "model": model,
        "feature_order": list(FEATURE_ORDER),
        "metrics": metrics,
        "dataset_rows": int(dataset_rows),
        "dataset_queries": int(dataset_queries),
        "source_catalog": source_catalog,
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "model_family": "xgboost_lambdamart",
    }
