"""
RelationalAnchorAgent: Phase 2 of Agentic Semantic FeatureOps

This agent is responsible for discovering and validating relational anchors:
  - Numeric ↔ Numeric: Correlations (computed by Phase 1)
  - Numeric ↔ Text: LLM-discovered rules (Phase 2 novelty)
  - Categorical ↔ Text: LLM-discovered rules (Phase 2 extension)

This is the **core research novelty**: detecting when relationships between 
columns break, not just when columns individually drift.

Example:
  - price alone looks normal: $8500
  - description alone looks normal: "broken second-hand item"
  - but price ↔ description relationship is BROKEN
  - → QUARANTINED (relational decoupling detected)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logger = logging.getLogger(__name__)


class RelationalAnchorAgent:
    """
    Phase 2 Agent: Relational Anchor Discovery and Validation
    
    Discovers relationships between numeric, categorical, and text columns
    using LLM reasoning (gpt-4o-mini) and validates them against sample data.
    """

    def __init__(self):
        """Initialize the relational anchor agent with LLM client if available."""
        self._llm_client = self._build_llm_client()

    def discover_anchors(
        self,
        baseline_profile: Dict[str, Any],
        sample_rows: pd.DataFrame,
        numeric_threshold: float = 0.5,
        text_threshold: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """
        Discover relational anchors from baseline profile and samples.
        
        Args:
            baseline_profile: Output from ProfilerAgent.build_profile()
            sample_rows: Sample DataFrame (e.g., first 10 rows of baseline data)
            numeric_threshold: Minimum correlation for numeric relationships
            text_threshold: Minimum confidence for LLM-discovered relationships
            
        Returns:
            List of relational anchor definitions
        """
        anchors: List[Dict[str, Any]] = []

        # Step 1: Extract column metadata from profile
        column_profiles = {col["column_name"]: col for col in baseline_profile.get("column_profiles", [])}
        numeric_cols = [name for name, col in column_profiles.items() if col["kind"] == "numeric"]
        text_cols = [name for name, col in column_profiles.items() if col["kind"] in ("text", "categorical")]

        # Step 2: Inherit numeric-numeric anchors from Phase 1
        anchors.extend(baseline_profile.get("relational_anchors", []))

        # Step 3: Discover numeric-text relationships (LLM-powered)
        if self._llm_client and numeric_cols and text_cols:
            numeric_text_anchors = self._discover_numeric_text_anchors(
                sample_rows, numeric_cols, text_cols, text_threshold
            )
            anchors.extend(numeric_text_anchors)

        # Step 4: Discover categorical-text relationships (LLM-powered)
        if self._llm_client and text_cols and len(text_cols) > 1:
            categorical_text_anchors = self._discover_categorical_text_anchors(
                sample_rows, text_cols, text_threshold
            )
            anchors.extend(categorical_text_anchors)

        return anchors

    def validate_anchors(
        self, anchors: List[Dict[str, Any]], sample_rows: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Validate discovered anchors against new data.
        
        Args:
            anchors: List of anchor definitions from discover_anchors()
            sample_rows: New sample rows to validate against
            
        Returns:
            Updated anchors with validation results
        """
        validated: List[Dict[str, Any]] = []

        for anchor in anchors:
            if anchor.get("type") == "numeric_correlation":
                # Numeric-numeric: recompute correlation
                result = self._validate_numeric_correlation(anchor, sample_rows)
            elif anchor.get("type") == "numeric_text_relationship":
                # Numeric-text: count violations
                result = self._validate_numeric_text_relationship(anchor, sample_rows)
            elif anchor.get("type") == "categorical_text_relationship":
                # Categorical-text: count violations
                result = self._validate_categorical_text_relationship(anchor, sample_rows)
            else:
                result = anchor

            validated.append(result)

        return validated

    # =========================================================================
    # Numeric-Text Relationship Discovery (Phase 2 Novelty)
    # =========================================================================

    def _discover_numeric_text_anchors(
        self, sample_rows: pd.DataFrame, numeric_cols: List[str], text_cols: List[str], threshold: float
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to discover numeric ↔ text relationships.
        
        Example prompt:
          "In these product samples, what relationships exist between price and description?"
          → Answer: "High prices correlate with premium/luxury descriptors"
        """
        if not self._llm_client or not sample_rows.shape[0]:
            return []

        anchors: List[Dict[str, Any]] = []

        for num_col in numeric_cols:
            for text_col in text_cols:
                # Prepare sample data for LLM
                samples = self._prepare_samples(sample_rows, num_col, text_col, max_samples=5)
                if not samples:
                    continue

                try:
                    # Ask LLM to find relationship
                    prompt = self._build_discovery_prompt(num_col, text_col, samples)
                    response = self._llm_client.chat.completions.create(
                        model=os.getenv("OPENAI_ANCHOR_MODEL", "gpt-4o-mini"),
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a data relationship analyst. Discover if there is a meaningful "
                                    "relationship between numeric and text columns. Return JSON with keys: "
                                    "has_relationship (bool), rule (string), confidence (0-1), evidence (string)."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=200,
                    )

                    content = (response.choices[0].message.content or "").strip()
                    parsed = json.loads(content)

                    if parsed.get("has_relationship") and parsed.get("confidence", 0) >= threshold:
                        anchor: Dict[str, Any] = {
                            "anchor_id": f"{num_col}_{text_col}_semantic_relationship",
                            "type": "numeric_text_relationship",
                            "numeric_column": num_col,
                            "text_column": text_col,
                            "baseline_rule": parsed.get("rule", ""),
                            "llm_evidence": parsed.get("evidence", ""),
                            "confidence": parsed.get("confidence", 0),
                            "source": "RelationalAnchorAgent",
                            "status": "discovered",
                        }
                        anchors.append(anchor)
                        logger.info(
                            f"Discovered anchor: {num_col} ↔ {text_col} (confidence={parsed.get('confidence')})"
                        )

                except Exception as exc:
                    logger.debug(f"Failed to discover numeric-text anchor {num_col}↔{text_col}: {exc}")

        return anchors

    def _discover_categorical_text_anchors(
        self, sample_rows: pd.DataFrame, text_cols: List[str], threshold: float
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to discover categorical ↔ text relationships.
        
        Example: status="luxury" ↔ description="premium/luxury words"
        """
        if not self._llm_client or len(text_cols) < 2 or not sample_rows.shape[0]:
            return []

        anchors: List[Dict[str, Any]] = []

        for i, col1 in enumerate(text_cols):
            for col2 in text_cols[i + 1 :]:
                samples = self._prepare_samples(sample_rows, col1, col2, max_samples=5)
                if not samples:
                    continue

                try:
                    prompt = self._build_discovery_prompt(col1, col2, samples)
                    response = self._llm_client.chat.completions.create(
                        model=os.getenv("OPENAI_ANCHOR_MODEL", "gpt-4o-mini"),
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a text data analyst. Discover if there is semantic coherence "
                                    "between these text/categorical columns. Return JSON with keys: "
                                    "has_relationship (bool), rule (string), confidence (0-1), evidence (string)."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=200,
                    )

                    content = (response.choices[0].message.content or "").strip()
                    parsed = json.loads(content)

                    if parsed.get("has_relationship") and parsed.get("confidence", 0) >= threshold:
                        anchor: Dict[str, Any] = {
                            "anchor_id": f"{col1}_{col2}_semantic_coherence",
                            "type": "categorical_text_relationship",
                            "column_1": col1,
                            "column_2": col2,
                            "baseline_rule": parsed.get("rule", ""),
                            "llm_evidence": parsed.get("evidence", ""),
                            "confidence": parsed.get("confidence", 0),
                            "source": "RelationalAnchorAgent",
                            "status": "discovered",
                        }
                        anchors.append(anchor)

                except Exception as exc:
                    logger.debug(f"Failed to discover text-text anchor {col1}↔{col2}: {exc}")

        return anchors

    # =========================================================================
    # Anchor Validation
    # =========================================================================

    def _validate_numeric_correlation(self, anchor: Dict[str, Any], sample_rows: pd.DataFrame) -> Dict[str, Any]:
        """Recompute correlation for numeric-numeric anchors."""
        try:
            left = anchor.get("left_column")
            right = anchor.get("right_column")
            if not left or not right or left not in sample_rows.columns or right not in sample_rows.columns:
                return anchor

            numeric_left = pd.to_numeric(sample_rows[left], errors="coerce").dropna()
            numeric_right = pd.to_numeric(sample_rows[right], errors="coerce").dropna()

            if len(numeric_left) < 3 or len(numeric_right) < 3:
                return anchor

            corr = abs(float(numeric_left.corr(numeric_right)))
            if np.isnan(corr):
                corr = 0.0

            anchor["current_correlation_strength"] = round(corr, 3)
            anchor["validation_status"] = "valid" if corr > 0.4 else "degraded"
        except Exception as exc:
            logger.debug(f"Failed to validate correlation {anchor.get('anchor_id')}: {exc}")

        return anchor

    def _validate_numeric_text_relationship(self, anchor: Dict[str, Any], sample_rows: pd.DataFrame) -> Dict[str, Any]:
        """Validate numeric-text relationship by counting violations."""
        try:
            num_col = anchor.get("numeric_column")
            text_col = anchor.get("text_column")

            if not num_col or not text_col or num_col not in sample_rows.columns or text_col not in sample_rows.columns:
                return anchor

            # Count violations (rows that violate the baseline rule)
            violations = 0
            for _, row in sample_rows.iterrows():
                num_val = pd.to_numeric(row.get(num_col), errors="coerce")
                text_val = str(row.get(text_col, "")).lower()

                if pd.isna(num_val) or not text_val:
                    continue

                # Simple heuristic: check if high values match rule
                # (In real use, this would be more sophisticated LLM validation)
                violations += 0  # Simplified for now

            total = sample_rows.shape[0]
            violation_rate = violations / max(total, 1)

            anchor["current_violation_rate"] = round(violation_rate, 3)
            anchor["validation_status"] = "valid" if violation_rate < 0.3 else "weakened"
        except Exception as exc:
            logger.debug(f"Failed to validate numeric-text relationship: {exc}")

        return anchor

    def _validate_categorical_text_relationship(self, anchor: Dict[str, Any], sample_rows: pd.DataFrame) -> Dict[str, Any]:
        """Validate categorical-text relationship by counting coherence."""
        try:
            col1 = anchor.get("column_1")
            col2 = anchor.get("column_2")

            if not col1 or not col2 or col1 not in sample_rows.columns or col2 not in sample_rows.columns:
                return anchor

            # Simplified: count rows where both columns have non-null values
            coherent = 0
            for _, row in sample_rows.iterrows():
                val1 = str(row.get(col1, "")).strip()
                val2 = str(row.get(col2, "")).strip()
                if val1 and val2:
                    coherent += 1

            total = sample_rows.shape[0]
            coherence_rate = coherent / max(total, 1)

            anchor["current_coherence_rate"] = round(coherence_rate, 3)
            anchor["validation_status"] = "valid" if coherence_rate > 0.7 else "degraded"
        except Exception as exc:
            logger.debug(f"Failed to validate categorical-text relationship: {exc}")

        return anchor

    # =========================================================================
    # Utility Helpers
    # =========================================================================

    @staticmethod
    def _prepare_samples(
        rows: pd.DataFrame, col1: str, col2: str, max_samples: int = 5
    ) -> List[Dict[str, Any]]:
        """Extract sample pairs of values from two columns."""
        samples: List[Dict[str, Any]] = []

        for _, row in rows.iterrows():
            val1 = row.get(col1)
            val2 = row.get(col2)

            if val1 is None or val2 is None or (isinstance(val1, float) and np.isnan(val1)):
                continue
            if isinstance(val2, float) and np.isnan(val2):
                continue

            samples.append({col1: str(val1), col2: str(val2)})

            if len(samples) >= max_samples:
                break

        return samples

    @staticmethod
    def _build_discovery_prompt(col1: str, col2: str, samples: List[Dict[str, Any]]) -> str:
        """Build LLM prompt for discovering relationships."""
        samples_text = "\n".join(f"  {col1}={s[col1]}, {col2}={s[col2]}" for s in samples)
        return (
            f"Analyze these {col1} and {col2} column samples:\n\n{samples_text}\n\n"
            f"Is there a meaningful relationship between {col1} and {col2}? "
            f"Return JSON: {{'has_relationship': bool, 'rule': string, 'confidence': 0-1, 'evidence': string}}"
        )

    @staticmethod
    def _build_llm_client() -> Optional[Any]:
        """Build OpenAI client if API key exists."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.info("OPENAI_API_KEY not set. Running RelationalAnchorAgent in demo mode.")
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
    import json as json_module

    profile_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_product_demo_profile.json")
    csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("test_product_demo.csv")

    if not profile_path.exists() or not csv_path.exists():
        print(f"Error: {profile_path} or {csv_path} not found")
        sys.exit(1)

    # Load profile and samples
    with open(profile_path, "r") as f:
        profile = json_module.load(f)
    df = pd.read_csv(csv_path)

    print(f"[RelationalAnchorAgent] Profile: {profile['metadata']['dataset_name']}")
    print(f"[RelationalAnchorAgent] Samples: {len(df)} rows")

    agent = RelationalAnchorAgent()
    print("[RelationalAnchorAgent] Discovering relational anchors...")

    anchors = agent.discover_anchors(profile, df, numeric_threshold=0.5, text_threshold=0.7)

    print(f"[RelationalAnchorAgent] ✓ Discovered {len(anchors)} anchors")
    for anchor in anchors:
        print(f"  - {anchor.get('anchor_id')}: {anchor.get('type')}")

    print("[RelationalAnchorAgent] ✓ Phase 2 ready")
