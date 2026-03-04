import abc
import numpy as np
import os
import json
from typing import Tuple

POLICY_ACTIONS = [
    "auto_merge_schema",
    "create_new_schema_version",
    "quarantine_data",
    "rollback_previous_schema",
    "require_human_approval",
]


class PolicyBase(abc.ABC):
    def __init__(self, actions=POLICY_ACTIONS):
        self.actions = actions

    @abc.abstractmethod
    def choose_action(self, x: np.ndarray) -> Tuple[str, float]:
        """Return (action, score/confidence)"""

    @abc.abstractmethod
    def update(self, action: str, x: np.ndarray, reward: float):
        """Update policy with observed reward for action taken"""

    def explain(self, action: str, x: np.ndarray) -> dict:
        """Return per-feature contribution / attribution for the given action and context x.

        Default: no explanation (empty dict).
        """
        return {}


class LinUCBPolicy(PolicyBase):
    """Simple LinUCB implementation for contextual bandit.

    Maintains parameter vectors theta_a for each action a.
    """

    def __init__(self, actions=POLICY_ACTIONS, alpha: float = 1.0, d: int = None):
        super().__init__(actions=actions)
        self.alpha = float(alpha)
        self.d = d  # feature dimension; set at first choose if None

        # per-action A (dxd) and b (dx1)
        self.A = {}
        self.b = {}

    def _ensure_dim(self, x: np.ndarray):
        if self.d is None:
            self.d = x.shape[0]
            for a in self.actions:
                self.A[a] = np.eye(self.d)
                self.b[a] = np.zeros((self.d,))

    def choose_action(self, x: np.ndarray) -> Tuple[str, float]:
        x = np.asarray(x, dtype=float)
        self._ensure_dim(x)

        best_action = None
        best_score = -np.inf
        scores = {}  # Track all scores
        
        for a in self.actions:
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv.dot(self.b[a])
            p = theta.dot(x) + self.alpha * np.sqrt(x.dot(A_inv).dot(x))
            scores[a] = float(p)  # Store score
            if p > best_score:
                best_score = float(p)
                best_action = a
        
        # Print UCB scores for visibility
        print("\n" + "="*60)
        print("UCB SCORES (LinUCB Policy Decision)")
        print("="*60)
        for action, score in sorted(scores.items(), key=lambda x: -x[1]):
            marker = "[SELECTED]" if action == best_action else "          "
            print(f"{marker} {action}: {score:.3f}")
        print("="*60)
        
        return best_action, float(best_score)

    def update(self, action: str, x: np.ndarray, reward: float):
        x = np.asarray(x, dtype=float)
        self._ensure_dim(x)
        self.A[action] += np.outer(x, x)
        self.b[action] += reward * x

    def explain(self, action: str, x: np.ndarray) -> dict:
        # compute theta and per-feature contributions
        x = np.asarray(x, dtype=float)
        self._ensure_dim(x)
        try:
            A_inv = np.linalg.inv(self.A[action])
            theta = A_inv.dot(self.b[action])
            contrib = theta * x
            # return mapping index->value and top features
            contrib_list = contrib.tolist()
            top_idx = sorted(range(len(contrib_list)), key=lambda i: abs(contrib_list[i]), reverse=True)[:5]
            return {"theta": theta.tolist(), "contrib": contrib_list, "top_features_idx": top_idx}
        except Exception:
            return {}

    def save(self, path: str):
        payload = {"alpha": self.alpha, "d": self.d, "actions": self.actions, "A": {}, "b": {}}
        for a in self.actions:
            payload["A"][a] = self.A[a].tolist()
            payload["b"][a] = self.b[a].tolist()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        obj = cls(actions=payload.get("actions"), alpha=payload.get("alpha", 1.0), d=payload.get("d"))
        for a in obj.actions:
            obj.A[a] = np.array(payload["A"][a])
            obj.b[a] = np.array(payload["b"][a])
        return obj


class EpsilonGreedyPolicy(PolicyBase):
    def __init__(self, actions=POLICY_ACTIONS, epsilon: float = 0.1):
        super().__init__(actions=actions)
        self.epsilon = epsilon
        self.counts = {a: 0 for a in self.actions}
        self.values = {a: 0.0 for a in self.actions}

    def choose_action(self, x: np.ndarray) -> Tuple[str, float]:
        import random
        if random.random() < self.epsilon:
            a = np.random.choice(self.actions)
            return a, 0.0
        else:
            best = max(self.actions, key=lambda a: self.values[a])
            return best, float(self.values[best])

    def update(self, action: str, x: np.ndarray, reward: float):
        self.counts[action] += 1
        n = self.counts[action]
        self.values[action] += (reward - self.values[action]) / n

    def explain(self, action: str, x: np.ndarray) -> dict:
        # EpsilonGreedy has simple estimated values per action; attribute uniformly
        x = np.asarray(x, dtype=float) if hasattr(x, "__iter__") else None
        val = self.values.get(action, 0.0)
        if x is None:
            return {"value": val}
        # distribute value proportionally across features
        try:
            arr = np.asarray(x, dtype=float)
            abs_arr = np.abs(arr)
            total = abs_arr.sum() if abs_arr.sum() != 0 else 1.0
            contrib = (abs_arr / total * val).tolist()
            return {"value": val, "contrib": contrib}
        except Exception:
            return {"value": val}

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"epsilon": self.epsilon, "counts": self.counts, "values": self.values}, f, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        obj = cls(epsilon=payload.get("epsilon", 0.1))
        obj.counts = payload.get("counts", obj.counts)
        obj.values = payload.get("values", obj.values)
        return obj
