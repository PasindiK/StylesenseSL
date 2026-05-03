"""Test RelationalAnchorAgent Phase 2"""
import json
from pathlib import Path
import pandas as pd
from src.services.agentic_ai.featureops.agents.profiler_agent import ProfilerAgent
from src.services.agentic_ai.featureops.agents.baseline_agent import BaselineAgent
from src.services.agentic_ai.featureops.agents.relational_anchor_agent import RelationalAnchorAgent

# Load demo data
df = pd.read_csv('test_product_demo.csv')
print(f'✓ Loaded demo data: {len(df)} rows')

# Step 1: Build profile (Phase 1)
profiler = ProfilerAgent()
profile = profiler.build_profile(df, 'demo_product_for_anchors')
print(f'✓ Profile built with {len(profile["column_profiles"])} columns')
print(f'✓ Phase 1 anchors: {len(profile["relational_anchors"])}')

# Step 2: Load baseline (Phase 1.5)
baseline_dir = Path('src/services/agentic_ai/featureops/test_baselines_phase2')
baseline_dir.mkdir(parents=True, exist_ok=True)
baseline_agent = BaselineAgent(baseline_dir)
baseline_agent.save_internal_baseline(profile)
print('✓ Baseline saved')

# Step 3: Discover anchors (Phase 2)
anchor_agent = RelationalAnchorAgent()
print('\n✓ RelationalAnchorAgent initialized (demo mode - no LLM calls)')

# Discover anchors using the profile and sample data
all_anchors = anchor_agent.discover_anchors(profile, df, numeric_threshold=0.4, text_threshold=0.6)

print(f'\n✓ Total anchors discovered (Phase 1 + Phase 2):')
for anchor in all_anchors:
    anchor_type = anchor.get('type', 'unknown')
    if anchor_type == 'numeric_correlation':
        print(f'  - {anchor["left_column"]} ↔ {anchor["right_column"]}: r={anchor["correlation_strength"]} (PHASE 1)')
    else:
        print(f'  - {anchor.get("anchor_id")}: {anchor_type} (PHASE 2)')

# Validate anchors
print('\n✓ Validating anchors on full dataset...')
validated_anchors = anchor_agent.validate_anchors(all_anchors, df)
for anchor in validated_anchors:
    status = anchor.get('validation_status', 'unknown')
    print(f'  - {anchor.get("anchor_id", "unknown")}: {status}')

print('\n✓ Phase 2 (RelationalAnchorAgent) validation complete!')
print(f'Total anchors in enhanced profile: {len(validated_anchors)}')
