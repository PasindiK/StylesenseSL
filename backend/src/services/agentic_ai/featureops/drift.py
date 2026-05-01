from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from .models import DriftResult


class SemanticDriftDetector:
    """Lightweight drift detector for derived feature definitions and value snapshots."""

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _signature(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def evaluate(self, feature_name: str, definition: Dict[str, Any], current_stats: Dict[str, Any]) -> DriftResult:
        state = self._load_state()
        previous = state.get(feature_name)
        reasons = []
        score = 0.0

        current_signature = self._signature(definition)
        if previous:
            if previous.get("definition_signature") != current_signature:
                score += 0.7
                reasons.append("Feature definition signature changed from the previous release.")

            previous_mean = previous.get("stats", {}).get("mean")
            current_mean = current_stats.get("mean")
            previous_std = previous.get("stats", {}).get("std")
            current_std = current_stats.get("std")
            if previous_mean is not None and current_mean is not None:
                delta_mean = abs(float(current_mean) - float(previous_mean))
                if delta_mean > 0.35:
                    score += 0.2
                    reasons.append("Feature mean shifted materially from its previous release baseline.")
            if previous_std is not None and current_std is not None:
                delta_std = abs(float(current_std) - float(previous_std))
                if delta_std > 0.35:
                    score += 0.1
                    reasons.append("Feature dispersion shifted materially from its previous release baseline.")

        state[feature_name] = {
            "definition_signature": current_signature,
            "stats": current_stats,
        }
        self._save_state(state)

        score = max(0.0, min(1.0, score))
        return DriftResult(drift_detected=score >= 0.7, score=score, reasons=reasons)

