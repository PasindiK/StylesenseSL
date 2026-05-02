from __future__ import annotations

from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional

from .contracts import FeatureContractValidator, load_contracts
from .drift import SemanticDriftDetector
from .release_gate import NonCompensatoryReleaseGate
from .store import FeatureStoreRegistry


class AgenticSemanticFeatureOps:
    """Govern recommendation features before they are consumed by ranking."""

    def __init__(self, root_dir: Optional[Path] = None):
        base_dir = root_dir or Path(__file__).resolve().parents[4]
        processed_root = base_dir / "data" / "processed" / "agentic_featureops"
        contracts = load_contracts()
        self.validator = FeatureContractValidator(contracts)
        self.drift_detector = SemanticDriftDetector(processed_root / "feature_drift_state.json")
        self.release_gate = NonCompensatoryReleaseGate()
        self.store = FeatureStoreRegistry(processed_root)

    @staticmethod
    def _stats(values: Iterable[Any]) -> Dict[str, float]:
        numeric: List[float] = []
        for value in values:
            if value is None:
                continue
            try:
                numeric.append(float(value))
            except Exception:
                continue
        if not numeric:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean": float(mean(numeric)),
            "std": float(pstdev(numeric)) if len(numeric) > 1 else 0.0,
            "min": float(min(numeric)),
            "max": float(max(numeric)),
        }

    @staticmethod
    def _schema_consistency(values: List[Any]) -> bool:
        if not values:
            return False
        numeric = 0
        for value in values:
            if value is None:
                continue
            try:
                float(value)
                numeric += 1
            except Exception:
                return False
        return numeric > 0

    @staticmethod
    def _lineage_available(lineage: Dict[str, Any]) -> bool:
        if not lineage:
            return False
        if not lineage.get("component"):
            return False
        sources = lineage.get("source_systems")
        return isinstance(sources, list) and len(sources) > 0

    @staticmethod
    def _business_rule_valid(feature_name: str, stats: Dict[str, float]) -> bool:
        minimum = float(stats.get("min", 0.0))
        maximum = float(stats.get("max", 0.0))
        average = float(stats.get("mean", 0.0))
        spread = float(stats.get("std", 0.0))

        if minimum < 0.0 or maximum > 1.0:
            return False
        if maximum == minimum and average in {0.0, 1.0}:
            return False
        if feature_name in {"semantic_similarity", "intent_match", "trust_signal"} and average < 0.15:
            return False
        if feature_name == "popularity_signal" and spread <= 0.001:
            return False
        return True

    def govern_feature(self, feature_name: str, values: Iterable[Any], definition: Dict[str, Any], lineage: Dict[str, Any]) -> str:
        sample_values = list(values)
        validation = self.validator.validate({feature_name: sample_values[0] if sample_values else None})
        stats = self._stats(sample_values)
        checks = {
            "schema_consistency": self._schema_consistency(sample_values),
            "contract_compliance": len(validation.hard_failures) == 0 and len(validation.soft_failures) == 0,
            "lineage_availability": self._lineage_available(lineage),
            "business_rule_validity": self._business_rule_valid(feature_name, stats),
        }
        drift = self.drift_detector.evaluate(feature_name=feature_name, definition=definition, current_stats=stats)
        checks["semantic_consistency"] = not drift.semantic_drift_detected
        checks["statistical_stability"] = not drift.statistical_drift_detected
        decision = self.release_gate.decide(validation=validation, drift=drift, lineage=lineage, checks=checks)
        self.store.publish(feature_name, decision, stats)
        return decision.status

    def govern_feature_bundle(self, feature_columns: Dict[str, List[Any]], lineage: Dict[str, Any]) -> Dict[str, str]:
        statuses: Dict[str, str] = {}
        for feature_name, values in feature_columns.items():
            statuses[feature_name] = self.govern_feature(
                feature_name=feature_name,
                values=values,
                definition={"lineage": lineage, "feature_name": feature_name},
                lineage=lineage,
            )
        return statuses
