import json

with open('test_product_demo_profile.json', 'r') as f:
    profile = json.load(f)

print('=== SEMANTIC PROFILE STRUCTURE ===\n')
print(f'Dataset: {profile["metadata"]["dataset_name"]}')
print(f'Rows: {profile["metadata"]["row_count"]}, Columns: {profile["metadata"]["column_count"]}')

print(f'\n=== COLUMN PROFILES ({len(profile["column_profiles"])}) ===')
for col in profile['column_profiles']:
    stats = col.get('numeric_stats') or col.get('categorical_stats', {})
    print(f'  {col["column_name"]}: {col["kind"]} (non_null: {col["statistics"]["non_null_count"]})')
    if col['kind'] == 'numeric':
        print(f'    Mean: {stats.get("mean"):.2f}, Std: {stats.get("std"):.2f}, Scale: {col.get("scale_pattern")}')

print(f'\n=== RELATIONAL ANCHORS ({len(profile["relational_anchors"])}) ===')
for anchor in profile['relational_anchors']:
    print(f'  {anchor["left_column"]} ↔ {anchor["right_column"]}: r={anchor["correlation_strength"]}')

print(f'\n=== SUMMARY ===')
print(f'Text: {profile["summary"]["text"]}')
print(f'Signature: {profile["summary"]["signature"]}')
