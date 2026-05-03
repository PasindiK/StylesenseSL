"""
ProfilerAgent: Phase 1 of Agentic Semantic FeatureOps

This agent is responsible for converting a raw dataset into a compact semantic profile.
The profile includes:
  - Numeric statistics (mean, std, min, max, percentiles)
  - Text summaries (topic summaries per column)
  - Text embeddings (semantic representations)
  - Scale patterns (detected via heuristics)
  - Relational anchors (discovered via correlation analysis)

Output: semantic_profile.json with schema matching the 14-point spec.

No dependencies on baselines or other agents in Phase 1.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    """Safely convert value to float, handling inf/nan."""
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
    """Safely convert value to string."""
    if value is None:
        return ""
    return str(value).strip()


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer for text analysis."""
    return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]


class ProfilerAgent:
    """
    Phase 1 Agent: Semantic Profile Builder
    
    Creates comprehensive semantic profiles of datasets without requiring baselines.
    Focus: profile.json generation with numeric stats, text summaries, and embeddings.
    """

    def __init__(self):
        """Initialize the profiler agent with LLM client if available."""
        self._llm_client = self._build_llm_client()
        self._embedding_cache: Dict[str, List[float]] = {}

    def build_profile(self, data: pd.DataFrame, dataset_name: str) -> Dict[str, Any]:
        """
        Main entry point: Convert dataset to semantic profile.
        
        Args:
            data: Input DataFrame
            dataset_name: Descriptive name for the dataset
            
        Returns:
            Dictionary containing semantic_profile.json structure
        """
        profile_columns: List[Dict[str, Any]] = []
        numeric_column_names: List[str] = []

        # Profile each column
        for column_name in data.columns:
            series = data[column_name]
            column_profile = self._profile_column(series, column_name)
            profile_columns.append(column_profile)
            if column_profile["kind"] == "numeric":
                numeric_column_names.append(column_name)

        # Discover relational anchors (numeric ↔ numeric correlations)
        relational_anchors = self._discover_relational_anchors(data, numeric_column_names, profile_columns)

        # Create dataset-level summary
        summary_text = self._profile_summary_text(dataset_name, profile_columns, relational_anchors)

        # Embed the summary for semantic comparison
        summary_embedding = self._embed_text(summary_text)

        # Build final profile JSON
        profile = {
            "metadata": {
                "dataset_name": dataset_name,
                "row_count": int(len(data)),
                "column_count": int(len(data.columns)),
                "built_at": datetime.utcnow().isoformat(),
                "profiler_version": "1.0",
            },
            "column_profiles": profile_columns,
            "relational_anchors": relational_anchors,
            "summary": {
                "text": summary_text,
                "embedding": summary_embedding,
                "signature": self._hash_text(summary_text),
            },
        }

        return profile

    # =========================================================================
    # Column Profiling
    # =========================================================================

    def _profile_column(self, series: pd.Series, column_name: str) -> Dict[str, Any]:
        """Profile a single column: type, statistics, samples, summary."""
        non_null = series.dropna()
        missing_rate = float(series.isna().mean()) if len(series) else 0.0
        inferred_kind = self._infer_kind(series, column_name)
        samples = [str(value) for value in non_null.astype(str).drop_duplicates().head(10).tolist()]

        base_profile: Dict[str, Any] = {
            "column_name": column_name,
            "kind": inferred_kind,
            "statistics": {
                "row_count": int(len(series)),
                "non_null_count": int(len(non_null)),
                "missing_rate": missing_rate,
                "unique_count": int(non_null.nunique(dropna=True)),
            },
            "samples": samples,
        }

        if inferred_kind == "numeric":
            numeric_series = pd.to_numeric(non_null, errors="coerce").dropna()
            std_value = _safe_float(numeric_series.std(ddof=0), 0.0) or 0.0
            scale_pattern = self._infer_scale_pattern(column_name, numeric_series)

            base_profile["numeric_stats"] = {
                "mean": _safe_float(numeric_series.mean(), 0.0),
                "std": std_value,
                "min": _safe_float(numeric_series.min(), 0.0),
                "max": _safe_float(numeric_series.max(), 0.0),
                "median": _safe_float(numeric_series.median(), 0.0),
                "p10": _safe_float(numeric_series.quantile(0.10), 0.0),
                "p90": _safe_float(numeric_series.quantile(0.90), 0.0),
            }
            base_profile["scale_pattern"] = scale_pattern
            topic_summary = f"Numeric feature with mean {float(numeric_series.mean()):.3f} and std {std_value:.3f}"

        else:
            # Text or categorical column
            topic_summary = self._summarize_text_samples(column_name, samples)
            categorical_values = [str(value) for value in non_null.astype(str).value_counts().head(10).index.tolist()]
            base_profile["categorical_stats"] = {
                "top_values": categorical_values,
                "cardinality": int(non_null.nunique(dropna=True)),
            }

        base_profile["topic_summary"] = topic_summary
        base_profile["summary_text"] = f"{column_name} is {inferred_kind}. {topic_summary}"

        return base_profile

    def _infer_kind(self, series: pd.Series, column_name: str) -> str:
        """Infer column type: numeric, datetime, categorical, or text."""
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

    def _infer_scale_pattern(self, column_name: str, numeric_series: pd.Series) -> str:
        """Detect scale pattern: currency, percentage, ratio, count, etc."""
        lower_name = column_name.lower()
        min_val = float(numeric_series.min())
        max_val = float(numeric_series.max())

        if any(word in lower_name for word in ("price", "cost", "amount", "salary")):
            return "currency"
        if any(word in lower_name for word in ("percent", "rate", "ratio")):
            return "percentage"
        if 0 <= min_val and max_val <= 100:
            return "percentage"
        if 0 <= min_val and max_val <= 1:
            return "normalized_score"
        if min_val >= 0 and max_val == int(max_val):
            return "count"
        return "continuous"

    def _summarize_text_samples(self, column_name: str, samples: List[str]) -> str:
        """Summarize column meaning from text samples using LLM or heuristics."""
        if not samples:
            return f"No values observed for {column_name}."

        # Try LLM if available
        if self._llm_client is not None:
            try:
                prompt = (
                    f"Summarize the semantic meaning of the {column_name} column from these 10 samples. "
                    "Return a concise summary (1-2 sentences). Be precise about domain and content.\n\n"
                    + "\n".join(f"- {sample}" for sample in samples[:10])
                )
                response = self._llm_client.chat.completions.create(
                    model=os.getenv("OPENAI_PROFILE_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": "You are a data profiler. Summarize dataset columns concisely."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=150,
                )
                content = (response.choices[0].message.content or "").strip()
                return content
            except Exception as exc:
                logger.debug("LLM summary failed, falling back to heuristics: %s", exc)

        # Fallback: heuristic token-based summary
        token_counts: Dict[str, int] = {}
        for sample in samples:
            for token in _tokenize(sample):
                token_counts[token] = token_counts.get(token, 0) + 1

        top_tokens = sorted(token_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        if not top_tokens:
            return f"Values in {column_name} appear to be categorical labels."

        return "Top terms: " + ", ".join(token for token, _count in top_tokens)

    # =========================================================================
    # Relational Anchor Discovery (Phase 1 → Phase 2 transition)
    # =========================================================================

    def _discover_relational_anchors(
        self, data: pd.DataFrame, numeric_columns: List[str], column_profiles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Discover relationships between columns.
        
        Phase 1: Uses correlation analysis for numeric-numeric relationships.
        Phase 2: Will use LLM to find numeric↔text relationships.
        Phase 3: Will use LLM to discover categorical↔text relationships.
        """
        anchors: List[Dict[str, Any]] = []

        # Phase 1 Only: Numeric-numeric correlations
        if len(numeric_columns) < 2:
            return anchors

        numeric_frame = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
        for i, left in enumerate(numeric_columns):
            for right in numeric_columns[i + 1 :]:
                pair = numeric_frame[[left, right]].dropna()
                if len(pair) < 3:
                    continue

                corr = abs(float(pair[left].corr(pair[right])))
                if np.isnan(corr) or corr < 0.5:
                    continue

                anchor: Dict[str, Any] = {
                    "anchor_id": f"{left}_{right}_correlation",
                    "type": "numeric_correlation",
                    "left_column": left,
                    "right_column": right,
                    "correlation_strength": round(corr, 3),
                    "baseline_rule": f"High values in {left} correlate with high values in {right} (r={corr:.2f}).",
                    "status": "discovered",
                }
                anchors.append(anchor)

        return anchors

    # =========================================================================
    # Text Embedding & Similarity
    # =========================================================================

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Embed text using OpenAI's text-embedding-3-small model."""
        if not text or not self._llm_client:
            return None

        if text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            response = self._llm_client.embeddings.create(
                model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                input=text,
            )
            embedding = response.data[0].embedding
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as exc:
            logger.debug("Embedding failed: %s", exc)
            return None

    # =========================================================================
    # Utilities
    # =========================================================================

    def _profile_summary_text(
        self, dataset_name: str, columns: List[Dict[str, Any]], anchors: List[Dict[str, Any]]
    ) -> str:
        """Generate human-readable dataset summary."""
        parts = [f"Dataset '{dataset_name}' contains {len(columns)} columns."]

        numeric_cols = [col for col in columns if col["kind"] == "numeric"]
        text_cols = [col for col in columns if col["kind"] in ("text", "categorical")]

        if numeric_cols:
            parts.append(f"Numeric columns: {', '.join(col['column_name'] for col in numeric_cols)}.")

        if text_cols:
            parts.append(f"Text/categorical columns: {', '.join(col['column_name'] for col in text_cols)}.")

        if anchors:
            anchor_summaries = []
            for anchor in anchors:
                if anchor["type"] == "numeric_correlation":
                    anchor_summaries.append(
                        f"{anchor['left_column']}↔{anchor['right_column']} (r={anchor['correlation_strength']})"
                    )
            if anchor_summaries:
                parts.append(f"Discovered relationships: {', '.join(anchor_summaries)}.")

        return " ".join(parts)

    @staticmethod
    def _hash_text(text: str) -> str:
        """Generate a hash signature of text."""
        import hashlib

        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @staticmethod
    def _build_llm_client() -> Optional[Any]:
        """Build OpenAI client if API key exists."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.info("OPENAI_API_KEY not set. Running ProfilerAgent in heuristic-only mode.")
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception as exc:
            logger.warning("Failed to initialize OpenAI client: %s", exc)
            return None


# ========================================================================
# Standalone CLI for testing
# ========================================================================

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python profiler_agent.py <csv_path> [dataset_name]")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    dataset_name = sys.argv[2] if len(sys.argv) > 2 else csv_path.stem

    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)

    print(f"[ProfilerAgent] Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"[ProfilerAgent] Rows: {len(df)}, Columns: {len(df.columns)}")

    profiler = ProfilerAgent()
    print("[ProfilerAgent] Building semantic profile...")
    profile = profiler.build_profile(df, dataset_name)

    output_path = csv_path.parent / f"{csv_path.stem}_semantic_profile.json"
    print(f"[ProfilerAgent] Saving profile to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(profile, f, indent=2)

    print(f"[ProfilerAgent] ✓ Profile built. {len(profile['column_profiles'])} columns profiled.")
    print(f"[ProfilerAgent] ✓ {len(profile['relational_anchors'])} relational anchors discovered.")
    print(f"[ProfilerAgent] ✓ Profile saved to {output_path}")
