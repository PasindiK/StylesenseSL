#!/usr/bin/env python3
"""
Calibrate domain admission *policy thresholds* (auto / orphan / ambiguity margin)
using labeled validation data. Does not modify production code.

Reuses live score matrices from SilverToDomainLoaderService (same as tune_domain_admission_weights).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_MESH_ROOT = SCRIPT_DIR.parent
SERVICE_SRC = DATA_MESH_ROOT / "src"
VALIDATION_CSV = DATA_MESH_ROOT / "data" / "evaluation" / "domain_admission_validation.csv"
OUTPUT_JSON = DATA_MESH_ROOT / "data" / "evaluation" / "optimal_domain_thresholds.json"
REPORT_MD = DATA_MESH_ROOT / "data" / "evaluation" / "domain_threshold_calibration_report.md"
EMB_WEIGHTS = DATA_MESH_ROOT / "data" / "evaluation" / "optimal_embedding_domain_weights.json"
TFIDF_WEIGHTS = DATA_MESH_ROOT / "data" / "evaluation" / "optimal_domain_weights.json"

# Matches tune_domain_admission_weights.predict_outcome reference (not full production policy).
CURRENT_BASELINE = {"auto_threshold": 0.70, "orphan_threshold": 0.40, "ambiguity_margin": 0.10}

OBJ_W_DA = 0.38
OBJ_W_ORPHAN = 0.20
OBJ_W_REVIEW_ROUTE = 0.18
OBJ_W_STRICT = 0.14
OBJ_PENALTY_WRONG_AUTO = 0.42
OBJ_PENALTY_REVIEW_LOAD = 0.12


def _frange(lo: float, hi: float, step: float) -> list[float]:
    out: list[float] = []
    x = lo
    while x <= hi + 1e-9:
        out.append(round(x, 4))
        x = round(x + step, 4)
    return out


def load_blend_weights(backend: str) -> dict[str, float]:
    path = TFIDF_WEIGHTS if backend.strip().lower() == "tfidf" else EMB_WEIGHTS
    fallback = {"w1_semantic": 0.40, "w2_ontology": 0.30, "w3_contract": 0.25, "w4_memory": 0.05}
    if not path.is_file():
        return dict(fallback)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        bw = payload.get("best_weights")
        if not isinstance(bw, dict):
            return dict(fallback)
        w1 = float(bw.get("w1_semantic", fallback["w1_semantic"]))
        w2 = float(bw.get("w2_ontology", fallback["w2_ontology"]))
        w3 = float(bw.get("w3_contract", fallback["w3_contract"]))
        w4 = float(bw.get("w4_memory", fallback["w4_memory"]))
        s = w1 + w2 + w3 + w4
        if s <= 0:
            return dict(fallback)
        return {
            "w1_semantic": w1 / s,
            "w2_ontology": w2 / s,
            "w3_contract": w3 / s,
            "w4_memory": w4 / s,
        }
    except Exception:
        return dict(fallback)


def predict_outcome(
    best_score: float,
    ambiguity_gap: float,
    *,
    auto_threshold: float,
    orphan_threshold: float,
    ambiguity_margin: float,
) -> str:
    if best_score >= auto_threshold and ambiguity_gap >= ambiguity_margin:
        return "EXISTING_DOMAIN"
    if best_score < orphan_threshold:
        return "ORPHAN_DOMAIN_CANDIDATE"
    return "REVIEW_REQUIRED"


@dataclass
class ThresholdEval:
    auto_threshold: float
    orphan_threshold: float
    ambiguity_margin: float
    domain_assignment_accuracy: float
    wrong_auto_assignment_rate: float
    review_routing_accuracy: float
    orphan_detection_accuracy: float
    review_workload_fraction: float
    strict_outcome_accuracy: float
    objective_score: float
    counts: dict[str, int]


def evaluate_thresholds(
    auto_t: float,
    orphan_t: float,
    margin_m: float,
    rows: list[Any],
    sem_m: list[list[float]],
    ont_m: list[list[float]],
    con_m: list[list[float]],
    mem_m: list[list[float]],
    domain_labels: list[str],
    w: dict[str, float],
) -> ThresholdEval:
    n = len(rows)
    d = len(domain_labels)
    w1, w2, w3, w4 = w["w1_semantic"], w["w2_ontology"], w["w3_contract"], w["w4_memory"]

    pred_domains: list[str] = []
    pred_outcome: list[str] = []
    for i in range(n):
        rs = [
            min(
                1.0,
                max(
                    0.0,
                    w1 * sem_m[i][j] + w2 * ont_m[i][j] + w3 * con_m[i][j] + w4 * mem_m[i][j],
                ),
            )
            for j in range(d)
        ]
        j_best = max(range(d), key=lambda j: rs[j])
        best = float(rs[j_best])
        second = float(max((rs[j] for j in range(d) if j != j_best), default=0.0))
        gap = max(0.0, best - second)
        pred_domains.append(domain_labels[j_best])
        pred_outcome.append(
            predict_outcome(
                best,
                gap,
                auto_threshold=auto_t,
                orphan_threshold=orphan_t,
                ambiguity_margin=margin_m,
            )
        )

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
        if pred_outcome[i] == "EXISTING_DOMAIN" and pred_domains[i] == rows[i].expected_domain:
            da_hits += 1
    domain_assignment_accuracy = safe_rate(da_hits, gold_existing)

    orphan_hits = sum(1 for i in range(n) if orphan_mask[i] and pred_outcome[i] == "ORPHAN_DOMAIN_CANDIDATE")
    orphan_detection_accuracy = safe_rate(orphan_hits, sum(1 for x in orphan_mask if x))

    review_hits = sum(1 for i in range(n) if review_mask[i] and pred_outcome[i] == "REVIEW_REQUIRED")
    review_routing_accuracy = safe_rate(review_hits, sum(1 for x in review_mask if x))

    wrong_auto = 0
    for i in range(n):
        if pred_outcome[i] != "EXISTING_DOMAIN":
            continue
        ok = rows[i].expected_outcome == "EXISTING_DOMAIN" and pred_domains[i] == rows[i].expected_domain
        if not ok:
            wrong_auto += 1
    wrong_auto_assignment_rate = safe_rate(wrong_auto, n)

    review_predicted = sum(1 for p in pred_outcome if p == "REVIEW_REQUIRED")
    review_workload_fraction = safe_rate(review_predicted, n)

    strict_hits = sum(1 for i in range(n) if pred_outcome[i] == rows[i].expected_outcome)
    strict_outcome_accuracy = safe_rate(strict_hits, n)

    objective = (
        OBJ_W_DA * domain_assignment_accuracy
        + OBJ_W_ORPHAN * orphan_detection_accuracy
        + OBJ_W_REVIEW_ROUTE * review_routing_accuracy
        + OBJ_W_STRICT * strict_outcome_accuracy
        - OBJ_PENALTY_WRONG_AUTO * wrong_auto_assignment_rate
        - OBJ_PENALTY_REVIEW_LOAD * review_workload_fraction
    )

    return ThresholdEval(
        auto_threshold=auto_t,
        orphan_threshold=orphan_t,
        ambiguity_margin=margin_m,
        domain_assignment_accuracy=domain_assignment_accuracy,
        wrong_auto_assignment_rate=wrong_auto_assignment_rate,
        review_routing_accuracy=review_routing_accuracy,
        orphan_detection_accuracy=orphan_detection_accuracy,
        review_workload_fraction=review_workload_fraction,
        strict_outcome_accuracy=strict_outcome_accuracy,
        objective_score=objective,
        counts={
            "rows": n,
            "gold_existing": gold_existing,
            "gold_orphan": sum(1 for x in orphan_mask if x),
            "gold_review": sum(1 for x in review_mask if x),
            "predicted_review": review_predicted,
            "wrong_auto_events": wrong_auto,
        },
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate domain admission policy thresholds on labeled validation CSV.")
    ap.add_argument("--backend", choices=("tfidf", "embedding"), default="embedding")
    ap.add_argument("--data-root", type=Path, default=DATA_MESH_ROOT / "data")
    args = ap.parse_args()
    data_root = Path(args.data_root).resolve()

    if str(SERVICE_SRC) not in sys.path:
        sys.path.insert(0, str(SERVICE_SRC))

    from tune_domain_admission_weights import live_precompute_matrices, load_validation_rows

    if not VALIDATION_CSV.is_file():
        print("Missing validation CSV:", VALIDATION_CSV, file=sys.stderr)
        return 1

    rows = load_validation_rows(VALIDATION_CSV)
    blend = load_blend_weights(args.backend)
    sem_m, ont_m, con_m, mem_m, domain_labels, _, svc_semantic_backend, emb_warn = live_precompute_matrices(
        data_root, args.backend
    )

    auto_grid = _frange(0.60, 0.85, 0.05)
    orphan_grid = _frange(0.25, 0.50, 0.05)
    margin_grid = _frange(0.05, 0.20, 0.05)

    results: list[ThresholdEval] = []
    skipped = 0
    for auto_t in auto_grid:
        for orphan_t in orphan_grid:
            for margin_m in margin_grid:
                if orphan_t >= auto_t - 0.02:
                    skipped += 1
                    continue
                results.append(
                    evaluate_thresholds(
                        auto_t,
                        orphan_t,
                        margin_m,
                        rows,
                        sem_m,
                        ont_m,
                        con_m,
                        mem_m,
                        domain_labels,
                        blend,
                    )
                )

    results.sort(key=lambda r: r.objective_score, reverse=True)
    best = results[0]

    baseline = evaluate_thresholds(
        CURRENT_BASELINE["auto_threshold"],
        CURRENT_BASELINE["orphan_threshold"],
        CURRENT_BASELINE["ambiguity_margin"],
        rows,
        sem_m,
        ont_m,
        con_m,
        mem_m,
        domain_labels,
        blend,
    )

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    blend_src = EMB_WEIGHTS if args.backend == "embedding" else TFIDF_WEIGHTS
    try:
        blend_rel = str(blend_src.relative_to(DATA_MESH_ROOT))
    except ValueError:
        blend_rel = str(blend_src)

    json_payload: dict[str, Any] = {
        "auto_threshold": best.auto_threshold,
        "orphan_threshold": best.orphan_threshold,
        "ambiguity_margin": best.ambiguity_margin,
        "objective_score": round(best.objective_score, 6),
        "objective_weights": {
            "w_domain_assignment": OBJ_W_DA,
            "w_orphan_detection": OBJ_W_ORPHAN,
            "w_review_routing": OBJ_W_REVIEW_ROUTE,
            "w_strict_outcome": OBJ_W_STRICT,
            "penalty_wrong_auto": OBJ_PENALTY_WRONG_AUTO,
            "penalty_review_workload": OBJ_PENALTY_REVIEW_LOAD,
        },
        "metrics": {
            "domain_assignment_accuracy": round(best.domain_assignment_accuracy, 6),
            "wrong_auto_assignment_rate": round(best.wrong_auto_assignment_rate, 6),
            "review_routing_accuracy": round(best.review_routing_accuracy, 6),
            "orphan_detection_accuracy": round(best.orphan_detection_accuracy, 6),
            "review_workload_fraction": round(best.review_workload_fraction, 6),
            "strict_outcome_accuracy": round(best.strict_outcome_accuracy, 6),
        },
        "counts": best.counts,
        "blend_weights_used": {k: round(float(v), 6) for k, v in blend.items()},
        "blend_weights_source": blend_rel,
        "calibration_backend": args.backend,
        "semantic_backend_at_calibration": svc_semantic_backend,
        "embedding_calibration_warning": emb_warn,
        "validation_csv": str(VALIDATION_CSV.relative_to(DATA_MESH_ROOT)),
        "sweep": {
            "auto_threshold": auto_grid,
            "orphan_threshold": orphan_grid,
            "ambiguity_margin": margin_grid,
            "valid_combinations_tested": len(results),
            "skipped_invalid_combinations": skipped,
        },
        "baseline_reference_thresholds": CURRENT_BASELINE,
        "baseline_metrics": {
            "domain_assignment_accuracy": round(baseline.domain_assignment_accuracy, 6),
            "wrong_auto_assignment_rate": round(baseline.wrong_auto_assignment_rate, 6),
            "review_routing_accuracy": round(baseline.review_routing_accuracy, 6),
            "orphan_detection_accuracy": round(baseline.orphan_detection_accuracy, 6),
            "review_workload_fraction": round(baseline.review_workload_fraction, 6),
            "strict_outcome_accuracy": round(baseline.strict_outcome_accuracy, 6),
            "objective_score": round(baseline.objective_score, 6),
        },
        "explanation": (
            "Thresholds calibrate a 3-way decision on hybrid best score and leader gap: "
            "auto (EXISTING_DOMAIN) if score>=auto_threshold and gap>=ambiguity_margin; "
            "orphan if score<orphan_threshold; else REVIEW_REQUIRED. "
            "Production _resolve_admission_policy is unchanged; adopt these values only when explicitly wired in."
        ),
        "generated_at": generated,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    def fmt_m(ev: ThresholdEval) -> str:
        return (
            f"| domain_assign | {ev.domain_assignment_accuracy:.4f} |\n"
            f"| wrong_auto_rate | {ev.wrong_auto_assignment_rate:.4f} |\n"
            f"| review_route | {ev.review_routing_accuracy:.4f} |\n"
            f"| orphan_detect | {ev.orphan_detection_accuracy:.4f} |\n"
            f"| review_workload | {ev.review_workload_fraction:.4f} |\n"
            f"| strict_outcome | {ev.strict_outcome_accuracy:.4f} |\n"
            f"| objective | {ev.objective_score:.4f} |"
        )

    report = f"""# Domain admission threshold calibration

