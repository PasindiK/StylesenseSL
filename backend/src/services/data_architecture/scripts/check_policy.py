#!/usr/bin/env python
"""Check trained LinUCB policy.json — diagnose zero / identical scores (data architecture)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Package root: .../data_architecture (parent of scripts/)
ROOT = Path(__file__).resolve().parents[1]
policy_path = ROOT / "medallions" / "gold" / "ml_decision_engine" / "models" / "policy.json"

if not policy_path.is_file():
    print(f"Policy file not found: {policy_path}")
    sys.exit(1)

with open(policy_path, "r", encoding="utf-8") as f:
    policy = json.load(f)

print("=" * 70)
print("POLICY FILE DIAGNOSTICS")
print("=" * 70)
print(f"\nAlpha: {policy['alpha']}")
print(f"Feature dimension: {policy['d']}")
print(f"Actions: {len(policy['actions'])}")

print("\n" + "=" * 70)
print("b VECTORS (learned reward parameters)")
print("=" * 70)

for action in policy["actions"]:
    b_vec = policy["b"][action]
    non_zero = sum(1 for v in b_vec if abs(v) > 1e-10)
    print(f"\n{action}:")
    print(f"  Length: {len(b_vec)}")
    print(f"  Non-zero elements: {non_zero}")
    print(f"  First 3 values: {b_vec[:3]}")
    print(f"  Sum: {sum(b_vec):.6f}")

print("\n" + "=" * 70)
print("A MATRICES (context covariance)")
print("=" * 70)

for action in policy["actions"]:
    A_mat = policy["A"][action]
    print(f"\n{action}:")
    print(f"  Shape: {len(A_mat)}x{len(A_mat[0])}")
    print(f"  Trace (sum of diagonal): {sum(A_mat[i][i] for i in range(len(A_mat))):.2f}")

print("\n" + "=" * 70)
print("DIAGNOSIS")
print("=" * 70)

all_b_zero = all(all(abs(v) < 1e-10 for v in policy["b"][a]) for a in policy["actions"])

if all_b_zero:
    print("\nPROBLEM: All b vectors are ZERO.")
    print("  This can make scores identical / untrained.")
    print("  Check: reward_simulator.py, feature_builder.py, drift event JSON for training.")
else:
    print("\nOK: b vectors have non-zero values (policy appears trained).")
    print("  If API scores still look wrong, verify it loads this policy path.")
