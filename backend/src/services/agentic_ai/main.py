from src.services.agentic_ai.agents.catalog_agent import CatalogAgent


def main() -> None:
    agent = CatalogAgent()
    print(f"agentic_ai_ready={agent is not None}")


if __name__ == "__main__":
    main()
