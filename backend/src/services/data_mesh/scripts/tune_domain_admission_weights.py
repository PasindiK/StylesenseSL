#!/usr/bin/env python3
"""
Grid search over hybrid domain-admission weights (w1–w4).

Modes:
  --backend tfidf      Uses live TF-IDF profile similarity (production-aligned) + ontology, contract, memory.
                       Writes: data/evaluation/optimal_domain_weights.json (preserves existing scoring_backend if present).

  --backend embedding  Uses live sentence-embedding similarity when the model loads; otherwise TF-IDF as stand-in for w1.
                       Writes: data/evaluation/optimal_embedding_domain_weights.json

Does not start FastAPI. Requires pandas + project deps (same venv as the data mesh service).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_MESH_ROOT = SCRIPT_DIR.parent
SERVICE_SRC = DATA_MESH_ROOT / "src"
VALIDATION_CSV = DATA_MESH_ROOT / "data" / "evaluation" / "domain_admission_validation.csv"
OUTPUT_TFIDF_JSON = DATA_MESH_ROOT / "data" / "evaluation" / "optimal_domain_weights.json"
OUTPUT_EMBEDDING_JSON = DATA_MESH_ROOT / "data" / "evaluation" / "optimal_embedding_domain_weights.json"
OUTPUT_REPORT = DATA_MESH_ROOT / "data" / "evaluation" / "domain_weight_tuning_report.md"


@dataclass
class ValidationRow:
    dataset_name: str
    columns_text: str
    expected_outcome: str
    expected_domain: str


def load_validation_rows(path: Path) -> list[ValidationRow]:
    rows: list[ValidationRow] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(
                ValidationRow(
                    dataset_name=str(r["dataset_name"]).strip(),
                    columns_text=str(r["columns_text"]).strip(),
                    expected_outcome=str(r["expected_outcome"]).strip(),
                    expected_domain=str(r["expected_domain"]).strip(),
                )
            )
    return rows


def tokenize_columns_text(text: str) -> set[str]:
    raw = str(text or "").lower().replace(",", " ").split()
    return {t.strip() for t in raw if t.strip()}


def predict_outcome(best_score: float, ambiguity_gap: float) -> str:
    if best_score >= 0.70 and ambiguity_gap >= 0.10:
        return "EXISTING_DOMAIN"
    if best_score < 0.40:
        return "ORPHAN_DOMAIN_CANDIDATE"
    return "REVIEW_REQUIRED"


def weight_grid(step: float) -> list[tuple[float, float, float, float]]:
    if step <= 0 or step > 1:
        raise ValueError("step must be in (0, 1].")
    n = int(round(1.0 / step))
    if abs(n * step - 1.0) > 1e-6:
        raise ValueError("step must divide 1.0 evenly (e.g. 0.05 or 0.10).")
    combos: set[tuple[float, float, float, float]] = set()
    for k1 in range(n + 1):
        for k2 in range(n + 1 - k1):
            for k3 in range(n + 1 - k1 - k2):
                k4 = n - k1 - k2 - k3
                if k4 < 0:
                    continue
                w1, w2, w3, w4 = k1 * step, k2 * step, k3 * step, k4 * step
                combos.add((round(w1, 6), round(w2, 6), round(w3, 6), round(w4, 6)))
    return sorted(combos, key=lambda x: (-x[0], -x[1], -x[2], -x[3]))


def evaluate_weights(
    w: tuple[float, float, float, float],
    rows: list[ValidationRow],
    sem_m: list[list[float]],
    ont_m: list[list[float]],
    con_m: list[list[float]],
    mem_m: list[list[float]],
    domain_labels: list[str],
) -> dict[str, Any]:
    n = len(rows)
    d = len(domain_labels)
    row_scores: list[list[float]] = []
    for i in range(n):
        row_scores.append(
            [
                min(
                    1.0,
                    max(
                        0.0,
                        w[0] * sem_m[i][j] + w[1] * ont_m[i][j] + w[2] * con_m[i][j] + w[3] * mem_m[i][j],
                    ),
                )
                for j in range(d)
            ]
        )

    pred_domains: list[str] = []
    pred_outcome: list[str] = []
    for i in range(n):
        rs = row_scores[i]
        j_best = max(range(d), key=lambda j: rs[j])
        best = float(rs[j_best])
        second = float(max((rs[j] for j in range(d) if j != j_best), default=0.0))
        gap = max(0.0, best - second)
        pred_domains.append(domain_labels[j_best])
        pred_outcome.append(predict_outcome(best, gap))

    existing_mask = [r.expected_outcome == "EXISTING_DOMAIN" for r in rows]
    orphan_mask = [r.expected_outcome == "ORPHAN_DOMAIN_CANDIDATE" for r in rows]
    review_mask = [r.expected_outcome == "REVIEW_REQUIRED" for r in rows]

    def safe_rate(num: int, den: int) -> float:
        return float(num / den) if den else 1.0

    gold_existing = sum(1 for x in existing_mask if x)
    da_hits = 0
    for i in range(n):
        if not existing_mask[i]:
            continue
        exp_dom = rows[i].expected_domain
        if pred_outcome[i] == "EXISTING_DOMAIN" and pred_domains[i] == exp_dom:
            da_hits += 1
    domain_assignment_accuracy = safe_rate(da_hits, gold_existing)

    orphan_hits = sum(
        1 for i in range(n) if orphan_mask[i] and pred_outcome[i] == "ORPHAN_DOMAIN_CANDIDATE"
    )
    orphan_detection_accuracy = safe_rate(orphan_hits, sum(1 for x in orphan_mask if x))

    review_hits = sum(1 for i in range(n) if review_mask[i] and pred_outcome[i] == "REVIEW_REQUIRED")
    review_routing_accuracy = safe_rate(review_hits, sum(1 for x in review_mask if x))

    wrong_auto = 0
    for i in range(n):
        if pred_outcome[i] != "EXISTING_DOMAIN":
            continue
        exp = rows[i].expected_outcome
        ok = exp == "EXISTING_DOMAIN" and pred_domains[i] == rows[i].expected_domain
        if not ok:
            wrong_auto += 1
    wrong_auto_assignment_rate = safe_rate(wrong_auto, n)

    objective = (
        0.50 * domain_assignment_accuracy
        + 0.25 * orphan_detection_accuracy
        + 0.15 * review_routing_accuracy
        - 0.10 * wrong_auto_assignment_rate
    )

    return {
        "weights": {"w1_semantic": w[0], "w2_ontology": w[1], "w3_contract": w[2], "w4_memory": w[3]},
        "domain_assignment_accuracy": domain_assignment_accuracy,
        "orphan_detection_accuracy": orphan_detection_accuracy,
        "review_routing_accuracy": review_routing_accuracy,
        "wrong_auto_assignment_rate": wrong_auto_assignment_rate,
        "overall_objective_score": objective,
        "counts": {
            "rows": n,
            "gold_existing": gold_existing,
            "gold_orphan": sum(1 for x in orphan_mask if x),
            "gold_review": sum(1 for x in review_mask if x),
        },
    }


def live_precompute_matrices(
    data_root: Path,
    backend: str,
) -> tuple[list[list[float]], list[list[float]], list[list[float]], list[list[float]], list[str], list[ValidationRow], str, str | None]:
    """Build row×domain score matrices using SilverToDomainLoaderService (production-aligned components)."""
    if str(SERVICE_SRC) not in sys.path:
        sys.path.insert(0, str(SERVICE_SRC))

    import pandas as pd

    from silver_to_domain_loader import SilverToDomainLoaderService

    svc = SilverToDomainLoaderService(data_root=data_root)
    signatures = svc._domain_signatures()
    svc._merge_created_domain_signatures(signatures)
    domain_profile_texts = svc._build_domain_profile_texts(signatures)
    memory_entries = svc._read_memory_bank()
    domains = sorted(domain_profile_texts.keys())
    rows = load_validation_rows(VALIDATION_CSV)

    sem_m: list[list[float]] = []
    ont_m: list[list[float]] = []
    con_m: list[list[float]] = []
    mem_m: list[list[float]] = []
    tmp_paths: list[Path] = []

    use_embedding = backend.strip().lower() == "embedding"
    st_available = svc._sentence_transformer_model is not None

    try:
        for row in rows:
            col_list = [c.strip().lower() for c in str(row.columns_text).split() if c.strip()]
            if not col_list:
                col_list = ["_placeholder"]
            tmp = Path(tempfile.gettempdir()) / f"tune_dm_{uuid.uuid4().hex[:10]}.csv"
            tmp_paths.append(tmp)
            pd.DataFrame([{c: "" for c in col_list}]).to_csv(tmp, index=False)

            df = pd.read_csv(tmp)
            columns_detected = [str(c).strip().lower() for c in df.columns]
            dataset_profile_text = svc._build_dataset_profile_text(row.dataset_name, df, columns_detected)
            column_stems = svc._expand_column_token_stems(set(columns_detected))
            dataset_business_sentence = svc._build_dataset_business_sentence(
                row.dataset_name, df, columns_detected, column_stems
            )
            domain_business_sentences = {
                dom: svc._build_domain_business_sentence(dom, signatures, memory_entries) for dom in domains
            }

            if use_embedding and st_available:
                sem_dict = svc._embedding_similarities(
                    dataset_business_sentence,
                    domain_business_sentences,
                    svc._sentence_transformer_model,
                )
            else:
                sem_dict = svc._semantic_similarities(dataset_profile_text, domain_profile_texts)

            ranked = svc._rank_domain_contract_parts(tmp, columns_detected, signatures)
            con_by_domain = {p.domain: float(p.contract_coverage_score) for p in ranked}
            mem_by_domain = svc._memory_feedback_scores(dataset_profile_text, memory_entries, domains)

            sr, orow, cr, mr = [], [], [], []
            for dom in domains:
                sr.append(float(sem_dict.get(dom, 0.0)))
                orow.append(float(svc._ontology_concept_match_score(dom, column_stems)))
                cr.append(float(con_by_domain.get(dom, 0.0)))
                mr.append(float(mem_by_domain.get(dom, 0.5)))
            sem_m.append(sr)
            ont_m.append(orow)
            con_m.append(cr)
            mem_m.append(mr)
    finally:
        for p in tmp_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    warn = None
    if use_embedding and not st_available:
        warn = "sentence-transformers did not load; w1 used TF-IDF profile similarity as stand-in for embedding tuning."

    return sem_m, ont_m, con_m, mem_m, domains, rows, svc.semantic_backend, warn


def main() -> int:
    ap = argparse.ArgumentParser(description="Tune domain admission hybrid weights.")
    ap.add_argument(
        "--backend",
        choices=("tfidf", "embedding"),
        required=True,
        help="tfidf: live TF-IDF w1; embedding: MiniLM embedding w1 when available.",
    )
    ap.add_argument(
        "--step",
        type=float,
        default=0.05,
        help="Grid step on the weight simplex (e.g. 0.05 or 0.025).",
    )
    ap.add_argument(
        "--data-root",
        type=Path,
        default=DATA_MESH_ROOT / "data",
        help="Data mesh data root (contains Contracts, Data_Mesh_Domains, ...).",
    )
    args = ap.parse_args()
    step = float(args.step)
    data_root = Path(args.data_root).resolve()

    if step not in (0.025, 0.05, 0.1, 0.10) and step > 0:
        print("Note: typical steps are 0.025 (fine), 0.05, or 0.10; proceeding with", step)
    if not VALIDATION_CSV.is_file():
        print("Missing validation CSV:", VALIDATION_CSV, file=sys.stderr)
        return 1

    sem_m, ont_m, con_m, mem_m, domain_labels, rows, svc_semantic_backend, emb_warn = live_precompute_matrices(
        data_root, args.backend
    )
    combos = weight_grid(step)

    results: list[dict[str, Any]] = []
    for w in combos:
        results.append(evaluate_weights(w, rows, sem_m, ont_m, con_m, mem_m, domain_labels))

    results.sort(key=lambda r: r["overall_objective_score"], reverse=True)
    best = results[0]
    tested = len(combos)
    tied_at_best = sum(1 for r in results if r["overall_objective_score"] >= best["overall_objective_score"] - 1e-9)

    backend_label = str(args.backend).lower()
    out_path = OUTPUT_TFIDF_JSON if backend_label == "tfidf" else OUTPUT_EMBEDDING_JSON

    generated = __import__("datetime").datetime.now().isoformat(timespec="seconds")

    if backend_label == "tfidf":
        existing: dict[str, Any] = {}
        if OUTPUT_TFIDF_JSON.is_file():
            try:
                existing = json.loads(OUTPUT_TFIDF_JSON.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        scoring_router = existing.get("scoring_backend")
        if scoring_router not in ("sentence_embedding", "tfidf"):
            scoring_router = "sentence_embedding"
        out_payload: dict[str, Any] = {
            "scoring_backend": scoring_router,
            "best_weights": best["weights"],
            "metrics": {k: best[k] for k in best if k not in ("weights",)},
            "tested_combinations_count": tested,
            "grid_step": step,
            "tuning_backend": "tfidf",
            "fine_tune_summary": (
                f"Live TF-IDF w1 grid at step {step}: {tested} tuples; "
                f"{tied_at_best} tie(s) at objective {best['overall_objective_score']:.6f}. "
                f"Domains in matrix: {len(domain_labels)}."
            ),
            "explanation": (
                "best_weights tuned with live SilverToDomainLoaderService TF-IDF profile similarity (w1), "
                "ontology concept match, contract fit, reviewer memory. "
                "Embedding-specific weights live in optimal_embedding_domain_weights.json."
            ),
            "generated_at": generated,
        }
        # Preserve optional legacy keys users may rely on
        for k in ("prototype_weights", "prototype_metrics"):
            if k in existing:
                out_payload[k] = existing[k]
    else:
        out_payload = {
            "scoring_backend": "sentence_embedding",
            "best_weights": best["weights"],
            "metrics": {k: best[k] for k in best if k not in ("weights",)},
            "tested_combinations_count": tested,
            "grid_step": step,
            "tuning_backend": "embedding",
            "fine_tune_summary": (
                f"Live embedding w1 grid at step {step}: {tested} tuples; "
                f"{tied_at_best} tie(s) at objective {best['overall_objective_score']:.6f}. "
                f"Domains in matrix: {len(domain_labels)}."
            ),
            "explanation": (
                "best_weights tuned with live sentence-transformers embedding similarity (w1) when the model loads; "
                "otherwise TF-IDF was used as w1 stand-in for this run. "
                "TF-IDF routing weights remain in optimal_domain_weights.json."
            ),
            "semantic_backend_at_tune": svc_semantic_backend,
            "embedding_tune_warning": emb_warn,
            "generated_at": generated,
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    print("=== Domain admission weight tuning (live loader components) ===\n")
    print(f"backend: {args.backend} | validation rows: {len(rows)} | domains: {len(domain_labels)}")
    print(f"service.semantic_backend (at init): {svc_semantic_backend}")
    if emb_warn:
        print("WARNING:", emb_warn)
    print(f"Grid step: {step} | Combinations tested: {tested}\n")
    print("--- Top 5 weight tuples ---")
    for i, r in enumerate(results[:5], 1):
        w = r["weights"]
        print(
            f"{i}. objective={r['overall_objective_score']:.4f}  "
            f"w=({w['w1_semantic']:.2f},{w['w2_ontology']:.2f},{w['w3_contract']:.2f},{w['w4_memory']:.2f})  "
            f"da={r['domain_assignment_accuracy']:.3f} orphan={r['orphan_detection_accuracy']:.3f} "
            f"review={r['review_routing_accuracy']:.3f} wrong_auto={r['wrong_auto_assignment_rate']:.3f}"
        )
    bw = best["weights"]
    print("\n--- Best weights ---")
    print(
        f"objective={best['overall_objective_score']:.4f}  "
        f"w1={bw['w1_semantic']:.2f} w2={bw['w2_ontology']:.2f} w3={bw['w3_contract']:.2f} w4={bw['w4_memory']:.2f}"
    )
    print(f"\nWrote: {out_path}")

    report_lines = [
        f"# Domain admission tuning ({args.backend})",
        "",
        f"- Output: `{out_path.relative_to(DATA_MESH_ROOT)}`",
        f"- Grid step: **{step}**",
        f"- Best objective: **{best['overall_objective_score']:.4f}**",
        f"- semantic_backend at service init: **{svc_semantic_backend}**",
    ]
    if emb_warn:
        report_lines.append(f"- Warning: {emb_warn}")
    report_lines.append("")
    OUTPUT_REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote: {OUTPUT_REPORT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
