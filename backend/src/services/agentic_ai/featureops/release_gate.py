from __future__ import annotations

from .models import DriftResult, FeatureReleaseDecision, FeatureValidationResult


class NonCompensatoryReleaseGate:
    """Hard failures cannot be overridden by strong downstream scores."""

    def decide(
        self,
        validation: FeatureValidationResult,
        drift: DriftResult,
        lineage: dict,
        checks: dict | None = None,
    ) -> FeatureReleaseDecision:
        checks = checks or {}
        reasons = []

        if validation.hard_failures:
            status = "QUARANTINED"
            reasons.append("Critical contract failure detected.")
        elif not checks.get("schema_consistency", True):
            status = "QUARANTINED"
            reasons.append("Schema consistency check failed.")
        elif not checks.get("lineage_availability", True):
            status = "QUARANTINED"
            reasons.append("Lineage is missing, so feature provenance cannot be trusted.")
        elif not checks.get("business_rule_validity", True):
            status = "QUARANTINED"
            reasons.append("Business-rule validity check failed.")
        elif drift.semantic_drift_detected:
            status = "QUARANTINED" if drift.severity == "high" else "CONDITIONAL"
            reasons.append("Semantic drift was detected.")
        elif drift.statistical_drift_detected:
            status = "CONDITIONAL"
            reasons.append("Statistical drift was detected.")
        elif validation.soft_failures or not checks.get("contract_compliance", True):
            status = "CONDITIONAL"
            reasons.append("Soft contract compliance issue detected.")
        else:
            status = "READY"
            reasons.append("All release checks passed.")
        return FeatureReleaseDecision(
            status=status,
            validation=validation,
            drift=drift,
            lineage=lineage,
            checks=checks,
            reasons=reasons,
        )
