"""
Interpretation drift: same schema / column / type but meaning or numeric encoding differs.

- Meaning: embedding similarity only (no hand-tuned field-weight score).
- Numeric scale: data-driven affine / min-max proposals vs baseline reference moments.
- Decisions: driven by interpretation_calibration.json (operator-tunable, not scattered constants).
- Outputs: APPEND | SELF_HEAL | HUMAN_REVIEW | QUARANTINE (+ transform proposals for humans).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.services.semantic_drift import embedding_service

_CALIB_PATH = Path(__file__).resolve().parent / "interpretation_calibration.json"
_CALIB_CACHE: Optional[Dict[str, Any]] = None
_CALIB_MTIME: float = 0.0


def load_calibration() -> Dict[str, Any]:
    global _CALIB_CACHE, _CALIB_MTIME
    try:
        mtime = _CALIB_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _CALIB_CACHE is not None and mtime == _CALIB_MTIME:
        return _CALIB_CACHE
    if _CALIB_PATH.exists():
        _CALIB_CACHE = json.loads(_CALIB_PATH.read_text(encoding="utf-8"))
    else:
        _CALIB_CACHE = {}
    _CALIB_MTIME = mtime
    return _CALIB_CACHE


def _baseline_text_payload(baseline_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "column_name": baseline_profile.get("column_name", ""),
        "business_meaning": baseline_profile.get("business_meaning", ""),
        "role": baseline_profile.get("role", ""),
        "domain": baseline_profile.get("domain", ""),
        "unit": baseline_profile.get("unit", ""),
        "scale": baseline_profile.get("scale", ""),
        "value_direction": baseline_profile.get("value_direction", ""),
    }


def _new_text_payload(new_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "column_name": new_profile.get("column_name", ""),
        "business_meaning": new_profile.get("detected_business_meaning", ""),
        "role": new_profile.get("role", ""),
        "domain": new_profile.get("domain", ""),
        "unit": new_profile.get("unit", ""),
        "scale": new_profile.get("scale", ""),
        "value_direction": new_profile.get("value_direction", ""),
    }


def meaning_similarity_only(baseline_profile: Dict[str, Any], new_profile: Dict[str, Any]) -> float:
    t1 = embedding_service.build_comparison_text(_baseline_text_payload(baseline_profile))
    t2 = embedding_service.build_comparison_text(_new_text_payload(new_profile))
    return float(embedding_service.calculate_semantic_similarity(t1, t2))


def _moment_alignment(transformed: np.ndarray, ref: Dict[str, Any]) -> float:
    if transformed.size == 0 or not np.all(np.isfinite(transformed)):
        return 0.0
    rm = float(ref.get("ref_mean", 0.0))
    rs = max(float(ref.get("ref_std", 1e-9)), 1e-9)
    rmin = float(ref.get("ref_min", rm))
    rmax = float(ref.get("ref_max", rm))
    tm = float(np.mean(transformed))
    ts = max(float(np.std(transformed, ddof=0)), 1e-9)
    z_mean = abs(tm - rm) / rs
    z_std = abs(ts - rs) / rs
    span_new = float(np.max(transformed) - np.min(transformed)) if transformed.size else 0.0
    span_ref = max(rmax - rmin, 1e-9)
    z_span = abs(span_new - span_ref) / span_ref
    penalty = z_mean + 0.5 * z_std + 0.15 * z_span
    return float(1.0 / (1.0 + penalty))


def _numeric_series(series: pd.Series) -> np.ndarray:
    s = pd.to_numeric(series, errors="coerce").astype(float).to_numpy()
    return s[np.isfinite(s)]


def propose_numeric_transforms(
    series: pd.Series,
    baseline_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare upload column to baseline reference stats; propose identity / affine / minmax.
    All scoring is from distributional fit (no magic column-name rules).
    """
    ref_n = baseline_profile.get("ref_n")
    has_ref = (ref_n is not None and int(ref_n) > 0) or baseline_profile.get("ref_mean") is not None
    if not has_ref:
        return {
            "is_numeric": True,
            "has_reference": False,
            "candidates": [{"kind": "identity", "params": {}, "alignment_score": 0.5}],
            "best": {"kind": "identity", "params": {}, "alignment_score": 0.5},
            "identity_alignment": 0.5,
        }

    raw = _numeric_series(series)
    if raw.size == 0:
        return {
            "is_numeric": True,
            "has_reference": True,
            "candidates": [{"kind": "identity", "params": {}, "alignment_score": 0.0}],
            "best": {"kind": "identity", "params": {}, "alignment_score": 0.0},
        }

    ref_mean = float(baseline_profile.get("ref_mean", 0.0))
    ref_std = max(float(baseline_profile.get("ref_std", 1e-9)), 1e-9)
    ref_min = float(baseline_profile.get("ref_min", ref_mean))
    ref_max = float(baseline_profile.get("ref_max", ref_mean))

    candidates: List[Dict[str, Any]] = []

    # identity
    ident = raw.astype(float)
    candidates.append({"kind": "identity", "params": {}, "alignment_score": _moment_alignment(ident, baseline_profile)})

    # two-moment affine: match mean and std of baseline
    m_new = float(np.mean(raw))
    s_new = max(float(np.std(raw, ddof=0)), 1e-9)
    a = ref_std / s_new
    b = ref_mean - a * m_new
    aff = a * raw + b
    candidates.append({"kind": "affine", "params": {"a": float(a), "b": float(b)}, "alignment_score": _moment_alignment(aff, baseline_profile)})

    # min-max to baseline range
    mn, mx = float(np.min(raw)), float(np.max(raw))
    if mx - mn > 1e-12 and ref_max - ref_min > 1e-12:
        mm = (raw - mn) / (mx - mn) * (ref_max - ref_min) + ref_min
        candidates.append(
            {
                "kind": "minmax",
                "params": {"src_min": mn, "src_max": mx, "dst_min": ref_min, "dst_max": ref_max},
                "alignment_score": _moment_alignment(mm, baseline_profile),
            }
        )

    best = max(candidates, key=lambda c: float(c["alignment_score"]))
    ident_al = float(candidates[0]["alignment_score"])
    span_new = float(np.max(raw) - np.min(raw))
    span_ref = max(ref_max - ref_min, 1e-9)
    ratio = span_ref / max(span_new, 1e-9)
    span_mismatch = span_new > 1e-9 and (ratio > 3.0 or ratio < (1.0 / 3.0))
    improvement = float(best["alignment_score"]) - ident_al
    suspect_encoding_shift = bool(
        span_mismatch or (ident_al < 0.55 and improvement > 0.12) or (ident_al < 0.45 and float(best["alignment_score"]) > 0.55)
    )
    return {
        "is_numeric": True,
        "has_reference": True,
        "candidates": candidates,
        "best": best,
        "identity_alignment": ident_al,
        "suspect_encoding_shift": suspect_encoding_shift,
        "span_ratio": float(ratio) if span_new > 1e-9 else None,
    }


