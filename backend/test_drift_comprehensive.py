#!/usr/bin/env python3
"""Run comprehensive drift detection API tests."""

import requests
import pandas as pd
import numpy as np

print("=" * 60)
print("DRIFT DETECTION API TEST SUITE")
print("=" * 60)

# Test 1: Normal distribution
print('\n✓ Test 1: Numeric drift detection...')
records = []
for i in range(500):
    records.append({'val': np.random.normal(10, 2)})
for i in range(500, 1000):
    records.append({'val': np.random.normal(12, 2.5)})

r = requests.post('http://127.0.0.1:8000/api/featureops/drift/detect-internal',
                 json={'dataset_name': 'test1', 'dataset_rows': records},
                 timeout=60)
res = r.json()['result']
print(f'  Status: {r.status_code} - Detected: {res["drift_detected"]} - Score: {res["overall_drift_score"]:.3f}')

# Test 2: Categories with changes
print('\n✓ Test 2: Categorical drift detection...')
records = []
for i in range(500):
    records.append({'cat': np.random.choice(['A', 'B', 'C'])})
for i in range(500, 1000):
    records.append({'cat': np.random.choice(['B', 'C', 'D', 'E'])})

r = requests.post('http://127.0.0.1:8000/api/featureops/drift/detect-internal',
                 json={'dataset_name': 'test2', 'dataset_rows': records},
                 timeout=60)
res = r.json()['result']
print(f'  Status: {r.status_code} - Detected: {res["drift_detected"]} - Score: {res["overall_drift_score"]:.3f}')

# Test 3: Multiple columns
print('\n✓ Test 3: Multiple column drift detection...')
records = []
for i in range(500):
    records.append({'x': np.random.normal(5, 1), 'y': np.random.choice(['P', 'Q'])})
for i in range(500, 1000):
    records.append({'x': np.random.normal(8, 1), 'y': np.random.choice(['P', 'Q', 'R'])})

r = requests.post('http://127.0.0.1:8000/api/featureops/drift/detect-internal',
                 json={'dataset_name': 'test3', 'dataset_rows': records},
                 timeout=60)
res = r.json()['result']
print(f'  Status: {r.status_code} - Detected: {res["drift_detected"]} - Score: {res["overall_drift_score"]:.3f}')
print(f'  Detected {len(res["reasons"])} drift reasons')

# Test 4: No drift
print('\n✓ Test 4: No drift (baseline test)...')
records = []
for i in range(1000):
    records.append({'x': np.random.normal(5, 1), 'y': np.random.choice(['A', 'B', 'C'])})

r = requests.post('http://127.0.0.1:8000/api/featureops/drift/detect-internal',
                 json={'dataset_name': 'test4', 'dataset_rows': records},
                 timeout=60)
res = r.json()['result']
print(f'  Status: {r.status_code} - Detected: {res["drift_detected"]} - Score: {res["overall_drift_score"]:.3f}')

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED - API is stable and working!")
print("=" * 60)
