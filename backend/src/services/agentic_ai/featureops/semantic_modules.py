from __future__ import annotations

from typing import Any, Dict, List, Tuple


ROLE_SYNONYMS: Dict[str, List[str]] = {
    "quantity": ["qty", "quantity", "count", "units", "stock_qty"],
    "sales_amount": ["sales_amt", "sales_amount", "amount", "revenue", "price"],
    "order_date": ["order_dt", "order_date", "date", "timestamp", "created_at"],
    "customer_id": ["customer_id", "cust_id", "client_id"],
}


def _normalize_name(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _tokenize_name(value: str) -> List[str]:
    lowered = value.replace("_", " ").replace("-", " ").strip().lower()
    return [token for token in lowered.split() if token]


def _guess_role(column: Dict[str, Any]) -> str:
    name = str(column.get("column_name", "")).lower()
    kind = str(column.get("kind") or column.get("inferred_type") or "unknown").lower()
    scale = str(column.get("scale_pattern", "unknown")).lower()
    if any(token in name for token in ("date", "time", "timestamp", "created")) or kind == "datetime":
        return "Timestamp"
    if any(token in name for token in ("id", "code", "key")):
        return "Identifier"
    if any(token in name for token in ("qty", "quantity", "count", "units")):
        return "Measure"
    if any(token in name for token in ("amount", "price", "sales", "revenue", "cost")):
        return "Measure"
    if kind == "numeric":
        return "Measure"
    if kind == "categorical":
        return "Dimension"
    if kind == "text":
        return "Description"
    if scale in {"count", "percentage", "normalized_score"}:
        return "Measure"
    return "Unknown"


def _guess_domain(column_name: str, dataset_name: str) -> str:
    combined = f"{column_name} {dataset_name}".lower()
    if any(token in combined for token in ("sales", "order", "revenue", "customer", "invoice")):
        return "Sales"
    if any(token in combined for token in ("inventory", "stock", "warehouse", "sku")):
        return "Inventory"
    if any(token in combined for token in ("sensor", "device", "tilt", "rain", "humidity")):
        return "IoT"
    if any(token in combined for token in ("product", "catalog", "fashion", "rating")):
        return "Commerce"
    return "General"


def _guess_unit(column: Dict[str, Any]) -> str:
    if column.get("detected_unit"):
        return str(column["detected_unit"])
    scale = str(column.get("scale_pattern", "unknown")).lower()
    if scale == "count":
        return "Count"
    if scale == "percentage":
        return "Percentage"
    return "Unitless"


def _guess_value_direction(column_name: str, role: str) -> str:
    lowered = column_name.lower()
    if "risk" in lowered or "error" in lowered:
        return "Higher means higher risk"
    if "score" in lowered or "rating" in lowered:
        return "Higher means stronger score"
    if role == "Measure":
        return "Higher means more"
    return "Neutral"


def _guess_business_meaning(column_name: str, role: str, domain: str) -> str:
    tokens = _tokenize_name(column_name)
    label = " ".join(tokens) if tokens else column_name
    if role == "Timestamp":
        return f"{label} event timestamp"
    if role == "Identifier":
        return f"{label} unique identifier"
    if role == "Description":
        return f"{label} descriptive text in the {domain} domain"
    if role == "Dimension":
        return f"{label} business category in the {domain} domain"
    if role == "Measure":
        return f"{label} measured business value in the {domain} domain"
    return f"{label} business field"


def create_baseline_creation_module(profile: Dict[str, Any], baseline_version: str = "v1") -> List[Dict[str, Any]]:
    dataset_name = str(profile.get("dataset_name") or profile.get("metadata", {}).get("dataset_name") or "dataset")
    columns = profile.get("column_profiles", [])
    results: List[Dict[str, Any]] = []
    for column in columns:
        column_name = str(column.get("column_name", "unknown"))
        role = _guess_role(column)
        domain = _guess_domain(column_name, dataset_name)
        results.append(
            {
                "column_name": column_name,
                "business_meaning": _guess_business_meaning(column_name, role, domain),
                "role": role,
                "domain": domain,
                "unit": _guess_unit(column),
                "scale": str(column.get("scale_pattern", "unknown")),
                "data_type": str(column.get("kind") or column.get("inferred_type") or "unknown"),
                "value_direction": _guess_value_direction(column_name, role),
                "baseline_version": baseline_version,
            }
        )
    return results


def create_new_dataset_profiling_module(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    dataset_name = str(profile.get("dataset_name") or profile.get("metadata", {}).get("dataset_name") or "dataset")
    columns = profile.get("column_profiles", [])
    ordered_names = [str(column.get("column_name", "unknown")) for column in columns]
    results: List[Dict[str, Any]] = []
    for index, column in enumerate(columns):
        column_name = ordered_names[index]
        role = _guess_role(column)
        domain = _guess_domain(column_name, dataset_name)
        neighbors = [name for name in ordered_names[max(0, index - 1): index + 2] if name != column_name]
        results.append(
            {
                "column_name": column_name,
                "detected_data_type": str(column.get("kind") or column.get("inferred_type") or "unknown"),
                "sample_values": list(column.get("samples") or column.get("sample_values") or [])[:4],
                "nearby_columns": neighbors,
                "value_pattern": str(column.get("scale_pattern") or "unknown"),
                "possible_business_meaning": _guess_business_meaning(column_name, role, domain),
                "possible_domain": domain,
                "possible_role": role,
            }
        )
    return results


def _name_similarity(left: str, right: str) -> float:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.92
    left_tokens = set(_tokenize_name(left))
    right_tokens = set(_tokenize_name(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def _synonym_match(left: str, right: str) -> Tuple[bool, str]:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    for canonical, variants in ROLE_SYNONYMS.items():
        normalized_variants = {_normalize_name(value) for value in variants + [canonical]}
        if left_norm in normalized_variants and right_norm in normalized_variants:
            return True, canonical
    return False, ""


def create_column_matching_module(
    baseline_rows: List[Dict[str, Any]],
    profiling_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for incoming in profiling_rows:
        incoming_name = incoming["column_name"]
        best_match: Dict[str, Any] | None = None
        best_score = 0.0
        best_method = "unmatched"
        best_reason = "No confident baseline match found."

        for baseline in baseline_rows:
            baseline_name = baseline["column_name"]
            score = 0.0
            method = "semantic_similarity"
            reason = "Matched by semantic similarity."

            if incoming_name == baseline_name:
                score = 1.0
                method = "exact_name_match"
                reason = "Column name matches exactly."
            elif _normalize_name(incoming_name) == _normalize_name(baseline_name):
                score = 0.98
                method = "normalized_name_match"
                reason = "Normalized names match."
            else:
                synonym_hit, canonical = _synonym_match(incoming_name, baseline_name)
                if synonym_hit:
                    score = 0.95
                    method = "synonym_match"
                    reason = f"Both names map to the same synonym group ({canonical})."
                else:
                    score = _name_similarity(incoming_name, baseline_name)
                    if incoming.get("possible_role") == baseline.get("role"):
                        score += 0.08
                    if incoming.get("possible_domain") == baseline.get("domain"):
                        score += 0.08
                    score = min(score, 0.94)
                    reason = "Matched using semantic similarity of names, role, and domain."

            if score > best_score:
                best_score = score
                best_match = baseline
                best_method = method
                best_reason = reason

        matches.append(
            {
                "incoming_column": incoming_name,
                "baseline_column": best_match["column_name"] if best_match and best_score >= 0.45 else None,
                "match_method": best_method if best_score >= 0.45 else "unmatched",
                "match_score": round(best_score, 3),
                "baseline_role": best_match.get("role") if best_match and best_score >= 0.45 else None,
                "incoming_role": incoming.get("possible_role"),
                "baseline_domain": best_match.get("domain") if best_match and best_score >= 0.45 else None,
                "incoming_domain": incoming.get("possible_domain"),
                "reason": best_reason if best_score >= 0.45 else "No exact, normalized, synonym, or semantic match passed the baseline threshold.",
            }
        )
    return matches
