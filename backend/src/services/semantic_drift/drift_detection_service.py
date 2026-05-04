"""
Compare baseline profiles to new upload profiles.

Primary path: interpretation drift (embedding-only meaning + numeric transform proposals;
decisions from interpretation_calibration.json). Legacy weighted score helpers remain for tests.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.services.semantic_drift import embedding_service

SYNONYMS = {
    "sales_amt": "sales_amount",
    "revenue": "sales_amount",
    "amt": "sales_amount",
    "qty": "quantity",
}


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def match_columns(
    baseline_profiles: List[Dict[str, Any]],
    new_profiles: Dict[str, Any],
) -> Tuple[Dict[str, str], List[str], List[str]]:
    """
    Returns:
      mapping new_col -> baseline_col
      unmatched_new
      unmatched_baseline
    """
    baseline_by_name = {str(p["column_name"]): p for p in baseline_profiles}
    baseline_norm = {_norm_name(k): k for k in baseline_by_name}
    mapping: Dict[str, str] = {}
    used_baseline: set[str] = set()

    new_cols = list(new_profiles.keys())
    for nc in new_cols:
        if nc in baseline_by_name:
            mapping[nc] = nc
            used_baseline.add(nc)
            continue
        nn = _norm_name(nc)
        if nn in baseline_norm:
            mapping[nc] = baseline_norm[nn]
            used_baseline.add(baseline_norm[nn])
            continue
        if nn in SYNONYMS:
            canon = SYNONYMS[nn]
            if canon in baseline_by_name:
                mapping[nc] = canon
                used_baseline.add(canon)
                continue
        if nc in SYNONYMS and SYNONYMS[nc] in baseline_by_name:
            mapping[nc] = SYNONYMS[nc]
            used_baseline.add(SYNONYMS[nc])
            continue

    unmatched_new = [c for c in new_cols if c not in mapping]
    unmatched_baseline = [p["column_name"] for p in baseline_profiles if p["column_name"] not in used_baseline]
    return mapping, unmatched_new, unmatched_baseline


def calculate_drift_score(baseline_profile: Dict[str, Any], new_profile: Dict[str, Any], similarity_score: float) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0

    def changed(field: str, weight: float, a_key: str, b_key: Optional[str] = None):
        nonlocal score
        b_key = b_key or a_key
        a = str(baseline_profile.get(a_key, "")).strip().lower()
        b = str(new_profile.get(b_key, "")).strip().lower()
        if a != b:
            score += weight
            reasons.append(f"{field}_changed")

    changed("business_meaning", 40, "business_meaning", "detected_business_meaning")
    changed("role", 25, "role")
    changed("unit", 20, "unit")
    changed("domain", 10, "domain")
    changed("data_type", 5, "data_type", "data_type")

    if similarity_score >= 0.8:
        reasons.append("similarity_high")
    elif similarity_score >= 0.6:
        reasons.append("similarity_moderate_low")
        score += 5
    elif similarity_score >= 0.4:
        reasons.append("similarity_moderate")
        score += 15
    else:
        reasons.append("similarity_low")
        score += 25

    return score, reasons


def decide_action(drift_score: float, reasons: List[str]) -> str:
    if drift_score <= 20:
        return "APPEND"
    if drift_score <= 50:
        return "SELF_HEAL"
    return "QUARANTINE"


def detect_drift_for_column(
    baseline_profile: Dict[str, Any],
    new_profile: Dict[str, Any],
    upload_series: Optional[Any] = None,
) -> Dict[str, Any]:
    from src.services.semantic_drift import interpretation_drift_service

    return interpretation_drift_service.interpret_column_drift(baseline_profile, new_profile, upload_series)


def detect_dataset_drift(
    baseline_profiles: List[Dict[str, Any]],
    new_profile_bundle: Dict[str, Any],
    upload_df: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    from src.services.semantic_drift import interpretation_drift_service

    if upload_df is not None:
        return interpretation_drift_service.detect_dataset_interpretation_drift(
            baseline_profiles, new_profile_bundle, upload_df
        )

    cols = new_profile_bundle.get("columns") or {}
    mapping, unmatched_new, unmatched_baseline = match_columns(baseline_profiles, cols)
    results: List[Dict[str, Any]] = []

    baseline_by_name = {str(p["column_name"]): p for p in baseline_profiles}

    for new_col, base_col in mapping.items():
        res = detect_drift_for_column(baseline_by_name[base_col], cols[new_col], None)
        res["mapped_from"] = new_col
        results.append(res)

    for uc in unmatched_new:
        results.append(
            {
                "column_name": uc,
                "baseline_meaning": "",
                "new_meaning": cols[uc].get("detected_business_meaning", ""),
                "similarity_score": 0.0,
                "drift_score": 60.0,
                "severity": "HIGH",
                "decision": "QUARANTINE",
                "reasons": ["new_unmapped_column"],
                "explanation": "New column not present in approved baseline.",
                "business_risk": "Unknown column could break downstream contracts.",
                "recommended_action": "Add to baseline via governance or quarantine.",
            }
        )

    for ub in unmatched_baseline:
        results.append(
            {
                "column_name": ub,
                "baseline_meaning": baseline_by_name[ub].get("business_meaning", ""),
                "new_meaning": "",
                "similarity_score": 1.0,
                "drift_score": 10.0,
                "severity": "LOW",
                "decision": "APPEND",
                "reasons": ["missing_optional_in_upload"],
                "explanation": "Baseline column absent in upload; optional columns may be filled later.",
                "business_risk": "Low if column is optional.",
                "recommended_action": "Allow self-healing to add optional defaults when configured.",
            }
        )

    return results


def aggregate_decision(results: List[Dict[str, Any]]) -> str:
    if any(r.get("decision") == "QUARANTINE" for r in results):
        return "QUARANTINE"
    if any(r.get("decision") == "HUMAN_REVIEW" for r in results):
        return "HUMAN_REVIEW"
    if any(r.get("decision") == "SELF_HEAL" for r in results):
        return "SELF_HEAL"
    return "APPEND"
