from src.services.agentic_ai.agents.catalog_agent import CatalogAgent
from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.kg.config import KGConfig
from src.services.agentic_ai.kg.bootstrap import KGBootstrapLoader
from pathlib import Path


def main() -> None:
    kg_config = KGConfig.from_env()
    kg_client = Neo4jKGClient(kg_config)
    if kg_config.bootstrap_on_start and kg_client.enabled:
        data_root = Path(__file__).resolve().parents[3] / "data" / "raw"
        KGBootstrapLoader(kg_client, data_root=data_root).run_full_bootstrap()
    agent = CatalogAgent()
    print(f"agentic_ai_ready={agent is not None};kg_enabled={kg_client.enabled}")


if __name__ == "__main__":
    main()
