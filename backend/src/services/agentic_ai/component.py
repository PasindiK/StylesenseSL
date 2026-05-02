from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.ingestion import data_loader as data_loader_module
from src.ingestion.data_loader import DataLoader
from src.services.agentic_ai.agents.catalog_agent import CatalogAgent
from src.services.agentic_ai.agents.multi_stage_ranker import MultiStageRanker
from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.kg.scoring import KGScoringService
from src.users.user_agent import UserAgent
from src.utils.nl_parser import parse_intent


class AgenticSemanticFeatureOpsComponent:
    """Standalone Agentic AI component with governed retrieval + ranking."""

    def __init__(
        self,
        loader: Optional[DataLoader] = None,
        user_agent: Optional[UserAgent] = None,
    ) -> None:
        self.backend_root = Path(__file__).resolve().parents[3]
        raw_root = self.backend_root / "data" / "raw"
        data_loader_module.BASE_DIR = self.backend_root / "data"
        data_loader_module.RAW_DIR = raw_root
        self.loader = loader or DataLoader()
        try:
            self.loader.load_products()
        except Exception:
            self.loader.load_products(str(raw_root / "final_products.csv"))
        try:
            self.loader.load_shops()
        except Exception:
            try:
                self.loader.load_shops(str(raw_root / "shops_dataset.csv"))
            except Exception:
                pass
        self.catalog = CatalogAgent(loader=self.loader)
        self.user_agent = user_agent or UserAgent()
        self.kg_scorer = KGScoringService(Neo4jKGClient())
        self.ranker = MultiStageRanker(self.kg_scorer)

    def recommend(
        self,
        query: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        retrieval = self.catalog.answer_question(query, user_id=user_id)
        intent = retrieval.get("intent") or parse_intent(query)
        prefs = self.user_agent.get_preferences(user_id) if user_id else {}
        ranked = self.ranker.rank_candidates(
            user_id=user_id,
            candidates=retrieval.get("results", []),
            user_preferences=prefs,
            intent=intent,
            context=context or {"query": query},
        )
        return {
            "query": query,
            "intent": intent,
            "retrieval": {
                "search_method": retrieval.get("search_method"),
                "fallbacks": retrieval.get("fallbacks", []),
                "candidate_count": len(retrieval.get("results", [])),
            },
            "ranking": ranked,
        }
