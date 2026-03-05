import argparse
import json
from pathlib import Path

from src.services.agentic_ai.kg.pipeline import KGEndToEndPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end KG pipeline phases")
    parser.add_argument("--with-bootstrap", action="store_true", help="Run schema + historical bootstrap")
    parser.add_argument("--user-id", default="1", help="User ID for phase-4 event simulation")
    parser.add_argument("--query", default="casual blue outfits", help="Sample search query for phase-4")
    args = parser.parse_args()

    data_root = Path(__file__).resolve().parents[4] / "data" / "raw"
    pipeline = KGEndToEndPipeline(data_root=data_root)

    result = {
        "phase_1": pipeline.phase_1_setup(),
        "components": pipeline.component_catalog(),
    }

    if args.with_bootstrap:
        result["phase_2"] = pipeline.phase_2_schema()
        result["phase_3"] = pipeline.phase_3_bootstrap()

    result["phase_4"] = pipeline.phase_4_online_update(
        user_id=args.user_id,
        query=args.query,
        preference={"type": "style", "value": "Casual"},
    )
    result["graph_stats"] = pipeline.smoke_graph_stats()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
