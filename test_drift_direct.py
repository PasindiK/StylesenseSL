"""Direct test of drift detection without API"""
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from src.services.agentic_ai.featureops.comprehensive_drift_detector import ComprehensiveDriftDetector

# Load dataset
df = pd.read_csv('c:\\Users\\MCS\\Downloads\\semantic_internal_drift_1000_records.csv')
dataset_rows = df.to_dict('records')

print(f"✓ Dataset loaded: {len(dataset_rows)} rows, {len(df.columns)} columns")

# Initialize detector
state_dir = Path("c:\\Test\\drift_test_state")
detector = ComprehensiveDriftDetector(state_dir)
print(f"✓ Drift detector initialized")

# Run internal drift detection
try:
    result = detector.detect_internal_drift(df, "test_dataset")
    print(f"✓ Drift detection completed")
    print(f"  Drift Run ID: {result.drift_run_id}")
    print(f"  Drift Detected: {result.drift_detected}")
    print(f"  Severity: {result.severity}")
    print(f"  Overall Score: {result.overall_drift_score:.3f}")
    print(f"  Reasons: {len(result.reasons)}")
    for i, reason in enumerate(result.reasons[:5]):
        print(f"    {i+1}. {reason}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
