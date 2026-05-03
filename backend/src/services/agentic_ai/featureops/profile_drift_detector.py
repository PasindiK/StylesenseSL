from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency in local dev
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return default
        return numeric
    except Exception:
        return default


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _tokenize(text: str) -> List[str]:
    return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        size = min(len(left), len(right))
        left = left[:size]
        right = right[:size]
    left_vector = np.asarray(left, dtype=float)
    right_vector = np.asarray(right, dtype=float)
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(left_vector, right_vector) / denominator)


@dataclass
class ProfiledDriftResult:
    drift_run_id: str
    timestamp: str
    dataset_version_a: str
    dataset_version_b: Optional[str]
    is_internal_drift: bool
    statistical_signals: List[Dict[str, Any]]
    semantic_signals: List[Dict[str, Any]]
    behavioral_signals: Optional[Dict[str, Any]]
    statistical_drift_score: float
    semantic_drift_score: float
    behavioral_drift_score: float
    internal_drift_score: float
    external_drift_score: float
    overall_drift_score: float
    severity: str
    drift_detected: bool
    reasons: List[str]
    final_label: str
    internal_status: str
    external_status: str
    row_results: List[Dict[str, Any]] = field(default_factory=list)
    profiles: Dict[str, Any] = field(default_factory=dict)
    human_reviewed: bool = False
    human_label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProfileDriftDetector:
    """Profile-based drift detector with twin baselines and agentic triage."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = self.state_dir / "drift_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.internal_baseline_path = self.state_dir / "internal_baseline.json"
        self.external_baseline_path = self.state_dir / "external_baseline.json"
        self.calibration_path = self.state_dir / "profile_calibration.json"
        self._llm_client = self._build_llm_client()
        self._embedding_cache: Dict[str, List[float]] = {}
        self.thresholds = self._load_thresholds()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect_internal_drift(self, data: pd.DataFrame, dataset_name: str) -> ProfiledDriftResult:
        current_profile = self.build_profile(data, dataset_name)
        internal_baseline = self._load_baseline("internal")
        external_baseline = self._load_baseline("external")

        if internal_baseline is None:
            self.save_baseline("internal", current_profile)
            internal_baseline = current_profile

        internal_compare = self._compare_profiles(current_profile, internal_baseline, baseline_label="internal")
        external_compare = self._compare_profiles(current_profile, external_baseline, baseline_label="external") if external_baseline else self._empty_compare()

        row_results = self._build_row_results(data, current_profile, internal_baseline, external_baseline)
        return self._build_result(
            dataset_name=dataset_name,
            current_profile=current_profile,
            internal_baseline=internal_baseline,
            external_baseline=external_baseline,
            internal_compare=internal_compare,
            external_compare=external_compare,
            row_results=row_results,
            is_internal=True,
        )

    def detect_external_drift(
        self,
        data_baseline: pd.DataFrame,
        data_current: pd.DataFrame,
        dataset_name: str,
        baseline_version: str,
        current_version: str,
        schema_info: Optional[Dict[str, Any]] = None,
    ) -> ProfiledDriftResult:
        baseline_profile = self.build_profile(data_baseline, f"{dataset_name}:{baseline_version}")
        current_profile = self.build_profile(data_current, f"{dataset_name}:{current_version}")

        self.save_baseline("external", baseline_profile)
        internal_baseline = self._load_baseline("internal") or current_profile

        internal_compare = self._compare_profiles(current_profile, internal_baseline, baseline_label="internal")
        external_compare = self._compare_profiles(current_profile, baseline_profile, baseline_label="external")
        row_results = self._build_row_results(data_current, current_profile, internal_baseline, baseline_profile)

        return self._build_result(
            dataset_name=dataset_name,
            current_profile=current_profile,
            internal_baseline=internal_baseline,
            external_baseline=baseline_profile,
            internal_compare=internal_compare,
            external_compare=external_compare,
            row_results=row_results,
            is_internal=False,
        )

    def set_baseline(self, scope: str, data: pd.DataFrame, dataset_name: str) -> Dict[str, Any]:
        profile = self.build_profile(data, dataset_name)
        self.save_baseline(scope, profile)
        return {
            "status": "ok",
            "scope": scope,
            "dataset_name": dataset_name,
            "profile": profile,
        }

    def get_result(self, run_id: str) -> Optional[ProfiledDriftResult]:
        result_path = self.results_dir / f"{run_id}.json"
        if not result_path.exists():
            return None
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return self._dict_to_result(data)

    def label_result(self, run_id: str, label: str) -> Dict[str, Any]:
        result = self.get_result(run_id)
        if not result:
            raise ValueError(f"Drift result {run_id} not found")
        result.human_reviewed = True
        result.human_label = label
        self._save_result(result)
        return {"status": "ok", "message": f"Labeled result {run_id} as '{label}'"}

    def train(self, labeled_drift_runs: List[Tuple[Dict[str, Any], str] | Dict[str, Any]]) -> Dict[str, Any]:
        samples = []
        for item in labeled_drift_runs:
            if isinstance(item, tuple) and len(item) == 2:
                drift_result, label = item
            else:
                drift_result = item.get("drift_result", {}) if isinstance(item, dict) else {}
                label = item.get("label") if isinstance(item, dict) else None
            if not drift_result or not label:
                continue
            samples.append((drift_result, str(label)))

        if not samples:
            raise ValueError("No valid labeled drift runs provided")

        internal_scores = [float(sample[0].get("internal_drift_score", 0.0)) for sample in samples if sample[1] != "low"]
        external_scores = [float(sample[0].get("semantic_drift_score", 0.0)) for sample in samples if sample[1] in {"moderate", "high"}]
        safe_similarity = [float(sample[0].get("semantic_drift_score", 0.0)) for sample in samples if sample[1] == "low"]

        if internal_scores:
            learned_sigma_threshold = min(5.0, max(2.0, float(np.mean(internal_scores) * 6.0 or 3.0)))
            self.thresholds["internal_sigma_threshold"] = learned_sigma_threshold
        if external_scores:
            learned_semantic_threshold = max(0.55, min(0.9, 1.0 - float(np.mean(external_scores))))
            self.thresholds["semantic_threshold"] = learned_semantic_threshold
        if safe_similarity:
            self.thresholds["safe_similarity_floor"] = max(0.5, min(0.9, 1.0 - float(np.mean(safe_similarity))))

        self._save_thresholds()
        return {
            "trained_samples": len(samples),
            "thresholds": self.thresholds,
        }

    def get_training_stats(self) -> Dict[str, Any]:
        return {
            "thresholds": self.thresholds,
            "baseline_files": {
                "internal": str(self.internal_baseline_path),
                "external": str(self.external_baseline_path),
            },
        }

    # ------------------------------------------------------------------
    # Profile building
    # ------------------------------------------------------------------
    def build_profile(self, data: pd.DataFrame, dataset_name: str) -> Dict[str, Any]:
        profile_columns: List[Dict[str, Any]] = []
        numeric_column_names: List[str] = []

        for column_name in data.columns:
            series = data[column_name]
            column_profile = self._profile_column(series, column_name)
            profile_columns.append(column_profile)
            if column_profile["kind"] == "numeric":
                numeric_column_names.append(column_name)

        semantic_anchor = self._build_relational_anchor(data, numeric_column_names)
        summary_text = self._profile_summary_text(dataset_name, profile_columns, semantic_anchor)

        return {
            "dataset_name": dataset_name,
            "row_count": int(len(data)),
            "column_count": int(len(data.columns)),
            "column_profiles": profile_columns,
            "semantic_anchor": semantic_anchor,
            "summary_text": summary_text,
            "summary_embedding": self._embed_text(summary_text),
            "profile_signature": self._hash_text(summary_text),
            "built_at": datetime.utcnow().isoformat(),
        }

    def save_baseline(self, scope: str, profile: Dict[str, Any]) -> None:
        path = self.internal_baseline_path if scope == "internal" else self.external_baseline_path
        path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    def _load_baseline(self, scope: str) -> Optional[Dict[str, Any]]:
        path = self.internal_baseline_path if scope == "internal" else self.external_baseline_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Comparison and triage
    # ------------------------------------------------------------------
    def _compare_profiles(
        self,
        current_profile: Dict[str, Any],
        baseline_profile: Optional[Dict[str, Any]],
        baseline_label: str,
    ) -> Dict[str, Any]:
        if not baseline_profile:
            return self._empty_compare()

        current_columns = {col["column_name"]: col for col in current_profile.get("column_profiles", [])}
        baseline_columns = {col["column_name"]: col for col in baseline_profile.get("column_profiles", [])}
        common_columns = sorted(set(current_columns) & set(baseline_columns))

        numeric_signals: List[Dict[str, Any]] = []
        semantic_signals: List[Dict[str, Any]] = []
        reasons: List[str] = []
        drifted_numeric = 0
        drifted_semantic = 0
        max_sigma = 0.0
        min_similarity = 1.0

        for column_name in common_columns:
            current = current_columns[column_name]
            baseline = baseline_columns[column_name]
            kind = current.get("kind")

            if kind == "numeric" and baseline.get("kind") == "numeric":
                sigma_distance = self._sigma_distance(current, baseline)
                max_sigma = max(max_sigma, sigma_distance)
                internal_drift = sigma_distance > self.thresholds["internal_sigma_threshold"]
                if internal_drift:
                    drifted_numeric += 1
                    reasons.append(
                        f"Column '{column_name}' moved {sigma_distance:.2f} sigma from the {baseline_label} baseline."
                    )
                numeric_signals.append(
                    {
                        "column_name": column_name,
                        "kind": "numeric",
                        "baseline_mean": baseline.get("mean"),
                        "current_mean": current.get("mean"),
                        "baseline_std": baseline.get("std"),
                        "current_std": current.get("std"),
                        "sigma_distance": sigma_distance,
                        "internal_drift": internal_drift,
                        "threshold": self.thresholds["internal_sigma_threshold"],
                    }
                )
            else:
                baseline_summary = baseline.get("topic_summary") or baseline.get("summary_text") or self._column_text(baseline)
                current_summary = current.get("topic_summary") or current.get("summary_text") or self._column_text(current)
                similarity = self._semantic_similarity(current_summary, baseline_summary)
                min_similarity = min(min_similarity, similarity)
                semantic_drift = similarity < self.thresholds["semantic_threshold"]
                if semantic_drift:
                    drifted_semantic += 1
                    reasons.append(
                        f"Column '{column_name}' semantics changed (similarity {similarity:.2f} < {self.thresholds['semantic_threshold']:.2f})."
                    )
                semantic_signals.append(
                    {
                        "column_name": column_name,
                        "kind": kind,
                        "baseline_topic_summary": baseline.get("topic_summary"),
                        "current_topic_summary": current.get("topic_summary"),
                        "cosine_similarity": similarity,
                        "semantic_drift": semantic_drift,
                        "threshold": self.thresholds["semantic_threshold"],
                        "new_values": self._new_values(current, baseline),
                        "missing_values": self._missing_values(current, baseline),
                    }
                )

        new_columns = sorted(set(current_columns) - set(baseline_columns))
        missing_columns = sorted(set(baseline_columns) - set(current_columns))
        if new_columns:
            reasons.append(f"New columns appeared: {new_columns}")
        if missing_columns:
            reasons.append(f"Columns disappeared: {missing_columns}")

        internal_match = drifted_numeric == 0 and not new_columns and not missing_columns
        external_match = drifted_semantic == 0 and min_similarity >= self.thresholds["semantic_threshold"]

        internal_status = "Aligned" if internal_match else "Drifted"
        external_status = "Market-Aligned" if external_match else "Outlier"

        return {
            "numeric_signals": numeric_signals,
            "semantic_signals": semantic_signals,
            "reasons": reasons,
            "internal_match": internal_match,
            "external_match": external_match,
            "internal_status": internal_status,
            "external_status": external_status,
            "max_sigma": max_sigma,
            "min_similarity": min_similarity,
            "new_columns": new_columns,
            "missing_columns": missing_columns,
            "drifted_numeric": drifted_numeric,
            "drifted_semantic": drifted_semantic,
        }

    def _empty_compare(self) -> Dict[str, Any]:
        return {
            "numeric_signals": [],
            "semantic_signals": [],
            "reasons": [],
            "internal_match": True,
            "external_match": True,
            "internal_status": "Aligned",
            "external_status": "Market-Aligned",
            "max_sigma": 0.0,
            "min_similarity": 1.0,
            "new_columns": [],
            "missing_columns": [],
            "drifted_numeric": 0,
            "drifted_semantic": 0,
        }

    def _build_result(
        self,
        dataset_name: str,
        current_profile: Dict[str, Any],
        internal_baseline: Optional[Dict[str, Any]],
        external_baseline: Optional[Dict[str, Any]],
        internal_compare: Dict[str, Any],
        external_compare: Dict[str, Any],
        row_results: List[Dict[str, Any]],
        is_internal: bool,
    ) -> ProfiledDriftResult:
        internal_sigma = float(internal_compare.get("max_sigma", 0.0))
        external_similarity = float(external_compare.get("min_similarity", 1.0)) if external_baseline else 1.0

        statistical_score = min(1.0, internal_sigma / max(self.thresholds["internal_sigma_threshold"], 1e-6))
        semantic_score = max(0.0, 1.0 - external_similarity)
        behavioral_score = 0.0
        internal_score = statistical_score if is_internal else max(statistical_score, semantic_score * 0.6)
        external_score = semantic_score if external_baseline else 0.0
        overall_score = min(1.0, statistical_score * 0.55 + semantic_score * 0.45)

        internal_match = bool(internal_compare.get("internal_match", True))
        external_match = bool(external_compare.get("external_match", True))

        if internal_match and external_match:
            final_label = "SAFE"
        elif internal_match and not external_match:
            final_label = "SAFE"
        elif not internal_match and external_match:
            final_label = "CONDITIONAL"
        else:
            final_label = "QUARANTINED"

        severity = "low"
        if final_label == "QUARANTINED" or internal_sigma >= 4.0 or external_similarity < 0.6:
            severity = "high"
        elif final_label == "CONDITIONAL" or internal_sigma >= 3.0 or external_similarity < 0.75:
            severity = "moderate"

        reasons = list(internal_compare.get("reasons", [])) + list(external_compare.get("reasons", []))
        if final_label == "SAFE" and not external_match:
            reasons.append("Internal baseline matched, but the external market profile is misaligned.")
        elif final_label == "CONDITIONAL":
            reasons.append("Market shift detected: the current profile matches the external baseline better than the internal one.")
        elif final_label == "QUARANTINED":
            reasons.append("Current profile matches neither the internal nor the external baseline.")

        result = ProfiledDriftResult(
            drift_run_id=self._generate_run_id(),
            timestamp=datetime.utcnow().isoformat(),
            dataset_version_a=f"{dataset_name}:current",
            dataset_version_b=f"{dataset_name}:baseline",
            is_internal_drift=is_internal,
            statistical_signals=internal_compare.get("numeric_signals", []),
            semantic_signals=external_compare.get("semantic_signals", []),
            behavioral_signals=None,
            statistical_drift_score=statistical_score,
            semantic_drift_score=semantic_score,
            behavioral_drift_score=behavioral_score,
            internal_drift_score=internal_score,
            external_drift_score=external_score,
            overall_drift_score=overall_score,
            severity=severity,
            drift_detected=final_label != "SAFE",
            reasons=reasons,
            final_label=final_label,
            internal_status=str(internal_compare.get("internal_status", "Drifted")),
            external_status=str(external_compare.get("external_status", "Outlier")),
            row_results=row_results,
            profiles={
                "current_profile": self._profile_preview(current_profile),
                "internal_baseline": self._profile_preview(internal_baseline) if internal_baseline else None,
                "external_baseline": self._profile_preview(external_baseline) if external_baseline else None,
            },
        )
        self._save_result(result)
        return result

    # ------------------------------------------------------------------
    # Row-level enrichment
    # ------------------------------------------------------------------
    def _build_row_results(
        self,
        data: pd.DataFrame,
        current_profile: Dict[str, Any],
        internal_baseline: Optional[Dict[str, Any]],
        external_baseline: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if data.empty:
            return []

        internal_columns = {col["column_name"]: col for col in (internal_baseline or {}).get("column_profiles", [])}
        external_summary = (external_baseline or current_profile).get("summary_text") or ""
        internal_summary = (internal_baseline or current_profile).get("summary_text") or ""
        numeric_columns = [col["column_name"] for col in current_profile.get("column_profiles", []) if col["kind"] == "numeric"]
        text_columns = [col["column_name"] for col in current_profile.get("column_profiles", []) if col["kind"] != "numeric"]

        row_results: List[Dict[str, Any]] = []
        for index, row in data.iterrows():
            row_id = self._row_id_for(row, index)
            reasons: List[str] = []
            internal_trigger = False

            for column_name in numeric_columns:
                baseline = internal_columns.get(column_name)
                if not baseline:
                    continue
                value = _safe_float(row.get(column_name))
                if value is None:
                    continue
                sigma_distance = self._row_sigma_distance(value, baseline)
                if sigma_distance > self.thresholds["internal_sigma_threshold"]:
                    internal_trigger = True
                    reasons.append(f"{column_name} is {sigma_distance:.2f} sigma from the internal baseline.")

            row_text = self._row_text(row, text_columns)
            internal_similarity = self._semantic_similarity(row_text, internal_summary)
            external_similarity = self._semantic_similarity(row_text, external_summary)
            external_trigger = external_similarity < self.thresholds["semantic_threshold"]

            if internal_similarity < self.thresholds["semantic_threshold"]:
                internal_trigger = True
                reasons.append("Row semantics are less aligned with the internal profile than expected.")
            if external_trigger:
                reasons.append("Row semantics are not aligned with the external market profile.")

            if not reasons:
                reasons.append("Row matches both baseline profiles.")

            if not internal_trigger and external_trigger:
                final_label = "CONDITIONAL"
            elif internal_trigger and external_trigger:
                final_label = "QUARANTINED"
            else:
                final_label = "SAFE"

            row_results.append(
                {
                    "row_id": row_id,
                    "internal_status": "Drifted" if internal_trigger else "Aligned",
                    "external_status": "Outlier" if external_trigger else "Market-Aligned",
                    "final_label": final_label,
                    "reasoning": " ".join(reasons),
                    "internal_similarity": internal_similarity,
                    "external_similarity": external_similarity,
                }
            )

        return row_results

    @staticmethod
    def _row_id_for(row: pd.Series, index: Any) -> str:
        for candidate in ("row_id", "id", "record_id", "uuid"):
            if candidate in row.index and pd.notna(row.get(candidate)):
                return str(row.get(candidate))
        return str(index)

    @staticmethod
    def _row_text(row: pd.Series, text_columns: List[str]) -> str:
        parts: List[str] = []
        for column_name in text_columns:
            value = row.get(column_name)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            parts.append(_safe_text(value))
        return " ".join(part for part in parts if part)

    # ------------------------------------------------------------------
    # Column profiling helpers
    # ------------------------------------------------------------------
    def _profile_column(self, series: pd.Series, column_name: str) -> Dict[str, Any]:
        non_null = series.dropna()
        missing_rate = float(series.isna().mean()) if len(series) else 0.0
        inferred_kind = self._infer_kind(series, column_name)
        samples = [str(value) for value in non_null.astype(str).drop_duplicates().head(10).tolist()]

        profile: Dict[str, Any] = {
            "column_name": column_name,
            "kind": inferred_kind,
            "row_count": int(len(series)),
            "non_null_count": int(len(non_null)),
            "missing_rate": missing_rate,
            "unique_count": int(non_null.nunique(dropna=True)),
            "sample_values": samples,
            "semantic_signature": self._hash_text(f"{column_name}:{inferred_kind}:{'|'.join(samples)}"),
        }

        if inferred_kind == "numeric":
            numeric_series = pd.to_numeric(non_null, errors="coerce").dropna()
            std_value = _safe_float(numeric_series.std(ddof=0), 0.0) or 0.0
            profile.update(
                {
                    "mean": _safe_float(numeric_series.mean(), 0.0),
                    "std": std_value,
                    "min": _safe_float(numeric_series.min(), 0.0),
                    "max": _safe_float(numeric_series.max(), 0.0),
                    "median": _safe_float(numeric_series.median(), 0.0),
                    "p10": _safe_float(numeric_series.quantile(0.10), 0.0),
                    "p90": _safe_float(numeric_series.quantile(0.90), 0.0),
                    "topic_summary": f"Numeric feature with mean {float(numeric_series.mean()):.3f} and std {std_value:.3f}",
                    "summary_text": f"{column_name} is numeric. mean={float(numeric_series.mean()):.3f}, std={std_value:.3f}, min={float(numeric_series.min()):.3f}, max={float(numeric_series.max()):.3f}.",
                }
            )
        else:
            topic_summary = self._summarize_text_samples(column_name, samples)
            categorical_values = [str(value) for value in non_null.astype(str).value_counts().head(10).index.tolist()]
            profile.update(
                {
                    "topic_summary": topic_summary,
                    "summary_text": f"{column_name} is {inferred_kind}. {topic_summary}",
                    "top_values": categorical_values,
                    "new_values": categorical_values[:5],
                    "missing_values": [],
                }
            )

        return profile

    def _infer_kind(self, series: pd.Series, column_name: str) -> str:
        lower_name = column_name.lower()
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if any(token in lower_name for token in ("timestamp", "date", "time", "created_at", "updated_at")):
            return "datetime"
        sample = series.dropna().astype(str).head(20).tolist()
        if not sample:
            return "categorical"
        joined = " ".join(sample)
        avg_length = sum(len(item) for item in sample) / max(len(sample), 1)
        if avg_length >= 20 or any(char in joined for char in [".", ",", "?", "!", ";"]):
            return "text"
        return "categorical"

    def _summarize_text_samples(self, column_name: str, samples: List[str]) -> str:
        if not samples:
            return f"No values observed for {column_name}."

        if self._llm_client is not None:
            try:
                prompt = (
                    f"Summarize the meaning of the {column_name} column from the following 10 samples. "
                    "Return a short JSON object with keys summary and anchor. Keep it concise.\n\n"
                    + "\n".join(f"- {sample}" for sample in samples[:10])
                )
                response = self._llm_client.chat.completions.create(
                    model=os.getenv("OPENAI_PROFILE_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": "You summarize semantic dataset profiles for drift triage."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=180,
                )
                content = (response.choices[0].message.content or "").strip()
                parsed = json.loads(content)
                summary = str(parsed.get("summary") or content).strip()
                anchor = str(parsed.get("anchor") or "").strip()
                if anchor:
                    return f"{summary} Anchor: {anchor}."
                return summary
            except Exception as exc:
                logger.debug("LLM profile summary failed, falling back to heuristics: %s", exc)

        token_counts: Dict[str, int] = {}
        for sample in samples:
            for token in _tokenize(sample):
                token_counts[token] = token_counts.get(token, 0) + 1
        top_tokens = sorted(token_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        if not top_tokens:
            return f"Values in {column_name} look like short categorical labels."
        return "Top terms: " + ", ".join(token for token, _count in top_tokens)

    def _build_relational_anchor(self, data: pd.DataFrame, numeric_columns: List[str]) -> str:
        if len(numeric_columns) < 2:
            return "No strong relational anchor detected."

        best_pair: Tuple[str, str] | None = None
        best_corr = 0.0
        numeric_frame = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
        for i, left in enumerate(numeric_columns):
            for right in numeric_columns[i + 1 :]:
                pair = numeric_frame[[left, right]].dropna()
                if len(pair) < 3:
                    continue
                corr = abs(float(pair[left].corr(pair[right])))
                if np.isnan(corr):
                    continue
                if corr > best_corr:
                    best_corr = corr
                    best_pair = (left, right)

        if not best_pair or best_corr < 0.45:
            return "No strong relational anchor detected."
        left, right = best_pair
        return f"{left} and {right} are strongly related with correlation {best_corr:.2f}."

    def _profile_summary_text(self, dataset_name: str, columns: List[Dict[str, Any]], anchor: str) -> str:
        parts = [f"Dataset {dataset_name} has {len(columns)} columns."]
        for column in columns[:12]:
            parts.append(
                f"{column['column_name']} ({column['kind']}): {column.get('topic_summary') or column.get('summary_text') or 'No summary.'}"
            )
        parts.append(f"Anchor: {anchor}")
        return " ".join(parts)

    def _profile_preview(self, profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not profile:
            return None
        return {
            "dataset_name": profile.get("dataset_name"),
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "semantic_anchor": profile.get("semantic_anchor"),
            "profile_signature": profile.get("profile_signature"),
        }

    def _column_text(self, column_profile: Dict[str, Any]) -> str:
        return str(column_profile.get("summary_text") or column_profile.get("topic_summary") or "")

    def _new_values(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
        current_values = set(current.get("top_values") or current.get("sample_values") or [])
        baseline_values = set(baseline.get("top_values") or baseline.get("sample_values") or [])
        return sorted(current_values - baseline_values)[:10]

    def _missing_values(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
        current_values = set(current.get("top_values") or current.get("sample_values") or [])
        baseline_values = set(baseline.get("top_values") or baseline.get("sample_values") or [])
        return sorted(baseline_values - current_values)[:10]

    def _sigma_distance(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> float:
        current_mean = _safe_float(current.get("mean"), 0.0) or 0.0
        baseline_mean = _safe_float(baseline.get("mean"), 0.0) or 0.0
        baseline_std = _safe_float(baseline.get("std"), 0.0) or 0.0
        sigma = abs(current_mean - baseline_mean) / max(baseline_std, 1e-6)
        if math.isnan(sigma) or math.isinf(sigma):
            return 0.0
        return float(sigma)

    def _row_sigma_distance(self, value: float, baseline: Dict[str, Any]) -> float:
        baseline_mean = _safe_float(baseline.get("mean"), 0.0) or 0.0
        baseline_std = _safe_float(baseline.get("std"), 0.0) or 0.0
        sigma = abs(value - baseline_mean) / max(baseline_std, 1e-6)
        if math.isnan(sigma) or math.isinf(sigma):
            return 0.0
        return float(sigma)

    def _build_llm_client(self) -> Optional[OpenAI]:
        if OpenAI is None:
            return None
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
        if not api_key:
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception:
            return None

    def _embed_text(self, text: str) -> List[float]:
        cleaned = text.strip()
        if not cleaned:
            return [0.0] * 32
        if cleaned in self._embedding_cache:
            return self._embedding_cache[cleaned]
        if self._llm_client is not None:
            try:
                response = self._llm_client.embeddings.create(
                    model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                    input=cleaned,
                )
                vector = list(response.data[0].embedding)
                self._embedding_cache[cleaned] = vector
                return vector
            except Exception as exc:
                logger.debug("Embedding call failed, using fallback vectorizer: %s", exc)

        tokens = _tokenize(cleaned)
        vector = [0.0] * 32
        for token in tokens:
            bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % len(vector)
            vector[bucket] += 1.0
        norm = float(np.linalg.norm(np.asarray(vector, dtype=float)))
        if norm > 0:
            vector = [value / norm for value in vector]
        self._embedding_cache[cleaned] = vector
        return vector

    def _semantic_similarity(self, left: str, right: str) -> float:
        if not left and not right:
            return 1.0
        if not left or not right:
            return 0.0
        return _cosine_similarity(self._embed_text(left), self._embed_text(right))

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _generate_run_id(self) -> str:
        import uuid

        return str(uuid.uuid4())

    def _save_result(self, result: ProfiledDriftResult) -> None:
        result_path = self.results_dir / f"{result.drift_run_id}.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    def _dict_to_result(self, data: Dict[str, Any]) -> ProfiledDriftResult:
        return ProfiledDriftResult(
            drift_run_id=data.get("drift_run_id", self._generate_run_id()),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            dataset_version_a=data.get("dataset_version_a", ""),
            dataset_version_b=data.get("dataset_version_b"),
            is_internal_drift=bool(data.get("is_internal_drift", False)),
            statistical_signals=list(data.get("statistical_signals", [])),
            semantic_signals=list(data.get("semantic_signals", [])),
            behavioral_signals=data.get("behavioral_signals"),
            statistical_drift_score=float(data.get("statistical_drift_score", 0.0)),
            semantic_drift_score=float(data.get("semantic_drift_score", 0.0)),
            behavioral_drift_score=float(data.get("behavioral_drift_score", 0.0)),
            internal_drift_score=float(data.get("internal_drift_score", 0.0)),
            external_drift_score=float(data.get("external_drift_score", 0.0)),
            overall_drift_score=float(data.get("overall_drift_score", 0.0)),
            severity=data.get("severity", "low"),
            drift_detected=bool(data.get("drift_detected", False)),
            reasons=list(data.get("reasons", [])),
            final_label=data.get("final_label", "SAFE"),
            internal_status=data.get("internal_status", "Aligned"),
            external_status=data.get("external_status", "Market-Aligned"),
            row_results=list(data.get("row_results", [])),
            profiles=dict(data.get("profiles", {})),
            human_reviewed=bool(data.get("human_reviewed", False)),
            human_label=data.get("human_label"),
        )

    def _load_thresholds(self) -> Dict[str, float]:
        defaults = {
            "internal_sigma_threshold": 3.0,
            "semantic_threshold": 0.75,
            "safe_similarity_floor": 0.75,
        }
        if not self.calibration_path.exists():
            return defaults
        try:
            data = json.loads(self.calibration_path.read_text(encoding="utf-8"))
            for key, value in defaults.items():
                data[key] = float(data.get(key, value))
            return data
        except Exception:
            return defaults

    def _save_thresholds(self) -> None:
        self.calibration_path.write_text(json.dumps(self.thresholds, indent=2), encoding="utf-8")
