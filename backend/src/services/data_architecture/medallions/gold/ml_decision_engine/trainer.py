import os
import glob
import json
import joblib
import numpy as np
from .feature_builder import build_feature_vector
from .policy import LinUCBPolicy, EpsilonGreedyPolicy
from .reward_simulator import simulate_reward, load_weights

DECISIONS_LOG = os.path.join("gold", "ml_decision_engine", "logs")
MODELS_DIR = os.path.join("gold", "ml_decision_engine", "models")
os.makedirs(DECISIONS_LOG, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


def _append_decision_log(record: dict):
    path = os.path.join(DECISIONS_LOG, "decisions.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_historical_events(events_dir: str):
    paths = glob.glob(os.path.join(events_dir, "*.json"))
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                yield json.load(f)
        except Exception:
            continue


def offline_train(events_dir: str, policy_save_path: str = None, policy_type: str = "linucb", epochs: int = 3, weights: dict = None):
    """Offline replay training using simulated rewards.

    - events_dir: location of historical drift event json files (e.g. `metadata/drift_events`)
    - policy_save_path: where to save the learned policy
    - policy_type: 'linucb' or 'eps'
    """
    if policy_type == "linucb":
        policy = LinUCBPolicy(alpha=0.5)
    else:
        policy = EpsilonGreedyPolicy()

    events = list(load_historical_events(events_dir))
    if not events:
        raise FileNotFoundError(f"No historical events found in {events_dir}")

    action_counts = {a: 0 for a in policy.actions}

    # load weights from config if not provided
    if weights is None:
        weights = load_weights()

    for epoch in range(epochs):
        cumulative_reward = 0.0
        for ev in events:
            fb = build_feature_vector(ev, dq_metrics=ev.get("extra", {}).get("dq_metrics", {}), pipeline_meta=ev.get("extra", {}).get("pipeline_meta", {}))
            x = fb["vector"]
            action, score = policy.choose_action(x)
            reward = simulate_reward(action, fb, weights=weights)
            policy.update(action, x, reward)
            action_counts[action] += 1
            cumulative_reward += reward

            # log decision for analysis
            # include explainability from policy
            explain = policy.explain(action, x)
            record = {
                "timestamp": ev.get("timestamp"),
                "table": ev.get("table"),
                "source_file": ev.get("source_file"),
                "features": fb.get("features"),
                "action": action,
                "score": score,
                "reward": reward,
                "explain": explain,
            }
            _append_decision_log(record)

        print(f"Epoch {epoch+1}/{epochs} cumulative_reward={cumulative_reward:.4f}")

    if policy_save_path:
        policy.save(policy_save_path)
        print(f"Policy saved: {policy_save_path}")
    else:
        # also save a default path
        default_path = os.path.join(MODELS_DIR, "policy.json")
        policy.save(default_path)
        print(f"Policy saved: {default_path}")

    metrics_path = os.path.join(MODELS_DIR, "training_metrics.json")
    metrics = {"action_counts": action_counts}
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"Training metrics saved: {metrics_path}")

    return policy, metrics


if __name__ == "__main__":
    # default offline training run (uses metadata/drift_events)
    from pathlib import Path
    events_dir = os.path.join("metadata", "drift_events")
    if not Path(events_dir).exists():
        print("No drift events found to train on. Generate or place sample JSON events in metadata/drift_events/")
    else:
        offline_train(events_dir, epochs=2)
