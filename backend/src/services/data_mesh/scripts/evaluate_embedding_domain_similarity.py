#!/usr/bin/env python3
"""
Compare sentence-embedding vs TF-IDF as the w1 semantic channel on the domain admission harness.

Weights match production JSON (same paths as SilverToDomainLoaderService):
  - Embedding hybrid arm: data/evaluation/optimal_embedding_domain_weights.json → best_weights
  - TF-IDF hybrid arm:    data/evaluation/optimal_domain_weights.json → best_weights

Fallbacks use DEFAULT_EMBEDDING_ADMISSION_WEIGHTS / DEFAULT_ADMISSION_SCORE_WEIGHTS from the loader module.

Does not modify production scoring code or mutate weight JSON files.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
SERVICE_SRC = THIS_DIR.parent / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from silver_to_domain_loader import (  # noqa: E402
    DEFAULT_ADMISSION_SCORE_WEIGHTS,
    DEFAULT_EMBEDDING_ADMISSION_WEIGHTS,
    SilverToDomainLoaderService,
)


def _load_best_weights_from_json(
    path: Path,
    data_root: Path,
) -> tuple[dict[str, float] | None, str]:
    """Return raw best_weights dict (or None) and a human-readable source label."""
    if not path.is_file():
        return None, f"missing {path.name} → fallback"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"invalid JSON {path.name} ({exc}) → fallback"
    bw = data.get("best_weights")
    if isinstance(bw, dict) and bw:
        try:
            rel = path.relative_to(data_root)
            return bw, f"file {rel}"
        except ValueError:
            return bw, f"file {path}"
    return None, f"empty best_weights in {path.name} → fallback"


def _write_temp_csv(dataset_name: str, columns: list[str]) -> Path:
    tmp = Path(tempfile.gettempdir()) / f"dm_eval_{uuid.uuid4().hex[:10]}_{dataset_name}"
    df = pd.DataFrame([{c: "" for c in columns}])
    df.to_csv(tmp, index=False)
    return tmp


def _assignment_top1(rows_gold: list[dict[str, str]], eval_rows: list[dict[str, Any]]) -> float:
    hits = 0
    total = 0
    for g, row in zip(rows_gold, eval_rows):
        if str(g.get("expected_outcome") or "").strip().upper() != "EXISTING_DOMAIN":
            continue
        total += 1
        if str(row.get("best_domain") or "").strip() == str(g.get("expected_domain") or "").strip():
            hits += 1
    return float(hits / total) if total else 0.0


def _orphan_accuracy(rows_gold: list[dict[str, str]], eval_rows: list[dict[str, Any]]) -> float:
    hits = 0
    total = 0
    for g, row in zip(rows_gold, eval_rows):
        if str(g.get("expected_outcome") or "").strip().upper() != "ORPHAN_DOMAIN_CANDIDATE":
            continue
        total += 1
        if str(row.get("admission_decision") or "") == "NEW_DOMAIN_CANDIDATE":
            hits += 1
    return float(hits / total) if total else 0.0


def _review_routing_accuracy(rows_gold: list[dict[str, str]], eval_rows: list[dict[str, Any]]) -> float:
    hits = 0
    total = 0
    for g, row in zip(rows_gold, eval_rows):
        if str(g.get("expected_outcome") or "").strip().upper() != "REVIEW_REQUIRED":
            continue
        total += 1
        d = str(row.get("admission_decision") or "")
        if d in {"HUMAN_REVIEW_REQUIRED", "GOVERNANCE_TICKET_RECOMMENDED"}:
            hits += 1
    return float(hits / total) if total else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="Embedding vs TF-IDF domain admission validation.")
    ap.add_argument(
        "--data-root",
        type=Path,
        default=THIS_DIR.parent / "data",
        help="Data mesh data root (contains Contracts, Data_Mesh_Domains, Data, ...).",
    )
    ap.add_argument(
        "--validation-csv",
        type=Path,
        default=THIS_DIR.parent / "data" / "evaluation" / "domain_admission_validation.csv",
    )
    args = ap.parse_args()
    data_root = args.data_root.resolve()
    val_path = args.validation_csv.resolve()

    eval_dir = data_root / "evaluation"
    path_embedding_weights = eval_dir / "optimal_embedding_domain_weights.json"
    path_tfidf_weights = eval_dir / "optimal_domain_weights.json"

    svc: SilverToDomainLoaderService = SilverToDomainLoaderService(data_root=data_root)
    signatures = svc._domain_signatures()
    svc._merge_created_domain_signatures(signatures)
    domain_profile_texts = svc._build_domain_profile_texts(signatures)
    memory_entries = svc._read_memory_bank()
    run_id = "eval-emb"
    ts = datetime.now().isoformat(timespec="seconds")

    raw_emb, emb_src_label = _load_best_weights_from_json(path_embedding_weights, data_root)
    raw_tf, tf_src_label = _load_best_weights_from_json(path_tfidf_weights, data_root)
    emb_weights = svc._normalize_weight_dict(raw_emb, DEFAULT_EMBEDDING_ADMISSION_WEIGHTS)
    tfidf_weights = svc._normalize_weight_dict(raw_tf, DEFAULT_ADMISSION_SCORE_WEIGHTS)

    rows_val: list[dict[str, str]] = []
    with val_path.open(newline="", encoding="utf-8") as f:
        rows_val.extend(csv.DictReader(f))

    temp_paths: list[Path] = []
    rows_emb: list[dict[str, Any]] = []
    rows_tf: list[dict[str, Any]] = []
    rows_oc: list[dict[str, Any]] = []
    # Ontology+contract diagnostic: w1=w4=0; w2:w3 ratio from production embedding weights file (same as tuned hybrid).
    d2 = float(emb_weights["w2_ontology"])
    d3 = float(emb_weights["w3_contract"])
    oc_sum = d2 + d3
    oc_weights = (
        svc._normalize_weight_dict(
            {"w1_semantic": 0.0, "w2_ontology": d2, "w3_contract": d3, "w4_memory": 0.0},
            {"w1_semantic": 0.0, "w2_ontology": 0.5, "w3_contract": 0.5, "w4_memory": 0.0},
        )
        if oc_sum > 0
        else {"w1_semantic": 0.0, "w2_ontology": 0.5, "w3_contract": 0.5, "w4_memory": 0.0}
    )
    for r in rows_val:
        cols = [c.strip().lower() for c in str(r["columns_text"]).split() if c.strip()]
        name = str(r["dataset_name"]).strip()
        p = _write_temp_csv(name, cols)
        temp_paths.append(p)
        rows_emb.append(
            svc._evaluate_dataset(
                p,
                run_id,
                ts,
                signatures,
                domain_profile_texts,
                memory_entries,
                semantic_channel="embedding",
                admission_weights=emb_weights,
            )
        )
        rows_tf.append(
            svc._evaluate_dataset(
                p,
                run_id,
                ts,
                signatures,
                domain_profile_texts,
                memory_entries,
                semantic_channel="tfidf",
                admission_weights=tfidf_weights,
            )
        )
        rows_oc.append(
            svc._evaluate_dataset(
                p,
                run_id,
                ts,
                signatures,
                domain_profile_texts,
                memory_entries,
                semantic_channel="tfidf",
                admission_weights=oc_weights,
            )
        )

    def report_block(eval_rows: list[dict[str, Any]]) -> dict[str, float]:
        return {
            "assignment_accuracy": _assignment_top1(rows_val, eval_rows),
            "orphan_detection_accuracy": _orphan_accuracy(rows_val, eval_rows),
            "review_routing_accuracy": _review_routing_accuracy(rows_val, eval_rows),
        }

    m_emb = report_block(rows_emb)
    m_tf = report_block(rows_tf)
    m_oc = report_block(rows_oc)

    print("=== TF-IDF vs embedding vs ontology+contract hybrid (same validation CSV) ===")
    print("data_root:", data_root)
    print("validation_csv:", val_path)
    print("rows:", len(rows_val))
    print("service.semantic_backend:", svc.semantic_backend)
    print("service.scoring_backend_effective:", svc.scoring_backend_effective)
    if svc.semantic_scoring_warning:
        print("WARNING:", svc.semantic_scoring_warning)
    print()
    print("--- Weight sources (match production JSON paths under data/evaluation/) ---")
    print("embedding hybrid:", emb_src_label)
    print("  normalized weights:", emb_weights)
    print("tfidf hybrid:", tf_src_label)
    print("  normalized weights:", tfidf_weights)
    print("ontology+contract diagnostic (w1=w4=0; w2:w3 from embedding hybrid weights above)")
    print("  normalized weights:", oc_weights)
    print()
    print("metrics_full_hybrid_tfidf_w1:", m_tf)
    print("metrics_full_hybrid_embedding_w1:", m_emb)
    print("metrics_ontology_contract_hybrid_w1_w4_zero:", m_oc)
    print()
    print("Per-row best_domain (tfidf_w1 | embedding_w1 | ontology+contract | gold_domain | outcome):")
    for g, t_row, e_row, oc_row in zip(rows_val, rows_tf, rows_emb, rows_oc):
        print(
            f"  {g.get('dataset_name')}: tfidf={t_row.get('best_domain')} emb={e_row.get('best_domain')} "
            f"ont+con={oc_row.get('best_domain')} gold={g.get('expected_domain')} outcome={g.get('expected_outcome')}"
        )

    for tp in temp_paths:
        try:
            tp.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
