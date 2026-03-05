import os
import json
import pandas as pd
from datetime import datetime

SILVER_CLEANED_DIR = "silver/cleaned"
SILVER_ENRICHED_DIR = "silver/enriched"
REPORTS_DIR = "reports"

os.makedirs(REPORTS_DIR, exist_ok=True)

def validate_file(file_path):
    """Validate a file and return metrics"""
    df = pd.read_csv(file_path)
    
    metrics = {
        "file_name": os.path.basename(file_path),
        "record_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "null_count": int(df.isnull().sum().sum()),
        "null_ratio": float(df.isnull().sum().sum() / (len(df) * len(df.columns))),
        "duplicate_count": int(df.duplicated().sum()),
        "memory_mb": float(df.memory_usage(deep=True).sum() / 1024 / 1024),
        "quality_score": int(100 * (1 - (df.isnull().sum().sum() / (len(df) * len(df.columns)))))
    }
    
    return metrics

def run_validation():
    """Validate all layers"""
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "layers": {
            "silver_cleaned": [],
            "silver_enriched": []
        }
    }
    
    print("\n" + "="*70)
    print("DATA QUALITY VALIDATION REPORT")
    print("="*70)
    
    # Validate cleaned
    print("\nSILVER CLEANED LAYER:")
    print("-" * 70)
    for fname in os.listdir(SILVER_CLEANED_DIR):
        if fname.endswith(".csv"):
            path = os.path.join(SILVER_CLEANED_DIR, fname)
            metrics = validate_file(path)
            report["layers"]["silver_cleaned"].append(metrics)
            print(f"{fname}:")
            print(f"  Records: {metrics['record_count']}")
            print(f"  Columns: {metrics['column_count']}")
            print(f"  Nulls: {metrics['null_count']} ({metrics['null_ratio']*100:.1f}%)")
            print(f"  DQ Score: {metrics['quality_score']}/100")
    
    # Validate enriched
    print("\nSILVER ENRICHED LAYER:")
    print("-" * 70)
    for fname in os.listdir(SILVER_ENRICHED_DIR):
        if fname.endswith(".csv"):
            path = os.path.join(SILVER_ENRICHED_DIR, fname)
            metrics = validate_file(path)
            report["layers"]["silver_enriched"].append(metrics)
            print(f"{fname}:")
            print(f"  Records: {metrics['record_count']}")
            print(f"  Columns: {metrics['column_count']}")
            print(f"  Nulls: {metrics['null_count']} ({metrics['null_ratio']*100:.1f}%)")
            print(f"  DQ Score: {metrics['quality_score']}/100")
    
    # Summary
    total_records = sum(m['record_count'] for m in report['layers']['silver_enriched'])
    avg_quality = sum(m['quality_score'] for m in report['layers']['silver_enriched']) / len(report['layers']['silver_enriched'])
    
    print("\n" + "="*70)
    print("SUMMARY:")
    print(f"  Total Records: {total_records}")
    print(f"  Average DQ Score: {avg_quality:.1f}/100")
    print(f"  Status: {'PASS' if avg_quality >= 95 else 'WARNING'}")
    print("="*70 + "\n")
    
    # Save report
    report_path = os.path.join(REPORTS_DIR, f"dq_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved: {report_path}")
    return report

if __name__ == "__main__":
    run_validation()