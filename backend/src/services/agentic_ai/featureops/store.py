from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .models import FeatureReleaseDecision


class FeatureStoreRegistry:
    """File-backed registry for feature release status and lineage."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "feature_registry.json"

    def _load(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def publish(self, feature_name: str, decision: FeatureReleaseDecision, stats: Dict[str, Any]) -> None:
        payload = self._load()
        payload[feature_name] = {
            "status": decision.status,
            "lineage": decision.lineage,
            "checks": decision.checks,
            "reasons": decision.reasons,
            "drift_score": decision.drift.score,
            "semantic_drift_score": decision.drift.semantic_score,
            "statistical_drift_score": decision.drift.statistical_score,
            "drift_severity": decision.drift.severity,
            "drift_reasons": decision.drift.reasons,
            "validation_issues": [
                {
                    "feature_name": issue.feature_name,
                    "severity": issue.severity,
                    "message": issue.message,
                }
                for issue in decision.validation.issues
            ],
            "stats": stats,
        }
        self._save(payload)

    def get_status(self, feature_name: str) -> str:
        payload = self._load()
        feature_payload = payload.get(feature_name) or {}
        return str(feature_payload.get("status") or "READY")
