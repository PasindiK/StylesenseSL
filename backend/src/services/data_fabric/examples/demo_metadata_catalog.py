"""Metadata Catalog demo for Data Fabric PHASE 4.

Demonstrates:
- Dataset registration/upsert
- Consumer tracking with wrapped loader
- Lineage registration
- Query APIs
- Health report and export
"""

from pathlib import Path
from pprint import pprint
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.metadata.catalog import MetadataCatalog


def main() -> int:
    base_dir = BASE_DIR
    db_path = base_dir / "src" / "metadata" / "metadata_catalog_demo.db"
    export_path = base_dir / "processed-data" / "metadata_catalog_summary.json"

    catalog = MetadataCatalog(db_path=str(db_path))

    # 1) Sample dataset registration
    catalog.upsert_dataset(
        dataset_name="users_dataset",
        domain="Customers",
        schema={"user_id": "int", "name": "string", "email": "string"},
        row_count=525,
        producer_pipeline="ingestion.auto_data_loader",
        validation_status="Passed",
        quality_score=92.5,
        description="User master data",
        owner="data-platform",
        source_system="csv",
        location="raw-data/users_dataset.csv",
        tags=["customers", "pii"],
    )

    catalog.upsert_dataset(
        dataset_name="transactions_dataset",
        domain="Orders",
        schema={"transaction_id": "int", "user_id": "int", "amount": "float"},
        row_count=9458,
        producer_pipeline="ingestion.auto_data_loader",
        validation_status="Failed",
        quality_score=61.0,
        description="Order transaction facts",
        owner="data-platform",
        source_system="csv",
        location="raw-data/transactions.csv",
        tags=["orders", "finance"],
    )

    # 2) Consumer tracking demonstration
    def _dummy_loader(dataset_name: str):
        return {"dataset_name": dataset_name, "status": "loaded"}

    catalog.load_dataset_with_tracking("users_dataset", "PowerBI_SalesDashboard", loader_fn=_dummy_loader)
    catalog.load_dataset_with_tracking("users_dataset", "recommendation_model_v1", loader_fn=_dummy_loader)
    catalog.load_dataset_with_tracking("transactions_dataset", "fraud_detection_model", loader_fn=_dummy_loader)

    # 3) Lineage registration example
    catalog.register_lineage(
        input_datasets=["users_dataset", "transactions_dataset"],
        output_dataset="customer_ltv_dataset",
    )

    # Register derived dataset so lineage queries are meaningful
    catalog.upsert_dataset(
        dataset_name="customer_ltv_dataset",
        domain="Analytics",
        schema={"user_id": "int", "ltv": "float"},
        row_count=500,
        producer_pipeline="pipeline.customer_ltv",
        validation_status="Warning",
        quality_score=78.0,
        description="Derived customer LTV table",
        owner="analytics-team",
        source_system="pipeline",
        location="gold/customer_ltv",
        tags=["analytics"],
    )

    # Query API examples
    print("\n=== get_dataset(users_dataset) ===")
    pprint(catalog.get_dataset("users_dataset"))

    print("\n=== get_datasets_by_domain(Customers) ===")
    pprint(catalog.get_datasets_by_domain("Customers"))

    print("\n=== get_datasets_by_producer(ingestion.auto_data_loader) ===")
    pprint(catalog.get_datasets_by_producer("ingestion.auto_data_loader"))

    print("\n=== get_datasets_by_consumer(PowerBI_SalesDashboard) ===")
    pprint(catalog.get_datasets_by_consumer("PowerBI_SalesDashboard"))

    print("\n=== list_stale_datasets(0) ===")
    pprint(catalog.list_stale_datasets(0))

    print("\n=== list_failed_validation_datasets() ===")
    pprint(catalog.list_failed_validation_datasets())

    print("\n=== get_downstream_dependencies(users_dataset) ===")
    pprint(catalog.get_downstream_dependencies("users_dataset"))

    print("\n=== generate_catalog_health_report() ===")
    pprint(catalog.generate_catalog_health_report(stale_threshold_days=30))

    summary = catalog.export_catalog_summary(str(export_path))
    print("\n=== export_catalog_summary() ===")
    print(f"Exported {summary['total_assets']} assets to: {export_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
