"""LinUCB arm selection: highest UCB score, with drift-aware tie-breaking.

Used by the API (live drift) and offline trainer so replay matches production.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple


def build_drift_counts_from_diff(diff_payload: Dict[str, Any]) -> Dict[str, int]:
    """Same counting rules as API ``_build_drift_counts`` (standard diff shape)."""
    if not isinstance(diff_payload, dict):
        return {"new": 0, "missing": 0, "dtype": 0, "renames": 0}
    return {
        "new": len(diff_payload.get("new_columns", []) or []),
        "missing": len(diff_payload.get("missing_columns", []) or []),
        "dtype": len(diff_payload.get("dtype_changes", []) or []),
        "renames": len(diff_payload.get("renames", []) or []),
    }


def drift_severity_bucket_for_tiebreak(diff_payload: Dict[str, Any]) -> str:
    """Coarse drift severity used only to break LinUCB score ties (not the primary decision)."""
    counts = build_drift_counts_from_diff(diff_payload)
    missing = counts.get("missing", 0)
    dtype_c = counts.get("dtype", 0)
    total = sum(counts.values())
    if missing > 0 or dtype_c >= 3 or total >= 8:
        return "high"
    if missing == 0 and dtype_c <= 1 and total <= 3:
        return "low"
    return "medium"


def preferred_action_order_for_tiebreak(severity: str) -> tuple:
    """When UCB scores tie, pick the first action in this list that appears in the tie set."""
    if severity == "high":
        return (
            "require_human_approval",
            "quarantine_data",
            "rollback_previous_schema",
            "create_new_schema_version",
            "auto_merge_schema",
        )
    if severity == "low":
        return (
            "auto_merge_schema",
            "create_new_schema_version",
            "require_human_approval",
            "quarantine_data",
            "rollback_previous_schema",
        )
    return (
        "create_new_schema_version",
        "require_human_approval",
        "auto_merge_schema",
        "quarantine_data",
        "rollback_previous_schema",
    )


def select_rl_action_from_scores(
    scores: Dict[str, float],
    diff_payload: Dict[str, Any],
) -> Tuple[str, float, Dict[str, Any]]:
    """Choose the arm with highest score; break ties using drift-aware priority.

    Returns:
        (chosen_action, winning_score, meta) where meta includes scores and tie-break info.
    """
    if not scores:
        raise ValueError("LinUCB scores dict is empty")

    best_score = max(scores.values())
    tied = [
        a
        for a, s in scores.items()
        if math.isclose(s, best_score, rel_tol=1e-9, abs_tol=1e-9)
    ]
    tied_sorted = sorted(tied)
    severity = drift_severity_bucket_for_tiebreak(diff_payload)
    meta: Dict[str, Any] = {
        "action_scores": dict(sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top_score": float(best_score),
        "tied_actions": tied_sorted,
        "score_tie": len(tied) > 1,
        "tie_break_severity": severity,
    }

    if len(tied) == 1:
        meta["tie_break_applied"] = False
        return tied[0], float(best_score), meta

    preference = preferred_action_order_for_tiebreak(severity)
    chosen = None
    for a in preference:
        if a in tied:
            chosen = a
            break
    if chosen is None:
        chosen = tied_sorted[0]
    meta["tie_break_applied"] = True
    meta["tie_break_choice_among"] = tied_sorted
    meta["tie_break_rule"] = (
        f"drift_severity={severity}; first matching action in severity-specific priority order"
    )
    return chosen, float(best_score), meta
