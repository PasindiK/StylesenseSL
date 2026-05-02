from __future__ import annotations

from .models import DriftResult, FeatureReleaseDecision, FeatureValidationResult


class NonCompensatoryReleaseGate:
    """Hard failures cannot be overridden by strong downstream scores."""

    def decide(
        self,
        validation: FeatureValidationResult,
        drift: DriftResult,
        lineage: dict,
    ) -> FeatureReleaseDecision:
        if validation.hard_failures:
            status = "QUARANTINED"
        elif drift.drift_detected or validation.soft_failures:
            status = "CONDITIONAL"
        else:
            status = "READY"
        return FeatureReleaseDecision(status=status, validation=validation, drift=drift, lineage=lineage)

