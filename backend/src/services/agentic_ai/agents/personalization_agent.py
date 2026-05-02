"""PersonalizationAgent: governed semantic reranking for agentic recommendations."""
from typing import Any, Dict, List, Optional

from src.users.user_agent import UserAgent
from src.services.agentic_ai.agents.multi_stage_ranker import MultiStageRanker
from src.services.agentic_ai.kg.client import Neo4jKGClient
from src.services.agentic_ai.kg.events import KGEventWriter
from src.services.agentic_ai.kg.scoring import KGScoringService


class PersonalizationAgent:
    def __init__(self, user_agent: UserAgent):
        self.user_agent = user_agent
        self.kg_client = Neo4jKGClient()
        self.kg_events = KGEventWriter(self.kg_client)
        self.kg_scorer = KGScoringService(self.kg_client)
        self.ranker = MultiStageRanker(self.kg_scorer)

    @staticmethod
    def _to_lower_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    @staticmethod
    def _normalized_lower_list(values: Any) -> List[str]:
        if not values or not isinstance(values, list):
            return []
        return [str(v).strip().lower() for v in values if v is not None and str(v).strip()]

    @staticmethod
    def _normalized_str_set(values: Any) -> set:
        if not values or not isinstance(values, list):
            return set()
        return {str(v).strip().lower() for v in values if v is not None and str(v).strip()}

    def rerank(
        self,
        user_id: Optional[str],
        candidates: List[Dict[str, Any]],
        intent: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not candidates:
            return {"results": [], "scores": [], "why": "No candidates", "intent": intent or {}, "context": context or {}}
        prefs = self.user_agent.get_preferences(user_id) if user_id else {}
        ranked = self.ranker.rank_candidates(
            user_id=user_id,
            candidates=candidates,
            user_preferences=prefs,
            intent=intent or {},
            context=context or {},
        )

        if user_id:
            self.kg_events.record_recommendation_impression(
                user_id=user_id,
                products=ranked.get("results", []),
                context=context,
            )

        ranked["intent"] = intent or {}
        ranked["context"] = context or {}
        ranked["why"] = "Governed semantic ranking applied"
        ranked["scores"] = [item.get("personalization_score", 0.0) for item in ranked.get("results", [])]
        return ranked

    def generate_chat_message(
        self,
        user_id: Optional[str],
        intent: Optional[Dict[str, Any]],
        best_matches: List[Dict[str, Any]],
        new_suggestions: List[Dict[str, Any]],
        user_name: Optional[str] = None,
    ) -> str:
        """Generate a user-friendly response while keeping telemetry out of chat text."""
        greeting = f"Hey {user_name}!" if user_name else "Hey!"

        all_products = (best_matches or []) + (new_suggestions or [])
        if not all_products:
            if intent and intent.get("category"):
                return (
                    f"{greeting}\n"
                    f"I couldn't find exact matches for {intent.get('category', 'that')} right now. "
                    "Could you share your preferred color, size, or budget?"
                )
            return (
                f"{greeting}\n"
                "I couldn't find exact matches yet. Could you share your preferred style, color, size, or budget?"
            )

        style = self._to_lower_str((intent or {}).get("style"))
        occasion = self._to_lower_str((intent or {}).get("occasion"))
        category = self._to_lower_str((intent or {}).get("category"))
        color = self._to_lower_str((intent or {}).get("color"))

        intro_bits = []
        if color:
            intro_bits.append(color)
        if category:
            intro_bits.append(category)
        subject = " ".join(intro_bits) if intro_bits else "pieces"

        context_bits = []
        if occasion:
            article = "an" if occasion[:1] in {"a", "e", "i", "o", "u"} else "a"
            context_bits.append(f"for {article} {occasion} setting")
        if style:
            context_bits.append(f"with a {style} vibe")
        context_text = " ".join(context_bits).strip()

        lines = [
            greeting,
            (
                f"I found some stylish {subject} that fit well {context_text}."
                if context_text else f"I found some stylish {subject} you may like."
            ),
            "Your top picks are shown in the product cards.",
            "These were selected because they align with your requested style and your recent preference patterns.",
        ]
        return "\n".join(lines).strip()
