"""
BaselineAgent: Phase 1.5 of Agentic Semantic FeatureOps

This agent is responsible for:
  1. Loading persisted baseline profiles (internal_baseline.json, external_baseline.json)
  2. Finding matching versions/families for baseline lookup
  3. Providing baseline context to downstream agents (Relational Anchor, Scoring, etc.)

This bridges Phase 1 (ProfilerAgent) → Phase 2 (RelationalAnchorAgent).

No LLM calls in this phase; pure profile retrieval and matching logic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaselineAgent:
    """
    Phase 1.5 Agent: Baseline Retrieval and Management
    
    Loads, manages, and retrieves baseline profiles for drift comparison.
    """

    def __init__(self, baseline_dir: Path):
        """
        Initialize the baseline agent.
        
        Args:
            baseline_dir: Directory containing baseline JSON files
                Expected structure:
                  baseline_dir/
                    ├─ internal_baseline.json
                    ├─ external_baseline.json
        """
        self.baseline_dir = baseline_dir
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.internal_baseline_path = self.baseline_dir / "internal_baseline.json"
        self.external_baseline_path = self.baseline_dir / "external_baseline.json"

    def load_internal_baseline(self) -> Optional[Dict[str, Any]]:
        """Load the saved internal baseline profile."""
        return self._load_baseline(self.internal_baseline_path)

    def load_external_baseline(self) -> Optional[Dict[str, Any]]:
        """Load the saved external baseline profile."""
        return self._load_baseline(self.external_baseline_path)

    def save_internal_baseline(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Save a new internal baseline profile."""
        return self._save_baseline(self.internal_baseline_path, profile, "internal")

    def save_external_baseline(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Save a new external baseline profile."""
        return self._save_baseline(self.external_baseline_path, profile, "external")

    def get_baseline_metadata(self) -> Dict[str, Any]:
        """Retrieve metadata about currently loaded baselines."""
        internal = self.load_internal_baseline()
        external = self.load_external_baseline()

        return {
            "internal": {
                "status": "loaded" if internal else "not_found",
                "dataset_name": internal.get("metadata", {}).get("dataset_name") if internal else None,
                "row_count": internal.get("metadata", {}).get("row_count") if internal else None,
                "column_count": internal.get("metadata", {}).get("column_count") if internal else None,
                "built_at": internal.get("metadata", {}).get("built_at") if internal else None,
            },
            "external": {
                "status": "loaded" if external else "not_found",
                "dataset_name": external.get("metadata", {}).get("dataset_name") if external else None,
                "row_count": external.get("metadata", {}).get("row_count") if external else None,
                "column_count": external.get("metadata", {}).get("column_count") if external else None,
                "built_at": external.get("metadata", {}).get("built_at") if external else None,
            },
        }

    def compare_baselines(self) -> Dict[str, Any]:
        """
        Compare internal and external baselines.
        
        Provides insights like:
          - Column alignment (common columns, new/missing)
          - Scale consistency
          - Semantic drift from internal to external
        """
        internal = self.load_internal_baseline()
        external = self.load_external_baseline()

        if not internal or not external:
            return {
                "status": "incomplete",
                "message": "Both internal and external baselines are required for comparison.",
            }

        internal_cols = {col["column_name"] for col in internal.get("column_profiles", [])}
        external_cols = {col["column_name"] for col in external.get("column_profiles", [])}

        common_cols = internal_cols & external_cols
        new_cols = external_cols - internal_cols
        missing_cols = internal_cols - external_cols

        return {
            "status": "complete",
            "column_alignment": {
                "common_columns": sorted(list(common_cols)),
                "new_in_external": sorted(list(new_cols)),
                "removed_in_external": sorted(list(missing_cols)),
            },
            "internal_anchors": len(internal.get("relational_anchors", [])),
            "external_anchors": len(external.get("relational_anchors", [])),
            "internal_dataset": internal.get("metadata", {}).get("dataset_name"),
            "external_dataset": external.get("metadata", {}).get("dataset_name"),
        }

    def get_column_profiles(self, baseline_type: str = "internal", column_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve column profiles from a baseline.
        
        Args:
            baseline_type: "internal" or "external"
            column_name: Optional filter for specific column
            
        Returns:
            Dictionary mapping column names to profiles
        """
        if baseline_type == "internal":
            baseline = self.load_internal_baseline()
        elif baseline_type == "external":
            baseline = self.load_external_baseline()
        else:
            return {"error": f"Unknown baseline_type: {baseline_type}"}

        if not baseline:
            return {"status": "not_found"}

        profiles: Dict[str, Any] = {}
        for col in baseline.get("column_profiles", []):
            col_name = col["column_name"]
            if column_name and col_name != column_name:
                continue
            profiles[col_name] = col

        return profiles

    def get_relational_anchors(self, baseline_type: str = "internal") -> List[Dict[str, Any]]:
        """
        Retrieve discovered relational anchors from a baseline.
        
        Args:
            baseline_type: "internal" or "external"
            
        Returns:
            List of anchor definitions
        """
        if baseline_type == "internal":
            baseline = self.load_internal_baseline()
        elif baseline_type == "external":
            baseline = self.load_external_baseline()
        else:
            return []

        if not baseline:
            return []

        return baseline.get("relational_anchors", [])

    # =========================================================================
    # Private Helpers
    # =========================================================================

    @staticmethod
    def _load_baseline(path: Path) -> Optional[Dict[str, Any]]:
        """Load a baseline JSON file."""
        if not path.exists():
            logger.debug(f"Baseline not found: {path}")
            return None

        try:
            with open(path, "r") as f:
                baseline = json.load(f)
            logger.info(f"Loaded baseline from {path}")
            return baseline
        except Exception as exc:
            logger.error(f"Failed to load baseline {path}: {exc}")
            return None

    @staticmethod
    def _save_baseline(path: Path, profile: Dict[str, Any], baseline_type: str) -> Dict[str, Any]:
        """Save a baseline JSON file."""
        try:
            with open(path, "w") as f:
                json.dump(profile, f, indent=2)
            logger.info(f"Saved {baseline_type} baseline to {path}")
            return {
                "status": "ok",
                "baseline_type": baseline_type,
                "path": str(path),
                "dataset_name": profile.get("metadata", {}).get("dataset_name"),
                "saved_at": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Failed to save baseline {path}: {exc}")
            return {
                "status": "error",
                "baseline_type": baseline_type,
                "error": str(exc),
            }


# ========================================================================
# Standalone CLI for testing
# ========================================================================

if __name__ == "__main__":
    import sys

    baseline_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/services/agentic_ai/featureops/drift_state")

    print(f"[BaselineAgent] Initializing with baseline_dir: {baseline_dir}")
    agent = BaselineAgent(baseline_dir)

    print("\n[BaselineAgent] Retrieving baseline metadata...")
    metadata = agent.get_baseline_metadata()
    print(f"  Internal: {metadata['internal']['status']}")
    print(f"  External: {metadata['external']['status']}")

    print("\n[BaselineAgent] Comparing baselines...")
    comparison = agent.compare_baselines()
    if comparison.get("status") == "complete":
        print(f"  Common columns: {len(comparison['column_alignment']['common_columns'])}")
        print(f"  Internal anchors: {comparison['internal_anchors']}")
        print(f"  External anchors: {comparison['external_anchors']}")
    else:
        print(f"  {comparison.get('message')}")

    print("\n[BaselineAgent] ✓ Baseline retrieval ready for Phase 2")
