#!/usr/bin/env python3
"""Detailed test of drift detection API with full JSON output."""

import requests
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

# Create a synthetic dataset with clear drift
np.random.seed(42)
records = []

# First half: baseline distribution
for i in range(500):
    records.append({
        'record_id': f'R{i:04d}',
        'timestamp': (datetime(2026, 1, 1) + timedelta(hours=i)).isoformat(),
        'product_id': f'P{np.random.randint(1, 50):03d}',
        'quality_score': np.random.normal(3.0, 1.1),  # Mean 3.0, std 1.1
        'score_source': 'legacy_1_to_5_rating',
        'price': np.random.normal(100, 20),
        'category': np.random.choice(['apparel', 'accessories', 'footwear']),
    })

# Second half: drift - quality_score changes, new score_source appears
for i in range(500, 1000):
    # Quality score drops (statistical drift)
    quality = np.random.normal(2.5, 1.3)  # Lower mean, higher variance
    
    # 90% of the time use old source, 10% use new source (semantic drift)
    if np.random.random() < 0.9:
        score_source = 'legacy_1_to_5_rating'
    else:
        score_source = 'new_0_to_1_normalized_score'
        quality = quality / 5.0  # Scale down for new source
    
    records.append({
        'record_id': f'R{i:04d}',
        'timestamp': (datetime(2026, 1, 1) + timedelta(hours=i)).isoformat(),
        'product_id': f'P{np.random.randint(1, 55):03d}',  # New products introduced
        'quality_score': quality,
        'score_source': score_source,
        'price': np.random.normal(105, 25),  # Slight price increase
        'category': np.random.choice(['apparel', 'accessories', 'footwear', 'new_category']),
    })

df = pd.DataFrame(records)
print(f"Testing drift detection with {len(df)} rows")

# Convert to list of dicts for JSON serialization
dataset_rows = df.to_dict('records')

# Prepare request payload
payload = {
    "dataset_name": "test_drift_dataset",
    "dataset_rows": dataset_rows,
}

# Call the API
print("Calling POST /api/featureops/drift/detect-internal...")
try:
    response = requests.post(
        'http://127.0.0.1:8000/api/featureops/drift/detect-internal',
        json=payload,
        timeout=60
    )
    
    print(f"Response Status: {response.status_code}\n")
    
    if response.status_code == 200:
        result = response.json()
        print("✅ SUCCESS! Full JSON response:")
        print(json.dumps(result, indent=2))
    else:
        print(f"❌ Error {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
