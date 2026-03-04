import math

# Simple configurable reward simulator for offline experiments

DEFAULT_WEIGHTS = {
    "pipeline_success": 1.0,
    "dq_improvement": 0.8,
    "storage_cost": -0.3,
    "manual_intervention_penalty": -1.0,
}


def simulate_reward(action: str, features: dict, weights: dict = None) -> float:
    """Return a simulated scalar reward for taking `action` given `features`.

    Simple heuristic-based reward composed from:
      - pipeline success proxy (downstream_failures == 0)
      - DQ proxy (null_ratio_delta negative -> improvement)
      - storage tier cost penalty
      - manual intervention penalty when action is human approval

    This is intentionally tunable for experiments.
    """
    w = DEFAULT_WEIGHTS.copy()
    if weights:
        w.update(weights)

    f = features.get("features") if isinstance(features, dict) and "features" in features else features

    # pipeline success: 1 if no downstream failures
    downstream_failures = float(getattr(f, "downstream_failures", f.get("downstream_failures", 0))) if isinstance(f, dict) else float(f[8])
    pipeline_success = 1.0 if downstream_failures == 0 else 0.0

    # dq improvement: if null_ratio_delta decreased (negative is improvement)
    null_delta = float(getattr(f, "null_ratio_delta", f.get("null_ratio_delta", 0.0))) if isinstance(f, dict) else float(f[6])
    dq_improvement = -null_delta if null_delta < 0 else 0.0

    # storage cost: moving to colder tier increases cost penalty
    storage_imp = float(getattr(f, "storage_tier_imp", f.get("storage_tier_imp", 0.0))) if isinstance(f, dict) else float(f[10])
    storage_cost = storage_imp * 0.1

    reward = (
        w["pipeline_success"] * pipeline_success
        + w["dq_improvement"] * dq_improvement
        + w["storage_cost"] * storage_cost
    )

    if action == "require_human_approval":
        reward += w["manual_intervention_penalty"]

    # small penalty for creating new schema versions or rollbacks (storage/time cost)
    if action in ["create_new_schema_version", "rollback_previous_schema"]:
        reward -= 0.05

    return float(reward)


def load_weights(config_path: str = None) -> dict:
    """Load reward weights from a JSON config file next to the decision engine.

    If not present, returns DEFAULT_WEIGHTS.
    """
    import json
    import os
    cfg_path = config_path or os.path.join("gold", "ml_decision_engine", "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("reward_weights", DEFAULT_WEIGHTS)
        except Exception:
            return DEFAULT_WEIGHTS
    return DEFAULT_WEIGHTS
