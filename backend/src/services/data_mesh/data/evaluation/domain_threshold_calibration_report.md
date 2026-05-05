# Domain admission threshold calibration

Generated: **2026-05-05T01:13:34+00:00** (UTC)

## Scope

- Validation: `data/evaluation/domain_admission_validation.csv`
- Semantic backend at run: **sentence_embedding** (`--backend embedding`)
- Blend weights: `data/evaluation/optimal_embedding_domain_weights.json` (normalized `best_weights`)
- Sweep: `auto_threshold` [0.6, 0.65, 0.7, 0.75, 0.8, 0.85], `orphan_threshold` [0.25, 0.3, 0.35, 0.4, 0.45, 0.5], `ambiguity_margin` [0.05, 0.1, 0.15, 0.2]
- Valid combinations tested: **144** (skipped 0 where `orphan_threshold >= auto_threshold - 0.02`)

## Decision rule (calibration harness)

Aligns with the weight-tuning harness (not full production `_resolve_admission_policy`):

1. If `best_hybrid_score >= auto_threshold` **and** `leader_gap >= ambiguity_margin` → **EXISTING_DOMAIN**
2. Else if `best_hybrid_score < orphan_threshold` → **ORPHAN_DOMAIN_CANDIDATE**
3. Else → **REVIEW_REQUIRED**

## Objective (for ranking sweeps only)

```
objective = 0.38*domain_assignment_accuracy
          + 0.2*orphan_detection_accuracy
          + 0.18*review_routing_accuracy
          + 0.14*strict_outcome_accuracy
          - 0.42*wrong_auto_assignment_rate
          - 0.12*review_workload_fraction
```

## Best thresholds (`optimal_domain_thresholds.json`)

| Parameter | Value |
|-----------|-------|
| auto_threshold | **0.6** |
| orphan_threshold | **0.4** |
| ambiguity_margin | **0.1** |

### Metrics (best)

| domain_assign | 1.0000 |
| wrong_auto_rate | 0.0000 |
| review_route | 1.0000 |
| orphan_detect | 1.0000 |
| review_workload | 0.1818 |
| strict_outcome | 1.0000 |
| objective | 0.8782 |

## Baseline (tuning reference: 0.70 / 0.40 / 0.10)

### Metrics (baseline)

| domain_assign | 1.0000 |
| wrong_auto_rate | 0.0000 |
| review_route | 1.0000 |
| orphan_detect | 1.0000 |
| review_workload | 0.1818 |
| strict_outcome | 1.0000 |
| objective | 0.8782 |

## Comparison

| Metric | Baseline | Best | Delta |
|--------|----------|------|-------|
| domain_assignment_accuracy | 1.0000 | 1.0000 | +0.0000 |
| wrong_auto_assignment_rate | 0.0000 | 0.0000 | +0.0000 |
| review_routing_accuracy | 1.0000 | 1.0000 | +0.0000 |
| orphan_detection_accuracy | 1.0000 | 1.0000 | +0.0000 |
| review_workload_fraction | 0.1818 | 0.1818 | +0.0000 |
| strict_outcome_accuracy | 1.0000 | 1.0000 | +0.0000 |
| objective_score | 0.8782 | 0.8782 | +0.0000 |

## Top 5 threshold tuples (by objective)

1. objective=0.8782  auto=0.6 orphan=0.4 margin=0.1  da=1.000 wrong_auto=0.000 review_rt=1.000 orphan=1.000 review_load=0.182
2. objective=0.8782  auto=0.6 orphan=0.45 margin=0.1  da=1.000 wrong_auto=0.000 review_rt=1.000 orphan=1.000 review_load=0.182
3. objective=0.8782  auto=0.65 orphan=0.4 margin=0.05  da=1.000 wrong_auto=0.000 review_rt=1.000 orphan=1.000 review_load=0.182
4. objective=0.8782  auto=0.65 orphan=0.4 margin=0.1  da=1.000 wrong_auto=0.000 review_rt=1.000 orphan=1.000 review_load=0.182
5. objective=0.8782  auto=0.65 orphan=0.45 margin=0.05  da=1.000 wrong_auto=0.000 review_rt=1.000 orphan=1.000 review_load=0.182

## Outputs

- `data/evaluation/optimal_domain_thresholds.json`
- `data/evaluation/domain_threshold_calibration_report.md`
