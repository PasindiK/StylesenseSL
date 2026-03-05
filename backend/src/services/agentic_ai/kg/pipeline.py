from pathlib import Path
from typing import Dict, Any, Optional

from .config import KGConfig
from .client import Neo4jKGClient
from .bootstrap import KGBootstrapLoader
from .events import KGEventWriter
from .scoring import KGScoringService
from .component_catalog import get_kg_component_catalog


class KGEndToEndPipeline:
    def __init__(self, data_root: Optional[Path] = None):
        self.config = KGConfig.from_env()
        self.client = Neo4jKGClient(self.config)
        self.data_root = data_root
        self.bootstrap_loader = None
        if data_root is not None:
            self.bootstrap_loader = KGBootstrapLoader(self.client, data_root=data_root)
        self.event_writer = KGEventWriter(self.client)
        self.scoring = KGScoringService(self.client)

    def phase_1_setup(self) -> Dict[str, Any]:
        return {
            "phase": "phase_1_setup",
            "kg_enabled": self.config.enabled,
            "neo4j_uri": self.config.uri,
            "connected": self.client.enabled,
        }

    def phase_2_schema(self) -> Dict[str, Any]:
        if not self.bootstrap_loader:
            return {"phase": "phase_2_schema", "ok": False, "reason": "data_root_not_provided"}
        self.bootstrap_loader.create_schema()
        return {"phase": "phase_2_schema", "ok": True}

    def phase_3_bootstrap(self) -> Dict[str, Any]:
        if not self.bootstrap_loader:
            return {"phase": "phase_3_bootstrap", "ok": False, "reason": "data_root_not_provided"}
        self.bootstrap_loader.run_full_bootstrap()
        return {"phase": "phase_3_bootstrap", "ok": True}

    def phase_4_online_update(self, user_id: str, query: str, preference: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self.event_writer.record_search(user_id=user_id, query=query, intent={})
        if preference and preference.get("type") and preference.get("value"):
            self.event_writer.record_user_preference(
                user_id=user_id,
                preference_type=str(preference["type"]),
                value=str(preference["value"]),
                weight=1.0,
            )
        return {"phase": "phase_4_online_update", "ok": True}

    def smoke_graph_stats(self) -> Dict[str, Any]:
        nodes = self.client.run_query("MATCH (n) RETURN count(n) AS c")
        rels = self.client.run_query("MATCH ()-[r]->() RETURN count(r) AS c")
        node_count = int(nodes[0].get("c", 0)) if nodes else 0
        rel_count = int(rels[0].get("c", 0)) if rels else 0
        return {"nodes": node_count, "relationships": rel_count}

    def component_catalog(self):
        return get_kg_component_catalog()