def _combined_score(sim: float, align: float, cal: Dict[str, Any]) -> float:
    w = cal.get("weights", {})
    wm = float(w.get("meaning_similarity", 0.55))
    wa = float(w.get("numeric_alignment", 0.45))
    return wm * sim + wa * align


def _apply_guard(
    baseline_profile: Dict[str, Any],
    new_profile: Dict[str, Any],
    guard: Dict[str, Any],
) -> bool:
    if not guard.get("enabled", True):
        return False
    col = str(new_profile.get("column_name", ""))
    rx = guard.get("column_name_regex")
    if rx and not re.search(rx, col):
        return False
    bm = str(baseline_profile.get("business_meaning", "")).lower()
    nm = str(new_profile.get("detected_business_meaning", "")).lower()
    b_any = [x.lower() for x in guard.get("baseline_meaning_contains_any", [])]
    n_any = [x.lower() for x in guard.get("new_meaning_contains_any", [])]
    if b_any and not any(x in bm for x in b_any):
        return False
    if n_any and not any(x in nm for x in n_any):
        return False
    return True


def _guard_action(baseline_profile: Dict[str, Any], new_profile: Dict[str, Any], cal: Dict[str, Any]) -> Optional[str]:
    for g in cal.get("semantic_guards", []):
        if _apply_guard(baseline_profile, new_profile, g):
            return str(g.get("action", "QUARANTINE")).upper()
    return None


