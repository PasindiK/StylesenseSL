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

    def govern_feature(self, feature_name: str, values: Iterable[Any], definition: Dict[str, Any], lineage: Dict[str, Any]) -> str:
        sample_values = list(values)
        validation = self.validator.validate({feature_name: sample_values[0] if sample_values else None})
        stats = self._stats(sample_values)
        drift = self.drift_detector.evaluate(feature_name=feature_name, definition=definition, current_stats=stats)
        decision = self.release_gate.decide(validation=validation, drift=drift, lineage=lineage)
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

