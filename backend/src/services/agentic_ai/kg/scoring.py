from typing import Any, Dict, List, Optional

from .client import Neo4jKGClient


class KGScoringService:
    def __init__(self, client: Neo4jKGClient):
        self.client = client

    def score_candidates(
        self,
        user_id: Optional[str],
        candidates: List[Dict[str, Any]],
        intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        if not user_id or not candidates or not self.client.enabled:
            return {}

        by_product: Dict[str, Dict[str, Any]] = {}
        category = (intent or {}).get("category")
        color = (intent or {}).get("color")

        for candidate in candidates:
            product_id = str(candidate.get("product_id") or "")
            if not product_id:
                continue

            rows = self.client.run_query(
                """
                MATCH (u:User {user_id: toString($user_id)})
                MATCH (p:Product {product_id: toString($product_id)})
                OPTIONAL MATCH (u)-[vc:VIEWED|WISHLISTED|ADDED_TO_CART|PURCHASED]->(p)
                OPTIONAL MATCH (u)-[pc:PREFERS_CATEGORY]->(:Category)<-[:IN_CATEGORY]-(p)
                OPTIONAL MATCH (u)-[pr:PREFERS_COLOR]->(:Color)<-[:HAS_COLOR]-(p)
                OPTIONAL MATCH (u)-[ps:PREFERS_STYLE]->(:StyleTag)<-[:HAS_TAG]-(p)
                WITH
                    coalesce(sum(vc.count), 0) AS behavior_hits,
                    coalesce(sum(pc.weight), 0) AS category_pref,
                    coalesce(sum(pr.weight), 0) AS color_pref,
                    coalesce(sum(ps.weight), 0) AS style_pref
                RETURN behavior_hits, category_pref, color_pref, style_pref
                """,
                {"user_id": user_id, "product_id": product_id},
            )
            if not rows:
                continue
            record = rows[0]
            behavior_hits = float(record.get("behavior_hits", 0) or 0)
            category_pref = float(record.get("category_pref", 0) or 0)
            color_pref = float(record.get("color_pref", 0) or 0)
            style_pref = float(record.get("style_pref", 0) or 0)

            raw = 0.35 * min(behavior_hits / 3.0, 1.0) + 0.30 * min(category_pref / 3.0, 1.0) + 0.20 * min(color_pref / 3.0, 1.0) + 0.15 * min(style_pref / 3.0, 1.0)
            reasons = []
            if behavior_hits > 0:
                reasons.append("Related to your previous interactions")
            if category_pref > 0 or (category and str(category).lower() in str(candidate.get("category", "")).lower()):
                reasons.append("Aligned with your category preferences")
            if color_pref > 0 or (color and str(color).lower() in str(candidate.get("color", "")).lower()):
                reasons.append("Matches your color preferences")
            if style_pref > 0:
                reasons.append("Connected to your style graph")

            by_product[product_id] = {
                "graph_score": round(min(max(raw, 0.0), 1.0), 4),
                "graph_reasons": reasons[:2],
            }

        return by_product
