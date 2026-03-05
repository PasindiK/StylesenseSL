from pathlib import Path

from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.kg.bootstrap import KGBootstrapLoader


def main() -> None:
    client = Neo4jKGClient()
    data_root = Path(__file__).resolve().parents[4] / "data" / "raw"
    loader = KGBootstrapLoader(client, data_root=data_root)
    loader.run_full_bootstrap()
    print(f"kg_bootstrap_complete={client.enabled}")


if __name__ == "__main__":
    main()
