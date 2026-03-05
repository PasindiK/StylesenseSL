# scripts/01_upload_to_bronze.py

# allow running this file directly (python scripts/s01_upload_to_bronze.py)
# by ensuring the project root is on sys.path so that `from scripts...` imports work
if __name__ == "__main__" and __package__ is None:
    import os, sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

import os
import sys
import runpy
import json
import pandas as pd
from datetime import datetime
# Delay importing SparkSession until we know Java is available (Windows compatibility)
import shutil

from scripts.logger import setup_logger
from scripts.dq_checks import DataQualityValidator
from scripts.schema_drift import handle_schema_drift

logger = setup_logger(__name__)

class BronzeUploader:
    """Upload CSV files to Bronze Layer + Schema Drift + Cleaned Silver Conversion"""

    def __init__(self, local_data_path='data'):
        self.local_data_path = local_data_path
        self.bronze_path = 'bronze/raw'

        # Ensure directory exists
        os.makedirs(self.bronze_path, exist_ok=True)

        # Spark session — only attempt to start if explicitly enabled (avoid Windows/Java hangs)
        enable_spark = os.environ.get("ENABLE_SPARK", "false").lower() in ("1", "true", "yes")
        if not enable_spark:
            self.spark = None
            logger.info("PySpark disabled by default. Set ENABLE_SPARK=1 to enable Spark startup.")
        else:
            # Quick Java availability check
            java_ok = False
            try:
                import subprocess
                proc = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                java_ok = proc.returncode == 0 or b"java version" in proc.stderr.lower() or b"openjdk" in proc.stderr.lower()
            except Exception:
                java_ok = False

            if not java_ok:
                self.spark = None
                logger.warning("Java runtime not found or not responding; skipping PySpark startup.")
            else:
                try:
                    # Import here to avoid import-time side-effects on platforms without Java
                    from pyspark.sql import SparkSession

                    self.spark = (
                        SparkSession.builder
                        .master("local[*]")
                        .appName("lakehouse-bronze-uploader")
                        .config("spark.ui.enabled", "false")
                        .getOrCreate()
                    )
                    logger.info("SparkSession initialized")
                except Exception as e:
                    self.spark = None
                    logger.warning(f"PySpark unavailable or failed to start: {e}. Falling back to pandas-only flow.")

    # -------------------------------------------------------------------------
    # SAFE METHOD TO RUN s02_bronze_to_silver_cleaned.py
    # -------------------------------------------------------------------------
    def _trigger_bronze_to_silver(self, table_name, bronze_file_path, dq_result, drift_result):

        script_path = os.path.join("scripts", "s02_bronze_to_silver_cleaned.py")

        if not os.path.exists(script_path):
            logger.error(f"Converter script missing: {script_path}")
            return False

        try:
            logger.info(f"Running converter script via runpy for {bronze_file_path}")

            runpy.run_path(script_path, run_name="__main__", init_globals={
                "INPUT_FILE": bronze_file_path,
                "TABLE_NAME": table_name,
                "DQ_RESULT": dq_result,
                "SCHEMA_DRIFT_RESULT": drift_result
            })

            logger.info(f"Conversion complete for {bronze_file_path}")
            return True

        except Exception as e:
            logger.exception(f"Conversion failed: {e}")
            return False

    # -------------------------------------------------------------------------
    def load_csv_to_bronze(self, csv_filename):
        """Load CSV -> Add metadata -> Save to Bronze -> Run DQ -> Drift -> Convert to Silver"""

        try:
            csv_path = os.path.join(self.local_data_path, csv_filename)
            df = pd.read_csv(csv_path)

            # Metadata
            df['_ingestion_ts'] = datetime.now()
            df['_source_file'] = csv_filename
            df['_ingestion_date'] = datetime.now().date()

            # Table name normalization
            table_name = (
                csv_filename.replace('_dataset.csv', '')
            ).replace(
                'synthetic_outerwear_sri_lanka_with_shop_ids', 'products'
            ).replace(
                'transactions_dataset', 'transactions'
            ).replace(
                'users_dataset', 'users'
            )

            # Save to bronze
            bronze_file_path = os.path.join(self.bronze_path, f"{table_name}_raw.csv")
            df.to_csv(bronze_file_path, index=False)

            logger.info(f"{table_name}: loaded {len(df)} rows to bronze")

            # ----------------------------
            # DQ CHECKS
            # ----------------------------
            validator = DataQualityValidator(df, table_name)
            dq_result = validator.run_checks()  # new method returning structured hard/soft checks

            # Save DQ results to metadata
            dq_metadata_path = os.path.join("metadata", "dq_results",
                                            f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            os.makedirs(os.path.dirname(dq_metadata_path), exist_ok=True)
            with open(dq_metadata_path, "w") as f:
                json.dump(dq_result, f, default=str, indent=2)

            if not dq_result['is_acceptable']:
                logger.error(f"Hard DQ failures: {dq_result['hard_failures']}")

            if dq_result['soft_warnings']:
                logger.warning(f"Soft DQ warnings: {dq_result['soft_warnings']}")

            # ----------------------------
            # SCHEMA DRIFT CHECKS
            # ----------------------------
            if self.spark is not None:
                try:
                    spark_df = self.spark.read.option("header", "true").csv(bronze_file_path)

                    drift_result = handle_schema_drift(
                        self.spark, table_name, spark_df, csv_filename, bronze_file_path
                    )
                except Exception as e:
                    logger.exception(f"Schema drift check failed: {e}")
                    drift_result = {"status": "DRIFT_CHECK_ERROR", "reason": str(e)}
            else:
                # PySpark not available — provide a safe default drift result
                drift_result = {"status": "NO_SPARK", "reason": "pyspark_unavailable"}

            logger.info(f"Schema drift for {csv_filename}: {drift_result}")

            status = drift_result.get("status", "UNKNOWN")

            # ----------------------------
            # COMBINE DQ + DRIFT STATUS
            # ----------------------------
            if not dq_result['is_acceptable']:
                status = "ALERT"

            # ----------------------------
            # DECISION FLOW
            # ----------------------------
            if status == "ALERT":
                # Quarantine file
                quarantine_dir = os.path.join("bronze", "quarantine", datetime.now().strftime("%Y%m%d"))
                os.makedirs(quarantine_dir, exist_ok=True)
                quarantined_path = os.path.join(quarantine_dir, os.path.basename(bronze_file_path))
                try:
                    # Use replace to avoid FileExistsError on Windows if target already exists
                    if os.path.exists(quarantined_path):
                        os.replace(bronze_file_path, quarantined_path)
                    else:
                        os.rename(bronze_file_path, quarantined_path)
                except Exception as move_err:
                    logger.exception(f"Failed to move file to quarantine: {move_err}")
                    # attempt a best-effort copy+remove
                    try:
                        import shutil
                        shutil.copy2(bronze_file_path, quarantined_path)
                        os.remove(bronze_file_path)
                    except Exception:
                        logger.exception("Quarantine fallback failed")

                logger.error(f"Schema ALERT or DQ hard failures: {drift_result}. File moved to quarantine: {quarantined_path}")
                return df, table_name, drift_result

            elif status in ("REVIEW", "REQUIRES_MANUAL_REVIEW", "NEW_COLUMNS_REQUIRES_REVIEW"):
                logger.warning(f"Schema REVIEW needed: {drift_result}")
                return df, table_name, drift_result

            elif status in ("OK", "AUTO_ACCEPT"):
                # Convert to Silver
                success = self._trigger_bronze_to_silver(table_name, bronze_file_path, dq_result, drift_result)
                if not success:
                    logger.warning(f"Failed Bronze->Silver conversion for {bronze_file_path}")
                return df, table_name, drift_result

            else:
                logger.warning(f"Unknown schema drift status: {status}")
                return df, table_name, drift_result

        except Exception as e:
            logger.exception(f"Error loading CSV '{csv_filename}': {e}")
            return None, None, None

    # -------------------------------------------------------------------------
    def upload_all_datasets(self):
        print("UPLOADING ALL DATASETS -> BRONZE LAYER")

        csv_files = [
            'synthetic_outerwear_sri_lanka_with_shop_ids.csv',
            'users_dataset.csv',
            'user_preferences_dataset.csv',
            'interactions_dataset.csv',
            'transactions_dataset.csv',
            'trends_dataset.csv',
            'shops_dataset.csv',
            'domain_health_history.csv'
        ]

        success = 0

        for csv_file in csv_files:
            df, table_name, result = self.load_csv_to_bronze(csv_file)
            if df is not None:
                success += 1

        print(f"UPLOAD COMPLETE -> {success}/{len(csv_files)} datasets")
        logger.info("Bronze upload completed")


# MAIN
if __name__ == "__main__":
    import sys
    import traceback

    try:
        print("DEBUG: sys.executable=", sys.executable)
        print("DEBUG: cwd=", os.getcwd())
        print("DEBUG: files in cwd=", os.listdir('.'))

        uploader = BronzeUploader(local_data_path='data')
        uploader.upload_all_datasets()

    except Exception as e:
        print("ERROR: Exception in s01_upload_to_bronze:")
        traceback.print_exc()
        # Re-raise to preserve non-zero exit code
        raise
