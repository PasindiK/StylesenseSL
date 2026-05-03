#!/usr/bin/env python3
"""Test drift detection API and show summary."""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Create a synthetic dataset with clear drift
np.random.seed(42)
records = []

# First half: baseline distribution
for i in range(500):
    records.append({
        'quality_score': np.random.normal(3.0, 1.1),
        'price': np.random.normal(100, 20),
        'category': np.random.choice(['A', 'B', 'C']),
    })

# Second half: drift
for i in range(500, 1000):
    records.append({
        'quality_score': np.random.normal(2.5, 1.3),  # Different mean/std
        'price': np.random.normal(105, 25),
        'category': np.random.choice(['A', 'B', 'C', 'D']),  # New category
    })

df = pd.DataFrame(records)

# Call API
response = requests.post(
    'http://127.0.0.1:8000/api/featureops/drift/detect-internal',
    json={"dataset_name": "test", "dataset_rows": df.to_dict('records')},
    timeout=60
)

if response.status_code == 200:
    result = response.json()
    res = result.get('result', {})
    print(f"✅ API Status: {response.status_code}")
    print(f"Drift Detected: {res.get('drift_detected')}")
    print(f"Severity: {res.get('severity')}")
    print(f"Overall Score: {res.get('overall_drift_score'):.3f}")
    print(f"Reasons Count: {len(res.get('reasons', []))}")
    print(f"Reasons: {res.get('reasons', [])}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text[:500])
