import abc
import numpy as np
import os
import json
from typing import Dict, Tuple

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

    def score_actions(self, x: np.ndarray) -> Dict[str, float]:
        """UCB score p_a(x) = θ_a^T x + α sqrt(x^T A_a^{-1} x) for every arm.

        When the policy is untrained (all b_a == 0), returns domain-aware proxy scores
        so arms still differentiate (same logic as previous choose_action).
        """
        x = np.asarray(x, dtype=float)
        self._ensure_dim(x)

        scores: Dict[str, float] = {}
        for a in self.actions:
            try:
                A_inv = np.linalg.inv(self.A[a])
                theta = A_inv.dot(self.b[a])
                p = theta.dot(x) + self.alpha * np.sqrt(x.dot(A_inv).dot(x))
                scores[a] = float(p)
            except np.linalg.LinAlgError:
                scores[a] = 0.0

        is_untrained = all(np.allclose(self.b[a], 0) for a in self.actions)
        if is_untrained:
            scores = self._domain_aware_fallback(x)

        return scores

    def choose_action(self, x: np.ndarray) -> Tuple[str, float]:
        """Pick the arm with highest UCB score; ties break by first arm in ``self.actions`` order."""
        scores = self.score_actions(x)
        best_action = max(self.actions, key=lambda a: scores[a])
        best_score = float(scores[best_action])
        return best_action, best_score
    
    def _domain_aware_fallback(self, x: np.ndarray) -> dict:
        """Use domain knowledge to score actions when untrained.
        
        Maps drift characteristics to appropriate actions:
        - Low risk, low changes → auto_merge_schema
        - Medium risk → create_new_schema_version  
        - High risk → quarantine_data / require_human_approval
        """
        # Extract features (assuming: new_cols, missing_cols, dtype_changes, renames, ...)
        num_new = int(x[0]) if len(x) > 0 else 0
        num_missing = int(x[1]) if len(x) > 1 else 0
        num_dtype = int(x[2]) if len(x) > 2 else 0
        num_renames = int(x[3]) if len(x) > 3 else 0
        
        total_changes = num_new + num_missing + num_dtype + num_renames
        risk_score = (num_missing * 5) + (num_dtype * 3) + (num_new * 1) + (num_renames * 2)
        
        scores = {}
        
        # Domain-based scoring logic
        if num_missing > 0 or num_dtype > 2 or risk_score > 10:
            # High risk - needs review or quarantine
            scores["require_human_approval"] = 10.0 + risk_score
            scores["quarantine_data"] = 9.0 + risk_score
            scores["rollback_previous_schema"] = 8.0 + risk_score
            scores["create_new_schema_version"] = 3.0
            scores["auto_merge_schema"] = 1.0
            
        elif num_dtype > 0 or total_changes > 3:
            # Medium risk - create new version or get approval
            scores["create_new_schema_version"] = 8.0 + (num_dtype * 2)
            scores["require_human_approval"] = 7.0 + (num_dtype * 1.5)
            scores["auto_merge_schema"] = 3.0
            scores["quarantine_data"] = 2.0
            scores["rollback_previous_schema"] = 1.5
            
        else:
            # Low risk - can auto-merge
            scores["auto_merge_schema"] = 9.0 + (10 - total_changes)
            scores["create_new_schema_version"] = 5.0
            scores["require_human_approval"] = 2.0
            scores["quarantine_data"] = 1.0
            scores["rollback_previous_schema"] = 0.5
        
        return scores

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
