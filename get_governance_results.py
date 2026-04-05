import sys
sys.path.insert(0, 'backend/src')
from services.data_mesh.agentic_ai.governance_intelligence import ADGRIEngine
from services.data_mesh.agentic_ai.governance_prioritization import GovernancePrioritizationEngine

engine = ADGRIEngine()
results = engine.compute_all_domains()

prio_engine = GovernancePrioritizationEngine()
priorities = prio_engine.prioritize_all_domains(results)

print("=== ADGRI SCORES (sorted highest to lowest) ===")
for r in sorted(results, key=lambda x: x.adgri_score, reverse=True):
    trend = getattr(r, 'trend_direction', 'N/A')
    vol_w = getattr(r, 'volume_weight', 0)
    fresh_w = getattr(r, 'freshness_weight', 0)
    dist_w = getattr(r, 'distribution_weight', 0)
    conf = getattr(r, 'confidence_label', 'N/A')
    factors = [('volume', r.volume_risk, vol_w), ('freshness', r.freshness_risk, fresh_w), ('distribution', r.distribution_risk, dist_w)]
    top_factor = max(factors, key=lambda x: x[1]*x[2] if x[2] else x[1])
    print(f"{r.domain_name}: ADGRI={r.adgri_score:.2f}, vol_risk={r.volume_risk:.4f}, fresh_risk={r.freshness_risk:.4f}, dist_risk={r.distribution_risk:.4f}, top_factor={top_factor[0]}, confidence={conf}, trend={trend}")

print()
print("=== PRIORITIZATION (top 5 by impact) ===")
for p in sorted(priorities, key=lambda x: x.governance_impact_score, reverse=True)[:7]:
    print(f"{p.domain_name}: priority={p.priority_level}, gov_risk={p.governance_risk:.2f}, impact={p.governance_impact_score:.2f}, action='{p.recommended_action}'")
