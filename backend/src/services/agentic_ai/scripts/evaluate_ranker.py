from __future__ import annotations
from typing import Iterable, List


def dcg_at_k(relevances: Iterable[float], k: int) -> float:
    values = list(relevances)[:k]
    total = 0.0
    for idx, rel in enumerate(values, start=1):
        total += (2 ** rel - 1) / __import__("math").log2(idx + 1)
    return total


def ndcg_at_k(relevances: List[float], k: int) -> float:
    ideal = sorted(relevances, reverse=True)
    denom = dcg_at_k(ideal, k)
    if denom == 0:
        return 0.0
    return dcg_at_k(relevances, k) / denom


def main() -> None:
    weighted_baseline = [3, 2, 2, 1, 0, 0]
    governed_ranker = [4, 3, 2, 1, 1, 0]
    print(f"Weighted baseline NDCG@6: {ndcg_at_k(weighted_baseline, 6):.4f}")
    print(f"Governed ranker NDCG@6: {ndcg_at_k(governed_ranker, 6):.4f}")


if __name__ == "__main__":
    main()
