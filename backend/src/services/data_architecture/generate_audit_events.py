#!/usr/bin/env python
"""Generate realistic governance audit events."""
import os
import json
from datetime import datetime, timedelta
import random

AUDIT_LOG_PATH = os.path.join("pipeline", "metadata", "audit_logs", "audit_log.jsonl")
os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)

# Governance event types and stakeholders
EVENT_TYPES = [
    "data_access",
    "policy_violation",
    "access_request",
    "data_export",
    "schema_change",
    "retention_policy_applied",
    "compliance_check",
    "user_onboarding",
    "permission_grant",
    "permission_revoke",
]

STAKEHOLDERS = [
    "fabric_component",
    "mesh_node",
    "agentic_ai",
    "analytics_user",
    "data_engineer",
    "analyst",
    "business_user",
]

STATUSES = [
    "approved",
    "denied",
    "pending",
    "completed",
    "failed",
    "unauthorized",
    "compliant",
    "review_needed",
]

USERS = [
    "priya@stylesense.ai",
    "rajesh@stylesense.ai",
    "amaya@stylesense.ai",
    "deepak@stylesense.ai",
    "sanjana@stylesense.ai",
    "nimal@stylesense.ai",
    "system-service",
    "scheduler",
]

PROVINCES = [
    "Western",
    "Central",
    "Southern",
    "Northern",
    "North Central",
    "North Western",
    "Eastern",
    "Uva",
    "Sabaragamuwa",
]

# Generate events for the last 7 days
events = []
base_time = datetime.utcnow() - timedelta(days=7)

for i in range(200):  # 200 audit events
    hours_ago = random.randint(0, 7 * 24)
    event_time = base_time + timedelta(hours=hours_ago, minutes=random.randint(0, 59))
    
    event_type = random.choice(EVENT_TYPES)
    stakeholder = random.choice(STAKEHOLDERS)
    status = random.choice(STATUSES)
    user = random.choice(USERS)
    province = random.choice(PROVINCES)
    
    # Determine details based on event type
    if event_type == "data_access":
        dataset = random.choice(["products", "users", "transactions", "orders", "inventory"])
        details = {
            "dataset": dataset,
            "stakeholder_type": stakeholder,
            "region": province,
            "province": province,
            "tables_accessed": random.randint(1, 5),
            "rows_read": random.randint(100, 1000000),
        }
    elif event_type == "policy_violation":
        details = {
            "violation_type": random.choice(["unauthorized_access", "data_export", "retention_breach"]),
            "severity": random.choice(["low", "medium", "high"]),
            "stakeholder": stakeholder,
            "region": province,
            "province": province,
        }
    elif event_type == "access_request":
        details = {
            "requester": user,
            "requested_datasets": random.randint(1, 3),
            "stakeholder_type": stakeholder,
            "region": province,
            "province": province,
            "business_justification": random.choice([
                "Data analysis",
                "ML training",
                "Reporting",
                "Compliance audit",
                "Operational monitoring",
            ]),
        }
    elif event_type == "compliance_check":
        details = {
            "check_type": random.choice(["retention", "encryption", "access_control", "data_quality"]),
            "result": status,
            "datasets_checked": random.randint(5, 20),
            "issues_found": random.randint(0, 5),
            "province": province,
        }
    else:
        details = {
            "stakeholder_type": stakeholder,
            "user": user,
            "region": province,
            "province": province,
            "resource": random.choice(["dataset_1", "dataset_2", "view_1", "catalog"]),
        }
    
    event = {
        "timestamp": event_time.isoformat() + "Z",
        "event_type": event_type,
        "status": status,
        "user": user,
        "details": details,
    }
    
    events.append(event)

# Sort by timestamp descending (newest first)
events.sort(key=lambda e: e["timestamp"], reverse=True)

# Write to JSONL
with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
    for event in events:
        f.write(json.dumps(event) + "\n")

print(f"✓ Generated {len(events)} governance audit events")
print(f"✓ Saved to: {AUDIT_LOG_PATH}")
print(f"\nEvent summary:")
print(f"  Event types: {len(set(e['event_type'] for e in events))} unique")
print(f"  Stakeholders: {len(set(d['stakeholder_type'] for e in events for d in [e.get('details', {})]))}")
print(f"  Provinces: {len(set(d.get('province') for e in events for d in [e.get('details', {})]))}")
print(f"  Statuses: {set(e['status'] for e in events)}")
