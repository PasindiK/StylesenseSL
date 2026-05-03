"""Quick test of ProfilerAgent Phase 1"""
from pathlib import Path
import pandas as pd
import json
from src.services.agentic_ai.featureops.agents.profiler_agent import ProfilerAgent

# Load demo dataset
df = pd.read_csv('test_product_demo.csv')
print(f'✓ Loaded test_product_demo.csv: {len(df)} rows, {len(df.columns)} columns')

# Initialize profiler
profiler = ProfilerAgent()
print('✓ ProfilerAgent initialized')

# Build profile
profile = profiler.build_profile(df, 'demo_product_dataset')
print(f'✓ Profile built')
print(f'  - Columns profiled: {len(profile["column_profiles"])}')
print(f'  - Relational anchors discovered: {len(profile["relational_anchors"])}')
print(f'  - Dataset summary: {profile["summary"]["text"][:120]}...')

# Check structure
print('\n✓ Profile structure:')
for col in profile['column_profiles']:
    print(f"  - {col['column_name']} ({col['kind']})")

# Save profile
output_path = Path('test_product_demo_profile.json')
with open(output_path, 'w') as f:
    json.dump(profile, f, indent=2)
print(f'\n✓ Profile saved to {output_path}')

print('\n✓ Phase 1 validation complete! ProfilerAgent works standalone.')