Generated: **{generated}** (UTC)

## Scope

- Validation: `{VALIDATION_CSV.relative_to(DATA_MESH_ROOT)}`
- Semantic backend at run: **{svc_semantic_backend}** (`--backend {args.backend}`)
- Blend weights: `{blend_rel}` (normalized `best_weights`)
- Sweep: `auto_threshold` {auto_grid}, `orphan_threshold` {orphan_grid}, `ambiguity_margin` {margin_grid}
- Valid combinations tested: **{len(results)}** (skipped {skipped} where `orphan_threshold >= auto_threshold - 0.02`)

## Decision rule (calibration harness)

Aligns with the weight-tuning harness (not full production `_resolve_admission_policy`):

1. If `best_hybrid_score >= auto_threshold` **and** `leader_gap >= ambiguity_margin` → **EXISTING_DOMAIN**
2. Else if `best_hybrid_score < orphan_threshold` → **ORPHAN_DOMAIN_CANDIDATE**
3. Else → **REVIEW_REQUIRED**

## Objective (for ranking sweeps only)

```
objective = {OBJ_W_DA}*domain_assignment_accuracy
          + {OBJ_W_ORPHAN}*orphan_detection_accuracy
          + {OBJ_W_REVIEW_ROUTE}*review_routing_accuracy
          + {OBJ_W_STRICT}*strict_outcome_accuracy
          - {OBJ_PENALTY_WRONG_AUTO}*wrong_auto_assignment_rate
          - {OBJ_PENALTY_REVIEW_LOAD}*review_workload_fraction
```

