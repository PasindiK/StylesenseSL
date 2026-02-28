"""PHASE 5 demo: Virtual integration with intelligent relationship discovery."""

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ingestion.folder_scanner import AutoDataLoader
from src.integration.virtual_integration import VirtualIntegrationLayer


def main() -> int:
    data_path = r"c:\Users\Molex Technologies\OneDrive - Sri Lanka Institute of Information Technology\Research\Data Fabric\raw-data copy"

    loader = AutoDataLoader(data_path)
    registry = loader.load_all_datasets(enable_preprocessing=True)

    datasets = {
        name: registry.get_dataset(name)
        for name in registry.list_datasets()
        if registry.get_dataset(name) is not None
    }

    integration = VirtualIntegrationLayer(metadata_catalog=loader.metadata_catalog)

    relationships = integration.infer_relationships(datasets, register_results=True)
    print(f"Inferred relationships (strong+probable): {len(relationships)}")

    top = relationships[:10]
    for rel in top:
        print(
            f"- {rel.left_dataset}.{rel.left_column} <-> {rel.right_dataset}.{rel.right_column} "
            f"| confidence={rel.confidence:.3f} decision={rel.decision} cardinality={rel.cardinality}"
        )

    joined_df, rel = integration.join_on_demand(
        datasets=datasets,
        left_dataset="transactions10K",
        right_dataset="users_dataset",
        output_dataset="virtual_transactions_users",
    )

    print("\nCreated derived dataset: virtual_transactions_users")
    print(f"Join confidence: {rel.confidence:.3f} ({rel.decision})")
    print(f"Joined rows: {len(joined_df)}")

    impact = integration.get_impact_analysis("users_dataset")
    print("\nImpact analysis for users_dataset:")
    print(impact)

    derived_meta = loader.metadata_catalog.get_dataset("virtual_transactions_users")
    if derived_meta:
        print("\nDerived metadata summary:")
        print(
            {
                "dataset_name": derived_meta.get("dataset_name"),
                "producer_pipeline": derived_meta.get("producer_pipeline"),
                "validation_status": derived_meta.get("validation_status"),
                "quality_score": derived_meta.get("quality_score"),
                "upstream_datasets": derived_meta.get("upstream_datasets"),
                "downstream_datasets": derived_meta.get("downstream_datasets"),
            }
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