def interpret_column_drift(
    baseline_profile: Dict[str, Any],
    new_profile: Dict[str, Any],
    upload_series: Optional[pd.Series],
    cal: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cal = cal or load_calibration()
    sim = meaning_similarity_only(baseline_profile, new_profile)
    reasons: List[str] = ["meaning_embedding_similarity"]

    guard_act = _guard_action(baseline_profile, new_profile, cal)
    if guard_act == "QUARANTINE":
        row = _result_row(
            new_profile,
            baseline_profile,
            sim,
            alignment=sim,
            combined=0.0,
            drift_score=100.0,
            severity="HIGH",
            decision="QUARANTINE",
            reasons=reasons + ["semantic_guard_triggered"],
            explanation="Governance guard flagged a dangerous semantic flip (config: semantic_guards).",
            transform_bundle=None,
        )
        row["recommended_action"] = "Quarantine dataset; unsafe semantic shift per governance guard."
        row["interpretation"] = {"meaning_similarity": round(sim, 4), "guard": True}
        return row

    dtype = str(new_profile.get("data_type", "")).lower()
    bdt = str(baseline_profile.get("data_type", "")).lower()
    numeric_like = dtype in ("integer", "decimal", "float") and bdt in ("integer", "decimal", "float", "")

    transform_bundle: Optional[Dict[str, Any]] = None
    align = sim
    suspect = False
    if numeric_like and upload_series is not None:
        transform_bundle = propose_numeric_transforms(upload_series, baseline_profile)
        ident_al = float(transform_bundle.get("identity_alignment", transform_bundle["best"]["alignment_score"]))
        best_al = float(transform_bundle["best"]["alignment_score"])
        suspect = bool(transform_bundle.get("suspect_encoding_shift"))
        if suspect and transform_bundle.get("has_reference"):
            align = max(sim, best_al, ident_al)
            reasons.append("numeric_encoding_shift_suspected")
        else:
            align = sim
            reasons.append("numeric_profiled_meaning_only")

    comb = _combined_score(sim, align, cal) if suspect else float(sim)
    cs = cal.get("combined_score", {})
    append_min = float(cs.get("append_min", 0.78))
    heal_min = float(cs.get("heal_min", 0.58))
    quarantine_sim_below = float(cs.get("quarantine_meaning_similarity_below", 0.35))
    nt = cal.get("numeric_transform", {})
    min_impr = float(nt.get("min_improvement_to_prefer_transform", 0.06))
    min_align_heal = float(nt.get("min_alignment_for_auto_heal", 0.62))
    min_sim_heal = float(nt.get("min_meaning_similarity_for_numeric_heal", 0.62))

    improvement = 0.0
    if transform_bundle and transform_bundle.get("has_reference"):
        improvement = float(transform_bundle["best"]["alignment_score"]) - float(transform_bundle.get("identity_alignment", 0.0))

    decision = "APPEND"
    explanation_bits = [f"Meaning similarity={sim:.3f} (embedding-only).", f"Alignment score={align:.3f}.", f"Combined={comb:.3f}."]

    if comb >= append_min:
        decision = "APPEND"
    elif suspect and numeric_like and transform_bundle and transform_bundle.get("has_reference"):
        if (
            improvement >= min_impr
            and float(transform_bundle["best"]["alignment_score"]) >= min_align_heal
            and sim >= min_sim_heal
        ):
            decision = "SELF_HEAL"
            explanation_bits.append(
                f"Numeric encoding differs; best transform={transform_bundle['best']['kind']} improves alignment by {improvement:.3f}."
            )
        elif comb >= heal_min:
            decision = "HUMAN_REVIEW"
            explanation_bits.append("Possible rescaling or meaning shift — human confirmation recommended before auto-heal.")
        else:
            decision = "HUMAN_REVIEW"
            explanation_bits.append("Low combined confidence — route to human review.")
    else:
        if comb >= heal_min:
            decision = "HUMAN_REVIEW"
        else:
            decision = "QUARANTINE" if sim < quarantine_sim_below else "HUMAN_REVIEW"
        explanation_bits.append("Non-numeric or missing baseline reference stats; decisions use meaning similarity only.")

    drift_score = round(100.0 * (1.0 - comb), 2)
    if decision == "QUARANTINE":
        severity = "HIGH"
    elif decision == "HUMAN_REVIEW":
        severity = "MODERATE"
    elif decision == "SELF_HEAL":
        severity = "MODERATE"
    else:
        severity = "NONE" if sim >= 0.85 else "LOW"

    rec = {
        "APPEND": "Append without structural repair.",
        "SELF_HEAL": "Apply proposed transforms then re-profile.",
        "HUMAN_REVIEW": "Hold for human approval; do not auto-apply ambiguous transforms.",
        "QUARANTINE": "Block ingestion until baseline or upload is corrected.",
    }[decision]

    out = _result_row(
        new_profile,
        baseline_profile,
        sim,
        alignment=align,
        combined=comb,
        drift_score=drift_score,
        severity=severity,
        decision=decision,
        reasons=reasons,
        explanation=" ".join(explanation_bits),
        transform_bundle=transform_bundle,
    )
    out["recommended_action"] = rec
    out["interpretation"] = {
        "meaning_similarity": round(sim, 4),
        "alignment_score": round(align, 4),
        "combined_score": round(comb, 4),
        "numeric_transform": transform_bundle,
        "calibration_path": str(_CALIB_PATH),
    }
    return out


def _result_row(
    new_profile: Dict[str, Any],
    baseline_profile: Dict[str, Any],
    sim: float,
    alignment: float,
    combined: float,
    drift_score: float,
    severity: str,
    decision: str,
    reasons: List[str],
    explanation: str,
    transform_bundle: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    business_risk = (
        "Guard triggered: possible inventory vs sales semantics."
        if decision == "QUARANTINE" and any("semantic_guard" in r for r in reasons)
        else "Low risk" if decision == "APPEND" else "Review recommended."
    )
    return {
        "column_name": str(new_profile.get("column_name")),
        "baseline_meaning": baseline_profile.get("business_meaning", ""),
        "new_meaning": new_profile.get("detected_business_meaning", ""),
        "similarity_score": round(sim, 4),
        "drift_score": drift_score,
        "severity": severity,
        "decision": decision,
        "reasons": reasons,
        "explanation": explanation.strip(),
        "business_risk": business_risk,
        "recommended_action": "",
        "transform_proposal": transform_bundle["best"] if transform_bundle else None,
    }


def detect_dataset_interpretation_drift(
    baseline_profiles: List[Dict[str, Any]],
    new_profile_bundle: Dict[str, Any],
    upload_df: Optional[pd.DataFrame],
    cal: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    # Lazy import avoids circular import with drift_detection_service.
    from src.services.semantic_drift.drift_detection_service import match_columns

    cal = cal or load_calibration()
    cols = new_profile_bundle.get("columns") or {}
    mapping, unmatched_new, unmatched_baseline = match_columns(baseline_profiles, cols)
    baseline_by_name = {str(p["column_name"]): p for p in baseline_profiles}
    results: List[Dict[str, Any]] = []

    for new_col, base_col in mapping.items():
        series = upload_df[new_col] if upload_df is not None and new_col in upload_df.columns else None
        row = interpret_column_drift(baseline_by_name[base_col], cols[new_col], series, cal=cal)
        row["mapped_from"] = new_col
        results.append(row)

    for uc in unmatched_new:
        results.append(
            {
                "column_name": uc,
                "baseline_meaning": "",
                "new_meaning": cols[uc].get("detected_business_meaning", ""),
                "similarity_score": 0.0,
                "drift_score": 100.0,
                "severity": "HIGH",
                "decision": "QUARANTINE",
                "reasons": ["new_unmapped_column"],
                "explanation": "New column not present in approved baseline.",
                "business_risk": "Unknown column could break downstream contracts.",
                "recommended_action": "Add to baseline via governance or quarantine.",
                "interpretation": None,
                "transform_proposal": None,
            }
        )

    for ub in unmatched_baseline:
        results.append(
            {
                "column_name": ub,
                "baseline_meaning": baseline_by_name[ub].get("business_meaning", ""),
                "new_meaning": "",
                "similarity_score": 1.0,
                "drift_score": 5.0,
                "severity": "LOW",
                "decision": "APPEND",
                "reasons": ["missing_optional_in_upload"],
                "explanation": "Baseline column absent in upload; optional columns may be filled later.",
                "business_risk": "Low if column is optional.",
                "recommended_action": "Allow self-healing to add optional defaults when configured.",
                "interpretation": None,
                "transform_proposal": None,
            }
        )

    return results


def aggregate_interpretation_decision(results: List[Dict[str, Any]]) -> str:
    if any(r.get("decision") == "QUARANTINE" for r in results):
        return "QUARANTINE"
    if any(r.get("decision") == "HUMAN_REVIEW" for r in results):
        return "HUMAN_REVIEW"
    if any(r.get("decision") == "SELF_HEAL" for r in results):
        return "SELF_HEAL"
    return "APPEND"