## Best thresholds (`optimal_domain_thresholds.json`)

| Parameter | Value |
|-----------|-------|
| auto_threshold | **{best.auto_threshold}** |
| orphan_threshold | **{best.orphan_threshold}** |
| ambiguity_margin | **{best.ambiguity_margin}** |

### Metrics (best)

{fmt_m(best)}

## Baseline (tuning reference: 0.70 / 0.40 / 0.10)

### Metrics (baseline)

{fmt_m(baseline)}

## Comparison

| Metric | Baseline | Best | Delta |
|--------|----------|------|-------|
| domain_assignment_accuracy | {baseline.domain_assignment_accuracy:.4f} | {best.domain_assignment_accuracy:.4f} | {best.domain_assignment_accuracy - baseline.domain_assignment_accuracy:+.4f} |
| wrong_auto_assignment_rate | {baseline.wrong_auto_assignment_rate:.4f} | {best.wrong_auto_assignment_rate:.4f} | {best.wrong_auto_assignment_rate - baseline.wrong_auto_assignment_rate:+.4f} |
| review_routing_accuracy | {baseline.review_routing_accuracy:.4f} | {best.review_routing_accuracy:.4f} | {best.review_routing_accuracy - baseline.review_routing_accuracy:+.4f} |
| orphan_detection_accuracy | {baseline.orphan_detection_accuracy:.4f} | {best.orphan_detection_accuracy:.4f} | {best.orphan_detection_accuracy - baseline.orphan_detection_accuracy:+.4f} |
| review_workload_fraction | {baseline.review_workload_fraction:.4f} | {best.review_workload_fraction:.4f} | {best.review_workload_fraction - baseline.review_workload_fraction:+.4f} |
| strict_outcome_accuracy | {baseline.strict_outcome_accuracy:.4f} | {best.strict_outcome_accuracy:.4f} | {best.strict_outcome_accuracy - baseline.strict_outcome_accuracy:+.4f} |
| objective_score | {baseline.objective_score:.4f} | {best.objective_score:.4f} | {best.objective_score - baseline.objective_score:+.4f} |

