from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass(frozen=True)
class KGComponent:
    name: str
    purpose: str
    inputs: str
    outputs: str


def get_kg_component_catalog() -> List[Dict[str, str]]:
    components = [
        KGComponent(
            name="KGConfig",
            purpose="Reads runtime switches and Neo4j connection configuration.",
            inputs="Environment variables",
            outputs="Validated KG runtime config",
        ),
        KGComponent(
            name="Neo4jKGClient",
            purpose="Manages Neo4j connectivity and query execution with fail-safe behavior.",
            inputs="Cypher + params",
            outputs="Query results / write side effects",
        ),
        KGComponent(
            name="KGBootstrapLoader",
            purpose="Creates schema and imports historical users/products/preferences/interactions.",
            inputs="Raw CSV datasets",
            outputs="Bootstrapped knowledge graph",
        ),
        KGComponent(
            name="KGEventWriter",
            purpose="Writes live user events like search, recommendation impressions, and preferences.",
            inputs="Runtime user actions",
            outputs="Updated edge counts, recency timestamps, and preferences",
        ),
        KGComponent(
            name="KGScoringService",
            purpose="Calculates graph relevance for product candidates per user.",
            inputs="user_id + candidate products + intent",
            outputs="graph_score + graph_reasons per product",
        ),
        KGComponent(
            name="PersonalizationAgent",
            purpose="Combines graph score with intent/profile/price/popularity signals for final ranking.",
            inputs="Catalog candidates + KG scores",
            outputs="Ranked recommendations with reasons",
        ),
    ]
    return [asdict(c) for c in components]
