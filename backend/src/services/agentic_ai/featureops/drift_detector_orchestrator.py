"""
Learned twin-baseline drift orchestration for Agentic Semantic FeatureOps.

This pipeline coordinates:
1. ProfilerAgent
2. BaselineAgent
3. RelationalAnchorAgent
4. LearnedScoringAgent

It replaces the previous broken hybrid integration with a working end-to-end
analysis flow that returns:
- normalized current/internal/external profiles
- validated relational anchors
- learned SAFE / CONDITIONAL / QUARANTINED predictions
- row-level triage
- column-level explanations
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.services.agentic_ai.featureops.agents.baseline_agent import BaselineAgent
from src.services.agentic_ai.featureops.agents.learned_scoring_agent import LearnedScoringAgent
from src.services.agentic_ai.featureops.agents.profiler_agent import ProfilerAgent
from src.services.agentic_ai.featureops.agents.relational_anchor_agent import RelationalAnchorAgent
from src.services.agentic_ai.featureops.predefined_baselines import (
    get_predefined_baseline,
    list_predefined_baselines,
    predefined_baseline_to_rows,
)
from src.services.agentic_ai.featureops.semantic_modules import (
    create_baseline_creation_module,
    create_column_matching_module,
    create_new_dataset_profiling_module,
)

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return default
        return numeric
    except Exception:
        return default


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    left_vector = np.asarray(left[:size], dtype=float)
    right_vector = np.asarray(right[:size], dtype=float)
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator <= 0:
        return 0.0
    return float(np.dot(left_vector, right_vector) / denominator)


def _entropy(values: List[str]) -> float:
    if not values:
        return 0.0
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    total = float(sum(counts.values()))
    result = 0.0
    for count in counts.values():
        probability = count / total
        if probability > 0:
            result -= probability * math.log(probability)
    return float(result)


@dataclass
class DriftAnalysis:
    drift_run_id: str
    timestamp: str
    dataset_name: str
    profile: Dict[str, Any]
    baselines: Dict[str, Any]
    available_predefined_baselines: List[Dict[str, Any]]
    selected_predefined_baseline: Optional[Dict[str, Any]]
    baseline_creation: List[Dict[str, Any]]
    new_dataset_profiling: List[Dict[str, Any]]
    column_matching: List[Dict[str, Any]]
    anchors: List[Dict[str, Any]]
    triage_matrix: Dict[str, Any]
    drifts_per_column: List[Dict[str, Any]]
    row_classifications: List[Dict[str, Any]]
    cross_modal: Dict[str, Any]
    human_review_queue: List[Dict[str, Any]]
    learned_scores: Dict[str, Any]
    release_summary: Dict[str, int]
    final_label: str
    overall_drift_score: float
    confidence: float
    severity: str
    reasons: List[str]
    affected_columns: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DriftDetectorOrchestrator:
    """Working learned drift pipeline for the DE component."""

    def __init__(self, state_dir: Path, openai_api_key: Optional[str] = None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = self.state_dir / "orchestrator_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir = self.state_dir.parent / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.profiler = ProfilerAgent()
        self.baseline_agent = BaselineAgent(self.state_dir)
        self.anchor_agent = RelationalAnchorAgent()
        self.scoring_agent = LearnedScoringAgent(self.model_dir)

        if self.scoring_agent.model is None:
            try:
                self.scoring_agent.train(num_samples_per_class=120)
                logger.info("Initialized learned drift model with synthetic training data.")
            except Exception as exc:
                logger.warning("Failed to bootstrap learned scoring model: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect_drift(
        self,
        current_data: pd.DataFrame,
        dataset_name: str,
        predefined_baseline_key: Optional[str] = None,
    ) -> DriftAnalysis:
        run_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        current_profile = self._normalize_profile(self.profiler.build_profile(current_data, dataset_name))
        internal_baseline = self._normalize_profile(
            self.baseline_agent.load_internal_baseline() or current_profile
        )
        external_baseline = self._normalize_profile(
            self.baseline_agent.load_external_baseline() or current_profile
        )

        if self.baseline_agent.load_internal_baseline() is None:
            self.baseline_agent.save_internal_baseline(current_profile)
        if self.baseline_agent.load_external_baseline() is None:
            self.baseline_agent.save_external_baseline(current_profile)

        available_predefined_baselines = list_predefined_baselines()
        suggested_predefined_baseline_key = predefined_baseline_key or self._suggest_predefined_baseline_key(
            dataset_name,
            current_profile,
            available_predefined_baselines,
        )
        selected_predefined_baseline = (
            get_predefined_baseline(suggested_predefined_baseline_key)
            if suggested_predefined_baseline_key
            else None
        )

        baseline_creation = (
            predefined_baseline_to_rows(selected_predefined_baseline)
            if selected_predefined_baseline
            else create_baseline_creation_module(
                internal_baseline,
                baseline_version=str(internal_baseline.get("baseline_version") or "v1"),
            )
        )
        new_dataset_profiling = create_new_dataset_profiling_module(current_profile)
        column_matching = create_column_matching_module(baseline_creation, new_dataset_profiling)

        sample_rows = current_data.head(min(len(current_data), 50))
        discovered_anchors = self.anchor_agent.discover_anchors(internal_baseline, sample_rows)
        validated_anchors = self.anchor_agent.validate_anchors(discovered_anchors, sample_rows)
        normalized_anchors = [self._normalize_anchor(anchor) for anchor in validated_anchors]

        dataset_features, dataset_feature_explanations = self._build_dataset_features(
            current_profile,
            internal_baseline,
            external_baseline,
            normalized_anchors,
        )
        learned_scores = self.scoring_agent.score(dataset_features)
        row_classifications = self._build_row_classifications(
            current_data,
            current_profile,
            internal_baseline,
            external_baseline,
            normalized_anchors,
        )
        cross_modal = self._run_cross_modal_checks(
            current_data,
            current_profile,
            internal_baseline,
            external_baseline,
            normalized_anchors,
            row_classifications,
        )
        triage_matrix = self._build_triage_matrix(row_classifications)
        drifts_per_column = self._analyze_column_drifts(
            current_profile,
            internal_baseline,
            external_baseline,
            normalized_anchors,
        )

        final_label = learned_scores.get("label", "SAFE")
        probabilities = learned_scores.get("probabilities", {})
        overall_drift_score = float(
            probabilities.get("QUARANTINED", 0.0) + 0.5 * probabilities.get("CONDITIONAL", 0.0)
        )
        confidence = float(learned_scores.get("confidence", 0.0))
        severity = self._severity_from_label(final_label, overall_drift_score)
        reasons = self._build_reasons(
            final_label,
            dataset_features,
            dataset_feature_explanations,
            normalized_anchors,
            row_classifications,
        )
        affected_columns = sorted(
            {
                drift["column_name"]
                for drift in drifts_per_column
                if drift["severity"] in {"moderate", "high"}
            }
        )
        release_summary = {
            "SAFE": sum(1 for drift in drifts_per_column if drift["severity"] in {"none", "low"}),
            "CONDITIONAL": sum(1 for drift in drifts_per_column if drift["severity"] == "moderate"),
            "QUARANTINED": sum(1 for drift in drifts_per_column if drift["severity"] == "high"),
        }

        analysis = DriftAnalysis(
            drift_run_id=run_id,
            timestamp=timestamp,
            dataset_name=dataset_name,
            profile=current_profile,
            baselines={
                "internal": internal_baseline,
                "external": external_baseline,
            },
            available_predefined_baselines=available_predefined_baselines,
            selected_predefined_baseline=selected_predefined_baseline,
            baseline_creation=baseline_creation,
            new_dataset_profiling=new_dataset_profiling,
            column_matching=column_matching,
            anchors=normalized_anchors,
            triage_matrix=triage_matrix,
            drifts_per_column=drifts_per_column,
            row_classifications=row_classifications,
            cross_modal=cross_modal,
            human_review_queue=cross_modal.get("human_review_queue", []),
            learned_scores={
                "features": dataset_features,
                "probabilities": probabilities,
                "confidence": confidence,
                "feature_importance": self.scoring_agent.get_feature_importance(),
                "model_info": self.scoring_agent.get_model_info(),
            },
            release_summary=release_summary,
            final_label=final_label,
            overall_drift_score=overall_drift_score,
            confidence=confidence,
            severity=severity,
            reasons=reasons,
            affected_columns=affected_columns,
        )
        self._save_analysis(analysis)
        return analysis

    def set_baseline(self, scope: str, data: pd.DataFrame, dataset_name: str) -> Dict[str, Any]:
        profile = self._normalize_profile(self.profiler.build_profile(data, dataset_name))
        if scope == "internal":
            result = self.baseline_agent.save_internal_baseline(profile)
        else:
            result = self.baseline_agent.save_external_baseline(profile)
        return {"status": "ok", "scope": scope, "profile": profile, "save_result": result}

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------
    def _normalize_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        if not profile:
            return {
                "dataset_name": "unknown",
                "created_at": datetime.utcnow().isoformat(),
                "row_count": 0,
                "column_count": 0,
                "column_profiles": [],
                "relational_anchors": [],
                "summary_text": "",
                "summary_embedding": [],
            }

        metadata = profile.get("metadata", {})
        summary = profile.get("summary", {})
        column_profiles = [self._normalize_column_profile(column) for column in profile.get("column_profiles", [])]
        return {
            "dataset_name": profile.get("dataset_name") or metadata.get("dataset_name") or "dataset",
            "created_at": profile.get("built_at") or metadata.get("built_at") or datetime.utcnow().isoformat(),
            "row_count": int(profile.get("row_count") or metadata.get("row_count") or 0),
            "column_count": int(profile.get("column_count") or metadata.get("column_count") or len(column_profiles)),
            "column_profiles": column_profiles,
            "relational_anchors": profile.get("relational_anchors", []),
            "summary_text": profile.get("summary_text") or summary.get("text") or "",
            "summary_embedding": profile.get("summary_embedding") or summary.get("embedding") or [],
        }

    def _normalize_column_profile(self, column: Dict[str, Any]) -> Dict[str, Any]:
        numeric_stats = column.get("numeric_stats", {})
        stats = column.get("statistics", {})
        categorical_stats = column.get("categorical_stats", {})
        kind = column.get("kind") or column.get("inferred_type") or "unknown"
        return {
            "column_name": column.get("column_name", "unknown"),
            "inferred_type": kind,
            "kind": kind,
            "missing_percent": float(column.get("missing_percent", stats.get("missing_rate", 0.0))),
            "unique_percent": float(
                column.get("unique_percent")
                if column.get("unique_percent") is not None
                else (
                    (stats.get("unique_count", 0) / max(stats.get("non_null_count", 1), 1))
                    if stats.get("non_null_count") is not None
                    else 0.0
                )
            ),
            "min": column.get("min", numeric_stats.get("min")),
            "max": column.get("max", numeric_stats.get("max")),
            "mean": column.get("mean", numeric_stats.get("mean")),
            "std": column.get("std", numeric_stats.get("std")),
            "sample_values": column.get("sample_values") or column.get("samples") or [],
            "row_count": int(column.get("row_count", stats.get("row_count", 0))),
            "column_count": 0,
            "scale_pattern": column.get("scale_pattern", "unknown"),
            "detected_unit": column.get("detected_unit", column.get("unit", "unitless")),
            "detected_direction": column.get("detected_direction", column.get("value_direction", "neutral")),
            "topic_summary": column.get("topic_summary", ""),
            "summary_text": column.get("summary_text", ""),
            "top_values": column.get("top_values") or categorical_stats.get("top_values") or [],
        }

    def _normalize_anchor(self, anchor: Dict[str, Any]) -> Dict[str, Any]:
        anchor_type = anchor.get("type", "numeric_correlation")
        mapped_type = {
            "numeric_correlation": "numeric-numeric",
            "numeric_text_relationship": "numeric-text",
            "categorical_text_relationship": "categorical-text",
        }.get(anchor_type, "numeric-text")
        column_1 = anchor.get("left_column") or anchor.get("numeric_column") or anchor.get("column_1") or ""
        column_2 = anchor.get("right_column") or anchor.get("text_column") or anchor.get("column_2") or ""
        validation_status = anchor.get("validation_status") or anchor.get("status") or "valid"
        mapped_status = {
            "valid": "valid",
            "discovered": "valid",
            "degraded": "weakened",
            "weakened": "weakened",
            "violated": "violated",
        }.get(validation_status, "valid")
        description = (
            anchor.get("baseline_rule")
            or anchor.get("description")
            or anchor.get("llm_evidence")
            or "Relationship discovered from baseline data."
        )
        return {
            "anchor_id": anchor.get("anchor_id") or f"{column_1}_{column_2}_anchor",
            "type": mapped_type,
            "column_1": column_1,
            "column_2": column_2,
            "status": mapped_status,
            "confidence": float(anchor.get("confidence", 0.65)),
            "baseline_correlation": _safe_float(
                anchor.get("correlation_strength", anchor.get("baseline_correlation_strength", 0.0))
            ),
            "current_correlation": _safe_float(
                anchor.get("current_correlation_strength", anchor.get("current_correlation", 0.0))
            ),
            "description": description,
            "violation_reason": anchor.get("violation_reason"),
        }

    def _suggest_predefined_baseline_key(
        self,
        dataset_name: str,
        current_profile: Dict[str, Any],
        available_predefined_baselines: List[Dict[str, Any]],
    ) -> Optional[str]:
        dataset_name_normalized = str(dataset_name or "").lower()
        current_columns = {
            str(column.get("column_name", "")).strip().lower()
            for column in current_profile.get("column_profiles", [])
            if column.get("column_name")
        }
        best_key: Optional[str] = None
        best_score = 0.0
        for baseline in available_predefined_baselines:
            baseline_key = str(baseline.get("baseline_key") or "")
            baseline_name = str(baseline.get("dataset_name") or "").lower()
            baseline_columns = {str(name).strip().lower() for name in (baseline.get("columns") or {}).keys()}
            overlap_score = (
                len(current_columns & baseline_columns) / max(len(baseline_columns), 1)
                if baseline_columns
                else 0.0
            )
            name_score = 0.0
            if baseline_key and baseline_key in dataset_name_normalized:
                name_score = 0.45
            elif baseline_name and baseline_name in dataset_name_normalized:
                name_score = 0.4
            score = overlap_score + name_score
            if score > best_score:
                best_score = score
                best_key = baseline_key
        return best_key if best_score >= 0.25 else None

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------
    def _build_dataset_features(
        self,
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
        anchors: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, float], List[str]]:
        internal_columns = {col["column_name"]: col for col in internal_baseline.get("column_profiles", [])}
        external_columns = {col["column_name"]: col for col in external_baseline.get("column_profiles", [])}
        current_columns = {col["column_name"]: col for col in current_profile.get("column_profiles", [])}
        common_internal = sorted(set(current_columns) & set(internal_columns))
        common_external = sorted(set(current_columns) & set(external_columns))

        internal_mean_distances: List[float] = []
        external_mean_distances: List[float] = []
        std_ratios: List[float] = []
        scale_mismatches = 0
        categorical_entropy_ratios: List[float] = []
        semantic_internal_similarities: List[float] = []
        semantic_external_similarities: List[float] = []
        per_column_drifts: List[float] = []

        for column_name in common_internal:
            current = current_columns[column_name]
            baseline = internal_columns[column_name]
            if current["inferred_type"] == "numeric" and baseline["inferred_type"] == "numeric":
                baseline_std = max(abs(_safe_float(baseline.get("std"), 1.0)), 1e-6)
                mean_distance = abs(_safe_float(current.get("mean")) - _safe_float(baseline.get("mean"))) / baseline_std
                internal_mean_distances.append(mean_distance)
                std_ratios.append(
                    abs(_safe_float(current.get("std"), 0.0) - _safe_float(baseline.get("std"), 0.0))
                    / max(abs(_safe_float(baseline.get("std"), 1.0)), 1e-6)
                )
                if current.get("scale_pattern") != baseline.get("scale_pattern"):
                    scale_mismatches += 1
                per_column_drifts.append(min(1.0, mean_distance / 4.0))
            else:
                similarity = self._semantic_similarity(
                    current.get("summary_text") or current.get("topic_summary") or "",
                    baseline.get("summary_text") or baseline.get("topic_summary") or "",
                )
                semantic_internal_similarities.append(similarity)
                current_entropy = _entropy([str(value) for value in current.get("top_values", [])])
                baseline_entropy = _entropy([str(value) for value in baseline.get("top_values", [])])
                categorical_entropy_ratios.append(current_entropy / max(baseline_entropy, 1e-6))
                per_column_drifts.append(1.0 - similarity)

        for column_name in common_external:
            current = current_columns[column_name]
            baseline = external_columns[column_name]
            if current["inferred_type"] == "numeric" and baseline["inferred_type"] == "numeric":
                baseline_std = max(abs(_safe_float(baseline.get("std"), 1.0)), 1e-6)
                mean_distance = abs(_safe_float(current.get("mean")) - _safe_float(baseline.get("mean"))) / baseline_std
                external_mean_distances.append(mean_distance)
            else:
                similarity = self._semantic_similarity(
                    current.get("summary_text") or current.get("topic_summary") or "",
                    baseline.get("summary_text") or baseline.get("topic_summary") or "",
                )
                semantic_external_similarities.append(similarity)

        anchor_violation_score = (
            sum(1 for anchor in anchors if anchor["status"] in {"violated", "weakened"}) / max(len(anchors), 1)
            if anchors
            else 0.0
        )
        minority_scale_ratio = scale_mismatches / max(
            1, sum(1 for column in current_profile.get("column_profiles", []) if column["inferred_type"] == "numeric")
        )
        current_embedding = current_profile.get("summary_embedding", [])
        internal_embedding = internal_baseline.get("summary_embedding", [])
        external_embedding = external_baseline.get("summary_embedding", [])
        internal_similarity = self._semantic_similarity(
            current_profile.get("summary_text", ""),
            internal_baseline.get("summary_text", ""),
            current_embedding,
            internal_embedding,
        )
        external_similarity = self._semantic_similarity(
            current_profile.get("summary_text", ""),
            external_baseline.get("summary_text", ""),
            current_embedding,
            external_embedding,
        )

        dataset_features = {
            "internal_mean_distance": float(np.mean(internal_mean_distances)) if internal_mean_distances else 0.0,
            "external_mean_distance": float(np.mean(external_mean_distances)) if external_mean_distances else 0.0,
            "text_embedding_distance": max(0.0, 1.0 - external_similarity),
            "anchor_violation_score": anchor_violation_score,
            "scale_mismatch_score": scale_mismatches / max(len(common_internal), 1),
            "numeric_std_ratio": float(np.mean(std_ratios)) if std_ratios else 0.0,
            "categorical_entropy_ratio": float(np.mean(categorical_entropy_ratios)) if categorical_entropy_ratios else 1.0,
            "minority_scale_ratio": minority_scale_ratio,
            "text_similarity_to_internal": internal_similarity,
            "text_similarity_to_external": external_similarity,
            "semantic_coherence_score": max(0.0, 1.0 - anchor_violation_score),
            "column_count_diff": abs(current_profile.get("column_count", 0) - internal_baseline.get("column_count", 0)),
            "new_column_ratio": len(set(current_columns) - set(internal_columns)) / max(len(current_columns), 1),
            "missing_column_ratio": len(set(internal_columns) - set(current_columns)) / max(len(internal_columns), 1),
            "max_column_drift": max(per_column_drifts) if per_column_drifts else 0.0,
        }

        explanations = [
            f"Internal alignment score: {(1 - min(dataset_features['internal_mean_distance'], 1)) * 100:.1f}%",
            f"External alignment score: {dataset_features['text_similarity_to_external'] * 100:.1f}%",
            f"Relational integrity: {(1 - dataset_features['anchor_violation_score']) * 100:.1f}%",
        ]
        return dataset_features, explanations

    # ------------------------------------------------------------------
    # Row-level scoring
    # ------------------------------------------------------------------
    def _build_row_classifications(
        self,
        data: pd.DataFrame,
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
        anchors: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        internal_columns = {col["column_name"]: col for col in internal_baseline.get("column_profiles", [])}
        external_columns = {col["column_name"]: col for col in external_baseline.get("column_profiles", [])}
        text_columns = [col["column_name"] for col in current_profile.get("column_profiles", []) if col["inferred_type"] != "numeric"]
        row_results: List[Dict[str, Any]] = []

        for index, row in data.iterrows():
            row_dict = row.to_dict()
            affected_columns: List[str] = []
            numeric_distances_internal: List[float] = []
            numeric_distances_external: List[float] = []

            for column in current_profile.get("column_profiles", []):
                column_name = column["column_name"]
                current_value = row_dict.get(column_name)
                if column["inferred_type"] != "numeric":
                    continue
                try:
                    numeric_value = float(current_value)
                except Exception:
                    continue
                internal_col = internal_columns.get(column_name)
                external_col = external_columns.get(column_name)
                if internal_col:
                    baseline_std = max(abs(_safe_float(internal_col.get("std"), 1.0)), 1e-6)
                    sigma = abs(numeric_value - _safe_float(internal_col.get("mean"))) / baseline_std
                    numeric_distances_internal.append(sigma)
                    if sigma > 2.5:
                        affected_columns.append(column_name)
                if external_col:
                    baseline_std = max(abs(_safe_float(external_col.get("std"), 1.0)), 1e-6)
                    sigma = abs(numeric_value - _safe_float(external_col.get("mean"))) / baseline_std
                    numeric_distances_external.append(sigma)

            row_text = " ".join(str(row_dict.get(column, "")).strip() for column in text_columns if str(row_dict.get(column, "")).strip())
            internal_similarity = self._semantic_similarity(row_text, internal_baseline.get("summary_text", ""))
            external_similarity = self._semantic_similarity(row_text, external_baseline.get("summary_text", ""))

            row_features = {
                "internal_mean_distance": float(np.mean(numeric_distances_internal)) if numeric_distances_internal else 0.0,
                "external_mean_distance": float(np.mean(numeric_distances_external)) if numeric_distances_external else 0.0,
                "text_embedding_distance": max(0.0, 1.0 - external_similarity),
                "anchor_violation_score": self._row_anchor_violation_score(row_dict, anchors),
                "scale_mismatch_score": 0.0,
                "numeric_std_ratio": 0.0,
                "categorical_entropy_ratio": 1.0,
                "minority_scale_ratio": 0.0,
                "text_similarity_to_internal": internal_similarity,
                "text_similarity_to_external": external_similarity,
                "semantic_coherence_score": max(0.0, 1.0 - self._row_anchor_violation_score(row_dict, anchors)),
                "column_count_diff": 0.0,
                "new_column_ratio": 0.0,
                "missing_column_ratio": 0.0,
                "max_column_drift": max(numeric_distances_internal) / 4.0 if numeric_distances_internal else 0.0,
            }
            scored = self.scoring_agent.score(row_features)
            label = scored.get("label", "SAFE")
            confidence = float(scored.get("confidence", 0.5))
            reasons: List[str] = []
            if numeric_distances_internal and max(numeric_distances_internal) > 2.5:
                reasons.append("Numeric values moved away from the internal baseline.")
            if external_similarity < 0.55:
                reasons.append("Row semantics do not match the external benchmark profile.")
            if row_features["anchor_violation_score"] > 0.35:
                reasons.append("Important cross-column relationships are weakened in this row.")
            if not reasons:
                reasons.append("Row remains aligned with the internal and external baselines.")

            row_results.append(
                {
                    "row_id": index,
                    "row_index": index,
                    "status": label,
                    "confidence": confidence,
                    "affected_columns": sorted(set(affected_columns)),
                    "reasons": reasons,
                    "internal_similarity": max(0.0, 1.0 - min(float(np.mean(numeric_distances_internal)) if numeric_distances_internal else 0.0, 1.0)),
                    "external_similarity": external_similarity,
                    "internal_status": "Aligned" if (not numeric_distances_internal or np.mean(numeric_distances_internal) < 1.5) else "Drifted",
                    "external_status": "Aligned" if external_similarity >= 0.6 else "Outlier",
                }
            )

        return row_results

    def _run_cross_modal_checks(
        self,
        data: pd.DataFrame,
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
        anchors: List[Dict[str, Any]],
        row_classifications: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if data.empty:
            return {
                "enabled": False,
                "explanation": "Cross-modal integrity check is waiting for uploaded rows.",
                "baseline_examples": [],
                "rows": [],
                "summary": {"SAFE": 0, "CONDITIONAL": 0, "QUARANTINED": 0, "pending_review": 0},
                "human_review_queue": [],
            }

        baseline_examples = self._select_clean_baseline_examples(data, row_classifications)
        suspicious_rows = self._select_cross_modal_candidate_rows(data, row_classifications)
        baseline_rules = [
            anchor.get("description") or anchor.get("baseline_rule") or anchor.get("anchor_id")
            for anchor in anchors[:6]
            if (anchor.get("description") or anchor.get("baseline_rule") or anchor.get("anchor_id"))
        ]

        results: List[Dict[str, Any]] = []
        llm_client = getattr(self.anchor_agent, "_llm_client", None)
        for candidate in suspicious_rows:
            row_id = int(candidate["row_id"])
            row = data.iloc[row_id].to_dict()
            if llm_client:
                result = self._evaluate_cross_modal_row_llm(
                    llm_client,
                    row_id,
                    row,
                    baseline_examples,
                    baseline_rules,
                    current_profile,
                    internal_baseline,
                    external_baseline,
                )
            else:
                result = self._evaluate_cross_modal_row_fallback(
                    row_id,
                    row,
                    candidate,
                    anchors,
                    current_profile,
                )
            results.append(result)

        summary = {
            "SAFE": sum(1 for row in results if row["status"] == "SAFE"),
            "CONDITIONAL": sum(1 for row in results if row["status"] == "CONDITIONAL"),
            "QUARANTINED": sum(1 for row in results if row["status"] == "QUARANTINED"),
        }
        human_review_queue = [
            {
                **row,
                "review_status": "Pending Review",
                "review_prompt": "Does this row still make business sense across its values?",
            }
            for row in results
            if row["status"] != "SAFE" or row["confidence"] < 0.8
        ]
        summary["pending_review"] = len(human_review_queue)

        return {
            "enabled": True,
            "explanation": (
                "Cross-modal integrity checks whether numeric, text, and categorical fields still make sense together. "
                "A row can look valid column by column, but still be risky if the relationship between fields is broken."
            ),
            "baseline_examples": baseline_examples,
            "baseline_rules": baseline_rules,
            "rows": results,
            "summary": summary,
            "human_loop_policy": {
                "safe": "Auto-pass",
                "conditional": "Ask human to confirm whether the unusual relationship still makes business sense.",
                "quarantined": "Block by default and require human override to continue.",
            },
            "human_review_queue": human_review_queue,
        }

    def _row_anchor_violation_score(self, row: Dict[str, Any], anchors: List[Dict[str, Any]]) -> float:
        if not anchors:
            return 0.0
        violations = 0
        total = 0
        for anchor in anchors:
            left = anchor.get("column_1")
            right = anchor.get("column_2")
            if not left or not right or left not in row or right not in row:
                continue
            total += 1
            left_value = row.get(left)
            right_value = str(row.get(right, "")).lower()
            if isinstance(left_value, (int, float)) and right_value:
                if left_value and left_value > 0 and any(token in right_value for token in ("broken", "damaged", "cheap", "fault")):
                    violations += 1
            elif str(left_value).strip() and not right_value:
                violations += 1
        return violations / max(total, 1)

    def _select_clean_baseline_examples(
        self,
        data: pd.DataFrame,
        row_classifications: List[Dict[str, Any]],
        max_examples: int = 5,
    ) -> List[Dict[str, Any]]:
        if data.empty:
            return []
        scored_rows = sorted(
            row_classifications,
            key=lambda row: (
                0 if row.get("status") == "SAFE" else 1,
                len(row.get("affected_columns", [])),
                -float(row.get("confidence", 0.0)),
            ),
        )
        examples: List[Dict[str, Any]] = []
        for row_meta in scored_rows:
            row_id = int(row_meta["row_id"])
            preview = self._compact_row_preview(data.iloc[row_id].to_dict())
            if preview:
                examples.append({"row_id": row_id, "values": preview})
            if len(examples) >= max_examples:
                break
        return examples

    def _select_cross_modal_candidate_rows(
        self,
        data: pd.DataFrame,
        row_classifications: List[Dict[str, Any]],
        max_rows: int = 15,
    ) -> List[Dict[str, Any]]:
        if data.empty:
            return []
        ranked = sorted(
            row_classifications,
            key=lambda row: (
                0 if row.get("status") == "QUARANTINED" else 1 if row.get("status") == "CONDITIONAL" else 2,
                -len(row.get("affected_columns", [])),
                -float(row.get("confidence", 0.0)),
            ),
        )
        chosen = ranked[:max_rows]
        if not chosen:
            chosen = row_classifications[: min(len(row_classifications), max_rows)]
        return chosen

    def _evaluate_cross_modal_row_llm(
        self,
        llm_client: Any,
        row_id: int,
        row: Dict[str, Any],
        baseline_examples: List[Dict[str, Any]],
        baseline_rules: List[str],
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            prompt = self._build_cross_modal_prompt(
                baseline_examples,
                baseline_rules,
                row,
                current_profile,
                internal_baseline,
                external_baseline,
            )
            response = llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a FeatureOps cross-modal integrity checker. "
                            "Return JSON only with keys: status, relational_drift, confidence, "
                            "broken_relationship, reason, recommended_action."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=250,
            )
            content = (response.choices[0].message.content or "").strip()
            parsed = json.loads(content.replace("```json", "").replace("```", "").strip())
            status = str(parsed.get("status") or "CONDITIONAL").upper()
            if status not in {"SAFE", "CONDITIONAL", "QUARANTINED"}:
                status = "CONDITIONAL"
            confidence = max(0.0, min(1.0, _safe_float(parsed.get("confidence"), 0.72)))
            return {
                "row_id": row_id,
                "status": status,
                "relational_drift": bool(parsed.get("relational_drift", status != "SAFE")),
                "confidence": confidence,
                "broken_relationship": parsed.get("broken_relationship") or "No major relationship break detected.",
                "reason": parsed.get("reason") or "LLM cross-modal review completed.",
                "recommended_action": parsed.get("recommended_action") or "Review this row before release.",
                "row_preview": self._compact_row_preview(row),
            }
        except Exception as exc:
            logger.debug("Cross-modal LLM check failed for row %s: %s", row_id, exc)
            fallback_meta = {
                "row_id": row_id,
                "status": "CONDITIONAL",
                "confidence": 0.68,
                "affected_columns": [],
                "reasons": ["Cross-modal LLM fallback used."],
            }
            return self._evaluate_cross_modal_row_fallback(
                row_id,
                row,
                fallback_meta,
                [],
                current_profile,
            )

    def _evaluate_cross_modal_row_fallback(
        self,
        row_id: int,
        row: Dict[str, Any],
        row_meta: Dict[str, Any],
        anchors: List[Dict[str, Any]],
        current_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        preview = self._compact_row_preview(row)
        numeric_columns = [col["column_name"] for col in current_profile.get("column_profiles", []) if col["inferred_type"] == "numeric"]
        text_columns = [col["column_name"] for col in current_profile.get("column_profiles", []) if col["inferred_type"] != "numeric"]
        high_numeric: List[str] = []
        low_value_text: List[str] = []
        for column in numeric_columns:
            value = row.get(column)
            try:
                numeric = float(value)
            except Exception:
                continue
            if numeric >= 1000 or numeric >= 100:
                high_numeric.append(column)
        for column in text_columns:
            text = str(row.get(column, "")).strip().lower()
            if any(token in text for token in ("broken", "damaged", "cheap", "fault", "error", "negative", "failed")):
                low_value_text.append(column)
        anchor_violation = self._row_anchor_violation_score(row, anchors)
        if high_numeric and low_value_text:
            status = "QUARANTINED"
            reason = (
                f"High-value numeric fields ({', '.join(high_numeric[:2])}) conflict with low-value text cues "
                f"in {', '.join(low_value_text[:2])}."
            )
            broken_relationship = "price-description or score-status mismatch"
            recommended_action = "Review both the numeric value and the descriptive fields before AI use."
            confidence = 0.9
        elif anchor_violation > 0.35 or row_meta.get("status") == "CONDITIONAL":
            status = "CONDITIONAL"
            reason = "The row is unusual across multiple fields and should be reviewed by a human."
            broken_relationship = "cross-column relationship shift"
            recommended_action = "Ask a reviewer whether this still makes business sense."
            confidence = 0.76
        else:
            status = "SAFE"
            reason = "Numeric, text, and categorical values still look consistent together."
            broken_relationship = "none"
            recommended_action = "No action needed."
            confidence = 0.82
        return {
            "row_id": row_id,
            "status": status,
            "relational_drift": status != "SAFE",
            "confidence": confidence,
            "broken_relationship": broken_relationship,
            "reason": reason,
            "recommended_action": recommended_action,
            "row_preview": preview,
        }

    def _build_cross_modal_prompt(
        self,
        baseline_examples: List[Dict[str, Any]],
        baseline_rules: List[str],
        row: Dict[str, Any],
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
    ) -> str:
        baseline_examples_json = json.dumps(baseline_examples[:5], ensure_ascii=False, indent=2)
        rule_lines = "\n".join(f"- {rule}" for rule in baseline_rules[:6]) or "- Numeric values should logically match related text and category fields."
        new_row_json = json.dumps(self._compact_row_preview(row), ensure_ascii=False, indent=2)
        return (
            "Valid baseline examples:\n"
            f"{baseline_examples_json}\n\n"
            "Rules learned from baseline:\n"
            f"{rule_lines}\n\n"
            f"Internal baseline summary: {internal_baseline.get('summary_text', '')}\n"
            f"External baseline summary: {external_baseline.get('summary_text', '')}\n"
            f"Current dataset summary: {current_profile.get('summary_text', '')}\n\n"
            "Now evaluate this new row:\n"
            f"{new_row_json}\n\n"
            "Decision guide:\n"
            "SAFE = values match baseline relationships.\n"
            "CONDITIONAL = unusual but logically explainable.\n"
            "QUARANTINED = relationship is broken and unsafe for AI use."
        )

    def _compact_row_preview(self, row: Dict[str, Any], max_fields: int = 6) -> Dict[str, Any]:
        preview: Dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            preview[key] = text if len(text) <= 80 else f"{text[:77]}..."
            if len(preview) >= max_fields:
                break
        return preview

    # ------------------------------------------------------------------
    # Derived UI structures
    # ------------------------------------------------------------------
    def _build_triage_matrix(self, row_classifications: List[Dict[str, Any]]) -> Dict[str, Any]:
        def _cell(internal: str, external: str, decision: str, rows: List[Dict[str, Any]], description: str) -> Dict[str, Any]:
            return {
                "internal": internal,
                "external": external,
                "decision": decision,
                "row_count": len(rows),
                "percentage": (len(rows) / max(len(row_classifications), 1)) * 100,
                "description": description,
                "reasoning": list({reason for row in rows for reason in row.get("reasons", [])})[:4],
            }

        safe_rows = [row for row in row_classifications if row["status"] == "SAFE"]
        conditional_rows = [row for row in row_classifications if row["status"] == "CONDITIONAL"]
        quarantined_rows = [row for row in row_classifications if row["status"] == "QUARANTINED"]
        external_outlier_rows = [row for row in safe_rows if row["external_status"] == "Outlier"]

        cells = [
            _cell("Aligned", "Aligned", "SAFE", [row for row in safe_rows if row["external_status"] == "Aligned"], "Stable internally and externally."),
            _cell("Aligned", "Outlier", "CONDITIONAL", external_outlier_rows, "Internally stable but externally out of market range."),
            _cell("Drifted", "Aligned", "CONDITIONAL", conditional_rows, "Internal history shifted, but market still supports it."),
            _cell("Drifted", "Outlier", "QUARANTINED", quarantined_rows, "Neither baseline supports the new behavior."),
        ]
        return {"cells": cells}

    def _analyze_column_drifts(
        self,
        current_profile: Dict[str, Any],
        internal_baseline: Dict[str, Any],
        external_baseline: Dict[str, Any],
        anchors: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        internal_columns = {col["column_name"]: col for col in internal_baseline.get("column_profiles", [])}
        external_columns = {col["column_name"]: col for col in external_baseline.get("column_profiles", [])}
        anchored_columns = {anchor["column_1"] for anchor in anchors} | {anchor["column_2"] for anchor in anchors}
        drifts: List[Dict[str, Any]] = []

        for column in current_profile.get("column_profiles", []):
            column_name = column["column_name"]
            internal = internal_columns.get(column_name, {})
            external = external_columns.get(column_name, {})
            drift_type = "numeric" if column["inferred_type"] == "numeric" else "text"
            baseline_stats: Dict[str, Any] = {}
            current_stats: Dict[str, Any] = {}
            reason = "Column remains aligned with learned baselines."
            severity = "none"
            impact = "Low release risk."
            recommendation = "No action needed."

            if drift_type == "numeric":
                baseline_mean = _safe_float(internal.get("mean"))
                baseline_std = max(abs(_safe_float(internal.get("std"), 1.0)), 1e-6)
                current_mean = _safe_float(column.get("mean"))
                current_std = _safe_float(column.get("std"))
                sigma = abs(current_mean - baseline_mean) / baseline_std
                external_mean = _safe_float(external.get("mean"))
                external_std = max(abs(_safe_float(external.get("std"), 1.0)), 1e-6)
                external_sigma = abs(current_mean - external_mean) / external_std
                baseline_stats = {"mean": baseline_mean, "std": _safe_float(internal.get("std")), "scale": internal.get("scale_pattern")}
                current_stats = {"mean": current_mean, "std": current_std, "scale": column.get("scale_pattern")}
                if sigma > 3.5 and external_sigma > 2.5:
                    severity = "high"
                    reason = "Numeric scale moved away from both the internal and external baselines."
                    impact = "High risk of semantic drift."
                    recommendation = "Quarantine until the scoring semantics are reviewed."
                elif sigma > 2.0:
                    severity = "moderate"
                    reason = "Numeric values drifted from internal history but remain closer to the external benchmark."
                    impact = "Potential valid market or operational shift."
                    recommendation = "Review and approve conditionally if the change is expected."
                elif sigma > 1.0:
                    severity = "low"
                    reason = "Small numeric movement detected against the internal baseline."
                    impact = "Low release risk."
                    recommendation = "Monitor in the next version."
            else:
                internal_similarity = self._semantic_similarity(
                    column.get("summary_text") or column.get("topic_summary") or "",
                    internal.get("summary_text") or internal.get("topic_summary") or "",
                )
                external_similarity = self._semantic_similarity(
                    column.get("summary_text") or column.get("topic_summary") or "",
                    external.get("summary_text") or external.get("topic_summary") or "",
                )
                baseline_stats = {
                    "internal_similarity": internal_similarity,
                    "external_similarity": external_similarity,
                    "baseline_terms": internal.get("top_values", [])[:5],
                }
                current_stats = {"current_terms": column.get("top_values", [])[:5]}
                if internal_similarity < 0.5 and external_similarity < 0.5:
                    severity = "high"
                    reason = "Text semantics no longer match either baseline profile."
                    impact = "Meaning changed enough to affect downstream recommendations."
                    recommendation = "Review mappings and quarantine until corrected."
                elif internal_similarity < 0.65:
                    severity = "moderate"
                    reason = "Text semantics drifted from internal history but still resemble the external benchmark."
                    impact = "Possible valid market shift."
                    recommendation = "Review semantically and release conditionally."
                elif internal_similarity < 0.8:
                    severity = "low"
                    reason = "Minor wording drift detected."
                    impact = "Low release risk."
                    recommendation = "Track but allow."

            if column_name in anchored_columns:
                weakened = [anchor for anchor in anchors if column_name in {anchor["column_1"], anchor["column_2"]} and anchor["status"] != "valid"]
                if weakened and severity in {"none", "low"}:
                    severity = "moderate" if any(anchor["status"] == "weakened" for anchor in weakened) else "high"
                    reason = "Cross-column relationship drift was detected for this field."
                    impact = "Relational meaning may have decoupled from its paired column."
                    recommendation = "Inspect relational anchor evidence before release."
                    drift_type = "relational"

            drifts.append(
                {
                    "column_name": column_name,
                    "drift_type": drift_type if drift_type in {"numeric", "text", "relational"} else "categorical",
                    "severity": severity,
                    "reason": reason,
                    "baseline_stats": baseline_stats,
                    "current_stats": current_stats,
                    "impact": impact,
                    "recommendation": recommendation,
                }
            )

        return drifts

    def _build_reasons(
        self,
        final_label: str,
        features: Dict[str, float],
        feature_explanations: List[str],
        anchors: List[Dict[str, Any]],
        row_classifications: List[Dict[str, Any]],
    ) -> List[str]:
        reasons = list(feature_explanations)
        weakened = [anchor for anchor in anchors if anchor["status"] == "weakened"]
        violated = [anchor for anchor in anchors if anchor["status"] == "violated"]
        if violated:
            reasons.append(
                f"{len(violated)} relational anchor(s) are broken, including {', '.join(anchor['anchor_id'] for anchor in violated[:2])}."
            )
        elif weakened:
            reasons.append(
                f"{len(weakened)} relational anchor(s) weakened, indicating cross-column semantics are changing."
            )
        quarantined_rows = sum(1 for row in row_classifications if row["status"] == "QUARANTINED")
        conditional_rows = sum(1 for row in row_classifications if row["status"] == "CONDITIONAL")
        total_rows = max(len(row_classifications), 1)
        if final_label == "QUARANTINED":
            reasons.append(f"{quarantined_rows} of {total_rows} rows are learned as high-risk drift.")
        elif final_label == "CONDITIONAL":
            reasons.append(f"{conditional_rows} of {total_rows} rows align with the market baseline better than internal history.")
        else:
            reasons.append("Learned scorer sees the upload as stable against both baselines.")
        return reasons

    def _severity_from_label(self, final_label: str, score: float) -> str:
        if final_label == "QUARANTINED" or score >= 0.7:
            return "high"
        if final_label == "CONDITIONAL" or score >= 0.35:
            return "moderate"
        return "low"

    # ------------------------------------------------------------------
    # Similarity + persistence
    # ------------------------------------------------------------------
    def _semantic_similarity(
        self,
        left_text: str,
        right_text: str,
        left_embedding: Optional[List[float]] = None,
        right_embedding: Optional[List[float]] = None,
    ) -> float:
        if left_embedding and right_embedding:
            similarity = _cosine_similarity(left_embedding, right_embedding)
            if similarity > 0:
                return similarity
        if not left_text and not right_text:
            return 1.0
        if not left_text or not right_text:
            return 0.0
        left_embedding = self.profiler._embed_text(left_text)  # type: ignore[attr-defined]
        right_embedding = self.profiler._embed_text(right_text)  # type: ignore[attr-defined]
        return _cosine_similarity(left_embedding, right_embedding)

    def _save_analysis(self, analysis: DriftAnalysis) -> None:
        result_path = self.results_dir / f"{analysis.drift_run_id}.json"
        result_path.write_text(json.dumps(analysis.to_dict(), indent=2), encoding="utf-8")