## Top 5 threshold tuples (by objective)

"""
    for i, r in enumerate(results[:5], 1):
        report += (
            f"{i}. objective={r.objective_score:.4f}  auto={r.auto_threshold} orphan={r.orphan_threshold} "
            f"margin={r.ambiguity_margin}  da={r.domain_assignment_accuracy:.3f} wrong_auto={r.wrong_auto_assignment_rate:.3f} "
            f"review_rt={r.review_routing_accuracy:.3f} orphan={r.orphan_detection_accuracy:.3f} "
            f"review_load={r.review_workload_fraction:.3f}\n"
        )

    if emb_warn:
        report += f"\n## Warning\n\n{emb_warn}\n"

    report += (
        f"\n## Outputs\n\n- `{OUTPUT_JSON.relative_to(DATA_MESH_ROOT)}`\n"
        f"- `{REPORT_MD.relative_to(DATA_MESH_ROOT)}`\n"
    )

    REPORT_MD.write_text(report, encoding="utf-8")

    print("=== Domain admission threshold calibration ===\n")
    print(f"backend: {args.backend} | rows: {len(rows)} | domains: {len(domain_labels)}")
    print(f"semantic_backend: {svc_semantic_backend}")
    if emb_warn:
        print("WARNING:", emb_warn)
    print(f"Combinations tested: {len(results)} (skipped invalid: {skipped})\n")
    print(
        f"BEST  auto={best.auto_threshold} orphan={best.orphan_threshold} margin={best.ambiguity_margin}  "
        f"objective={best.objective_score:.4f}"
    )
    print(
        f"  da={best.domain_assignment_accuracy:.3f} wrong_auto={best.wrong_auto_assignment_rate:.3f} "
        f"review_rt={best.review_routing_accuracy:.3f} orphan_det={best.orphan_detection_accuracy:.3f} "
        f"review_load={best.review_workload_fraction:.3f} strict={best.strict_outcome_accuracy:.3f}"
    )
    print(f"\nBaseline (0.70/0.40/0.10) objective={baseline.objective_score:.4f}")
    print(f"\nWrote: {OUTPUT_JSON}")
    print(f"Wrote: {REPORT_MD}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
