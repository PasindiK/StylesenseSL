"""Orchestrator to run the local medallion pipeline end-to-end.

Usage: set ENABLE_SPARK=1 (optional, requires Java) then run:
  .venv\Scripts\python.exe -m scripts.run_pipeline

The orchestrator will:
 - create layer folders
 - upload datasets to bronze (runs DQ + schema drift checks)
 - run silver enrichment for cleaned files
 - run DQ validation report
 - run gold curation, embeddings (if dependencies present), and prepare drift baseline
"""
import os
import runpy
import traceback

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
print(f"Running pipeline from base: {BASE}")

def safe_run(path, name=None, init_globals=None):
    try:
        print(f"\n--- Running: {path} ---")
        runpy.run_path(path, run_name="__main__", init_globals=(init_globals or {}))
        print(f"--- Completed: {path} ---\n")
        return True
    except Exception as e:
        print(f"Error running {path}: {e}")
        traceback.print_exc()
        return False


def main():
    # 1) Setup layers
    safe_run(os.path.join('scripts', 'setup_layers.py'))

    # 2) Upload to bronze (this will internally call s02 for OK files)
    try:
        from scripts.s01_upload_to_bronze import BronzeUploader
        uploader = BronzeUploader(local_data_path='data')
        uploader.upload_all_datasets()
    except Exception as e:
        print(f"Failed running s01 upload: {e}")
        traceback.print_exc()

    # 3) Enrich all cleaned silver files
    cleaned_dir = os.path.join('silver', 'cleaned')
    if os.path.exists(cleaned_dir):
        for fname in os.listdir(cleaned_dir):
            if not fname.endswith('_cleaned.csv'):
                continue
            input_path = os.path.join(cleaned_dir, fname)
            table = fname.replace('_cleaned.csv', '')
            init = {'INPUT_FILE': input_path, 'TABLE_NAME': table}
            safe_run(os.path.join('scripts', 's03_silver_to_enriched.py'), init_globals=init)
    else:
        print(f"No cleaned directory found at {cleaned_dir}")

    # 4) DQ validation report
    safe_run(os.path.join('scripts', 's04_dq_validation_report.py'))

    # 5) Gold curation
    safe_run(os.path.join('scripts', 's05_silver_to_gold_curated.py'))

    # 6) Embeddings (may require extra deps)
    safe_run(os.path.join('scripts', 's06_generate_embeddings.py'))

    # 7) Prepare drift baseline
    safe_run(os.path.join('scripts', 's07_prepare_drift_baseline.py'))

    print('\nPipeline run complete.')


if __name__ == '__main__':
    main()
