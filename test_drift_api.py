"""
Test script for drift detection API
"""
import pandas as pd
import requests
import json

# Load dataset
df = pd.read_csv('semantic_internal_drift_1000_records.csv')
dataset_rows = df.to_dict('records')

print(f"Dataset: {len(dataset_rows)} rows, {len(df.columns)} columns")
print(f"Columns: {list(df.columns)}")

# Test 1: Internal drift detection
print("\n" + "="*60)
print("TEST 1: Internal Drift Detection")
print("="*60)

url = "http://127.0.0.1:8000/api/featureops/drift/detect-internal"
payload = {
    "dataset_name": "semantic_internal_drift_test",
    "dataset_rows": dataset_rows
}

try:
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Status: {result.get('status')}")
        print(f"  Drift Run ID: {result.get('drift_run_id')}")
        print(f"  Drift Detected: {result.get('drift_detected')}")
        print(f"  Severity: {result.get('severity')}")
        print(f"  Overall Score: {result.get('overall_score'):.3f}")
        
        # Show signals
        result_data = result.get('result', {})
        print(f"\n  Statistical Signals ({len(result_data.get('statistical_signals', []))} columns):")
        for sig in result_data.get('statistical_signals', [])[:3]:
            print(f"    - {sig['column_name']} ({sig['dtype']})")
            if sig.get('ks_pvalue'):
                print(f"      KS p-value: {sig['ks_pvalue']:.6f}")
            if sig.get('chi2_pvalue'):
                print(f"      Chi-square p-value: {sig['chi2_pvalue']:.6f}")
        
        print(f"\n  Reasons:")
        for reason in result.get('result', {}).get('reasons', [])[:5]:
            print(f"    - {reason}")
    else:
        print(f"✗ Error: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"✗ Connection error: {e}")
    print("Is the backend running? Run: cd c:\\Test\\backend && python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000")
