from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    from .governance_intelligence import GovernanceIntelligenceEngine
except ImportError:
    from governance_intelligence import GovernanceIntelligenceEngine


@dataclass
class PriorityResult:
    domain_name: str
    adgri_score: float
    governance_risk_score: float
    criticality_score: float
    governance_impact_score: float
    priority_level: str
    trend_direction: str
    confidence_level: str
    top_governance_concern: str
    recommended_action: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_name": self.domain_name,
            "adgri_score": round(self.adgri_score, 4),
            "governance_risk_score": round(self.governance_risk_score, 4),
            "criticality_score": round(self.criticality_score, 4),
            "governance_impact_score": round(self.governance_impact_score, 4),
            "priority_level": self.priority_level,
            "trend_direction": self.trend_direction,
            "confidence_level": self.confidence_level,
            "top_governance_concern": self.top_governance_concern,
            "recommended_action": self.recommended_action,
            "explanation": self.explanation,
        }


class GovernancePrioritizationEngine:
    """Impact-aware governance decision-support layer built on ADGRI outputs.

    Model framing:
      governance_risk = 100 - ADGRI
      governance_impact = f(governance_risk, domain_criticality, trend_deterioration, confidence)

    Impact formulation used in this module:
      impact_raw = 0.50*risk + 0.35*criticality + 0.15*trend_factor
      governance_impact = impact_raw * confidence_factor

    Where all components are normalized to [0, 100].
    """

    CORE_DOMAINS = {"sales", "shop", "product", "users"}

    DOMAIN_IMPORTANCE_MAP = {
        "sales": 86.0,
        "product": 82.0,
        "users": 80.0,
        "shop": 76.0,
        "user_preferences": 56.0,
        "engagement": 48.0,
        "interaction": 42.0,
    }

    DOMAIN_CONSUMER_PAGES = {
        "sales": ["Sales", "ShopAnalysis", "Catalog", "DomainAnalytics", "Governance"],
        "product": ["Catalog", "Products", "DomainAnalytics", "Governance"],
        "users": ["Users", "DomainAnalytics", "Governance", "MLHealth"],
        "shop": ["ShopAnalysis", "ShopDomainAnalytics", "DomainAnalytics", "Governance"],
        "user_preferences": ["DomainAnalytics", "Governance"],
        "engagement": ["DomainAnalytics", "Governance", "PipelineMonitoring"],
        "interaction": ["DomainAnalytics", "Governance", "PipelineMonitoring"],
    }

    DOMAIN_API_USAGE_PROXY = {
        "sales": 7,
        "product": 6,
        "users": 6,
        "shop": 5,
        "user_preferences": 3,
        "engagement": 3,
        "interaction": 3,
    }

    PRIORITY_THRESHOLDS = {
        "high": 68.0,
        "medium": 45.0,
    }

    def __init__(self, governance_engine: GovernanceIntelligenceEngine) -> None:
        self.governance_engine = governance_engine

    def priorities_summary(self) -> dict[str, Any]:
        governance_summary = self.governance_engine.governance_summary()
        domains = governance_summary.get("domains", [])

        ranked = [self._build_priority(item).to_dict() for item in domains]
        ranked.sort(key=lambda item: float(item.get("governance_impact_score", 0.0)), reverse=True)

        high_priority = [item for item in ranked if item.get("priority_level") == "High"]
        medium_priority = [item for item in ranked if item.get("priority_level") == "Medium"]
        low_priority = [item for item in ranked if item.get("priority_level") == "Low"]
        avg_impact = (sum(float(item.get("governance_impact_score", 0.0)) for item in ranked) / len(ranked)) if ranked else 0.0
        highest = ranked[0] if ranked else None

        if high_priority:
            action_strategy = "Intervention"
            action_summary = "High-priority domains exist. Apply intervention actions for unstable high-impact domains first."
        elif medium_priority:
            action_strategy = "Monitoring"
            action_summary = "No high-priority domains. Focus on monitoring and preventive governance actions for medium-priority domains."
        else:
            action_strategy = "Routine"
            action_summary = "No urgent governance actions required. Continue routine governance monitoring."

        return {
            "layer_name": "Adaptive Explainable Governance Prioritization Layer",
            "model_name": "Governance Impact Prioritization Index (built on ADGRI)",
            "formula": {
                "risk": "governance_risk = 100 - ADGRI",
                "impact_raw": "impact_raw = 0.50*risk + 0.35*criticality + 0.15*trend_factor",
                "impact_weighted": "governance_impact = impact_raw * confidence_factor",
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "highest_priority_domain": highest,
            "average_impact_score": round(avg_impact, 4),
            "high_priority_domains_count": len(high_priority),
            "medium_priority_domains_count": len(medium_priority),
            "low_priority_domains_count": len(low_priority),
            "action_strategy": action_strategy,
            "action_summary": action_summary,
            "ranked_priorities": ranked,
        }

    def priority_for_domain(self, domain_name: str) -> dict[str, Any]:
        domain_governance = self.governance_engine.governance_domain(domain_name)
        result = self._build_priority(domain_governance).to_dict()
        result["governance_detail"] = {
            "adgri_score": domain_governance.get("adgri_score"),
            "trend_direction": domain_governance.get("trend_direction"),
            "trend_slope": domain_governance.get("trend_slope"),
            "confidence": domain_governance.get("confidence"),
            "top_reason": domain_governance.get("top_reason"),
            "contribution_breakdown": domain_governance.get("contribution_breakdown"),
        }
        return result

    def _build_priority(self, governance_payload: dict[str, Any]) -> PriorityResult:
        domain_name = str(governance_payload.get("domain_name") or "unknown_domain")
        domain_key = self._normalize_domain_key(domain_name)

        adgri = float(governance_payload.get("adgri_score") or governance_payload.get("governance_score") or 0.0)
        governance_risk = self._bounded_100(100.0 - adgri)
        criticality = self._criticality_score(domain_key)
        trend_direction, trend_score = self._trend_signal(governance_payload)

        confidence = governance_payload.get("confidence") or {}
        confidence_level = str(confidence.get("level") or "low").lower()
        confidence_factor = self._confidence_factor(confidence_level)

        risk_component = 0.55 * governance_risk
        criticality_component = 0.30 * criticality
        trend_component = 0.15 * trend_score
        impact_raw = risk_component + criticality_component + trend_component
        impact_score = self._bounded_100(impact_raw * confidence_factor)
        priority_level = self._priority_level(impact_score)

        concern = self._top_concern(governance_payload)
        action = self._recommended_action(
            priority_level=priority_level,
            concern=concern,
            criticality=criticality,
            trend_direction=trend_direction,
        )

        dominant_factor = self._dominant_factor(
            governance_payload=governance_payload,
            criticality_component=criticality_component,
            trend_component=trend_component,
        )

        explanation = self._build_explanation(
            domain_name=domain_name,
            priority_level=priority_level,
            impact_score=impact_score,
            governance_risk=governance_risk,
            criticality=criticality,
            trend_direction=trend_direction,
            confidence_level=confidence_level,
            dominant_factor=dominant_factor,
        )

        return PriorityResult(
            domain_name=domain_name,
            adgri_score=adgri,
            governance_risk_score=governance_risk,
            criticality_score=criticality,
            governance_impact_score=impact_score,
            priority_level=priority_level,
            trend_direction=trend_direction,
            confidence_level=confidence_level.capitalize(),
            top_governance_concern=concern,
            recommended_action=action,
            explanation=explanation,
        )

    def _normalize_domain_key(self, domain_name: str) -> str:
        value = str(domain_name).lower().strip()
        if value.endswith("_domain"):
            value = value[: -len("_domain")]
        if value == "interaction":
            return "interaction"
        return value

    def _criticality_score(self, domain_key: str) -> float:
        base_importance = float(self.DOMAIN_IMPORTANCE_MAP.get(domain_key, 45.0))
        consumers = self.DOMAIN_CONSUMER_PAGES.get(domain_key, [])
        usage_proxy = float(self.DOMAIN_API_USAGE_PROXY.get(domain_key, 2.0))

        consumer_signal = min(100.0, float(len(consumers)) * 14.0)
        api_signal = min(100.0, usage_proxy * 8.0)
        core_bonus = 5.0 if domain_key in self.CORE_DOMAINS else 0.0

        score = (0.62 * base_importance) + (0.23 * consumer_signal) + (0.15 * api_signal) + core_bonus
        return max(20.0, min(95.0, float(score)))

    def _trend_signal(self, governance_payload: dict[str, Any]) -> tuple[str, float]:
        raw_direction = str(governance_payload.get("trend_direction") or "stable").lower()
        slope = float(governance_payload.get("trend_slope") or 0.0)
        change_rate = float(governance_payload.get("trend_change_rate") or 0.0)

        deterioration_strength = max(0.0, (-slope * 45.0) + (max(0.0, -change_rate) * 30.0))
        improvement_strength = max(0.0, (slope * 45.0) + (max(0.0, change_rate) * 30.0))

        if raw_direction == "deteriorating" and deterioration_strength >= 14.0:
            direction = "deteriorating"
        elif raw_direction == "improving" and improvement_strength >= 12.0:
            direction = "improving"
        elif deterioration_strength >= 20.0:
            direction = "deteriorating"
        elif improvement_strength >= 16.0:
            direction = "improving"
        else:
            direction = "stable"

        mapping = {
            "deteriorating": 78.0,
            "stable": 45.0,
            "improving": 25.0,
        }
        trend_score = mapping.get(direction, 45.0)
        return direction, trend_score

    def _confidence_factor(self, confidence_level: str) -> float:
        mapping = {
            "high": 1.00,
            "medium": 0.90,
            "low": 0.80,
        }
        return mapping.get(confidence_level, 0.80)

    def _priority_level(self, impact_score: float) -> str:
        if impact_score >= float(self.PRIORITY_THRESHOLDS["high"]):
            return "High"
        if impact_score >= float(self.PRIORITY_THRESHOLDS["medium"]):
            return "Medium"
        return "Low"

    def _top_concern(self, governance_payload: dict[str, Any]) -> str:
        top_reason = str(governance_payload.get("top_reason") or "").strip()
        if top_reason:
            return top_reason

        contributions = governance_payload.get("contribution_breakdown") or {}
        if isinstance(contributions, dict) and contributions:
            best = max(
                contributions.items(),
                key=lambda item: float((item[1] or {}).get("score_impact", 0.0)),
            )[0]
            if best == "freshness":
                return "Freshness instability is the dominant governance concern."
            if best == "volume":
                return "Volume instability is the dominant governance concern."
            if best == "distribution":
                return "Distribution instability is the dominant governance concern."

        return "Mixed governance instability signals require closer review."

    def _recommended_action(self, priority_level: str, concern: str, criticality: float, trend_direction: str) -> str:
        concern_lower = concern.lower()
        actions: list[str] = []

        if priority_level == "High":
            if "fresh" in concern_lower:
                actions.append("Intervene now: investigate refresh instability and enforce domain refresh SLA checks.")
            elif "volume" in concern_lower:
                actions.append("Intervene now: review abnormal volume behavior and validate upstream ingest consistency.")
            elif "distribution" in concern_lower:
                actions.append("Intervene now: monitor and contain distribution shift with focused quality controls.")
            else:
                actions.append("Intervene now: run focused governance diagnostics on current instability drivers.")
        elif priority_level == "Medium":
            if "fresh" in concern_lower:
                actions.append("Monitor refresh cadence and tighten SLA alerts for this domain.")
            elif "volume" in concern_lower:
                actions.append("Monitor volume pattern changes and investigate recurring anomalies.")
            elif "distribution" in concern_lower:
                actions.append("Monitor distribution drift and schedule targeted quality review.")
            else:
                actions.append("Monitor governance indicators and schedule preventive review.")
        else:
            actions.append("No urgent intervention required; continue routine governance monitoring.")

        if priority_level != "Low" and criticality >= 75.0:
            actions.append("Prioritize domain review due to high business criticality.")

        if priority_level == "High" and str(trend_direction).lower() == "deteriorating":
            actions.append("Escalate due to worsening governance trend.")

        return " ".join(actions[:2])

    def _dominant_factor(self, governance_payload: dict[str, Any], criticality_component: float, trend_component: float) -> str:
        contributions = governance_payload.get("contribution_breakdown") or {}
        risk_component = 0.0
        risk_label = "risk"

        if isinstance(contributions, dict) and contributions:
            top_metric = max(
                contributions.items(),
                key=lambda item: float((item[1] or {}).get("score_impact", 0.0)),
            )[0]
            risk_component = float((contributions.get(top_metric) or {}).get("score_impact", 0.0))
            risk_label = {
                "freshness": "freshness",
                "volume": "volume",
                "distribution": "distribution",
            }.get(top_metric, "risk")

        scored = [
            ("criticality", criticality_component),
            ("trend", trend_component),
            (risk_label, risk_component),
        ]
        return max(scored, key=lambda item: float(item[1]))[0]

    def _build_explanation(
        self,
        domain_name: str,
        priority_level: str,
        impact_score: float,
        governance_risk: float,
        criticality: float,
        trend_direction: str,
        confidence_level: str,
        dominant_factor: str,
    ) -> str:
        level_text = priority_level.lower()
        base = (
            f"{domain_name} is classified as {level_text} priority (impact {impact_score:.1f}). "
            f"Governance risk is {governance_risk:.1f}, criticality is {criticality:.1f}, "
            f"trend is {trend_direction}, and confidence is {confidence_level}."
        )

        factor_reason = {
            "freshness": "Freshness instability is the dominant factor.",
            "volume": "Volume instability is the dominant factor.",
            "distribution": "Distribution instability is the dominant factor.",
            "criticality": "Business criticality is amplifying governance impact.",
            "trend": "Trend deterioration is increasing governance urgency.",
        }.get(dominant_factor, "Governance signals are mixed and should be monitored.")

        return f"{base} {factor_reason}"

    def _bounded_100(self, value: float) -> float:
        return max(0.0, min(100.0, float(value)))
