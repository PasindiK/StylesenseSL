"""Test BaselineAgent with Phase 1 profile"""
import json
from pathlib import Path
from src.services.agentic_ai.featureops.agents.baseline_agent import BaselineAgent

# Create temp baseline directory
baseline_dir = Path("src/services/agentic_ai/featureops/test_baselines")
baseline_dir.mkdir(parents=True, exist_ok=True)

# Load the Phase 1 profile we just created
with open("test_product_demo_profile.json", "r") as f:
    demo_profile = json.load(f)

print("✓ Loaded demo profile")

# Initialize BaselineAgent
agent = BaselineAgent(baseline_dir)
print("✓ BaselineAgent initialized")

# Save as internal baseline
result = agent.save_internal_baseline(demo_profile)
print(f"✓ Saved internal baseline: {result['status']}")

# Retrieve metadata
metadata = agent.get_baseline_metadata()
print(f"\n✓ Baseline Metadata:")
print(f"  Internal Status: {metadata['internal']['status']}")
print(f"  Internal Dataset: {metadata['internal']['dataset_name']}")
print(f"  Internal Rows: {metadata['internal']['row_count']}")
print(f"  Internal Columns: {metadata['internal']['column_count']}")

# Get column profiles
cols = agent.get_column_profiles("internal")
print(f"\n✓ Retrieved {len(cols)} column profiles from internal baseline")
for col_name in list(cols.keys())[:3]:
    col = cols[col_name]
    print(f"  - {col_name}: {col['kind']}")

# Get relational anchors
anchors = agent.get_relational_anchors("internal")
print(f"\n✓ Retrieved {len(anchors)} relational anchors from internal baseline")
for anchor in anchors:
    print(f"  - {anchor['left_column']} ↔ {anchor['right_column']} (r={anchor['correlation_strength']})")

print("\n✓ Phase 1.5 (BaselineAgent) validation complete!")
