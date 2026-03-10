#!/usr/bin/env python
"""Generate synthetic drift events for policy training."""
import os
import json
from datetime import datetime, timedelta
import random

DRIFT_DIR = os.path.join("pipeline", "metadata", "drift_events")
os.makedirs(DRIFT_DIR, exist_ok=True)

# Simulate realistic drift scenarios
tables = ["products", "users", "transactions", "orders", "inventory"]
event_count = 0

base_time = datetime(2026, 1, 1, 0, 0, 0)

for table_idx, table in enumerate(tables):
    for scenario in range(5):  # 5 scenarios per table
        event_time = base_time + timedelta(days=scenario, hours=table_idx * 4)
        
        # Create varied drift scenarios
        scenario_type = scenario % 3
        
        if scenario_type == 0:  # New columns (good for auto_merge)
            diff = {
                "new_columns": ["new_feature_1", "new_feature_2"],
                "missing_columns": [],
                "dtype_changes": [],
                "renames": [],
            }
            dq_metrics = {
                "null_ratio_delta": -0.02,  # Data quality improving
                "duplicate_ratio": 0.001,
            }
        elif scenario_type == 1:  # Mixed drift (requires review)
            diff = {
                "new_columns": ["field_x"],
                "missing_columns": ["old_field"],
                "dtype_changes": ["price: int -> float"],
                "renames": [{"old_name": "user_name", "new_name": "username", "similarity": 0.92, "type_match": True}],
            }
            dq_metrics = {
                "null_ratio_delta": 0.05,  # Data quality degrading
                "duplicate_ratio": 0.015,
            }
        else:  # Minor drift (safe auto)
            diff = {
                "new_columns": ["updated_ts"],
                "missing_columns": [],
                "dtype_changes": [],
                "renames": [],
            }
            dq_metrics = {
                "null_ratio_delta": -0.01,
                "duplicate_ratio": 0.0,
            }
        
        event = {
            "timestamp": event_time.isoformat(),
            "table": table,
            "source_file": f"raw/{table}_data.csv",
            "diff": diff,
            "extra": {
                "dq_metrics": dq_metrics,
                "pipeline_meta": {
                    "downstream_failure_count": 0 if scenario_type == 0 else (1 if scenario_type == 1 else 0),
                    "avg_latency_ms": random.randint(100, 500),
                    "storage_move": random.choice(["hot", "warm"]),
                    "row_count_delta": random.randint(-1000, 5000),
                },
            },
        }
        
        fname = os.path.join(DRIFT_DIR, f"drift_{table}_{event_count:03d}.json")
        with open(fname, "w") as f:
            json.dump(event, f, indent=2)
        event_count += 1
        print(f"Created {fname}")

print(f"\nGenerated {event_count} training events in {DRIFT_DIR}")
