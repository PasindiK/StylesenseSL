from datetime import datetime
from typing import Any, Dict, List, Optional

from .client import Neo4jKGClient


class KGEventWriter:
    def __init__(self, client: Neo4jKGClient):
        self.client = client

    def record_search(self, user_id: str, query: str, intent: Optional[Dict[str, Any]] = None) -> None:
        if not user_id:
            return
        self.client.execute_write(
            """
            MERGE (u:User {user_id: toString($user_id)})
            MERGE (q:SearchQuery {text: $query})
            MERGE (u)-[r:SEARCHED]->(q)
            SET r.count = coalesce(r.count, 0) + 1,
                r.last_ts = $ts,
                r.intent_category = $intent_category,
                r.intent_color = $intent_color
            """,
            {
                "user_id": user_id,
                "query": query,
                "ts": datetime.utcnow().isoformat(),
                "intent_category": (intent or {}).get("category"),
                "intent_color": (intent or {}).get("color"),
            },
        )

    def record_recommendation_impression(
        self,
        user_id: str,
        products: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not user_id or not products:
            return
        ts = datetime.utcnow().isoformat()
        for rank, product in enumerate(products, start=1):
            product_id = str(product.get("product_id") or "")
            if not product_id:
                continue
            self.client.execute_write(
                """
                MERGE (u:User {user_id: toString($user_id)})
                MATCH (p:Product {product_id: toString($product_id)})
                MERGE (u)-[r:RECOMMENDED]->(p)
                SET r.last_ts = $ts,
                    r.rank = $rank,
                    r.score = $score,
                    r.query = $query,
                    r.count = coalesce(r.count, 0) + 1
                """,
                {
                    "user_id": user_id,
                    "product_id": product_id,
                    "ts": ts,
                    "rank": rank,
                    "score": float(product.get("personalization_score") or 0),
                    "query": (context or {}).get("query"),
                },
            )

    def record_user_preference(self, user_id: str, preference_type: str, value: str, weight: float = 1.0) -> None:
        if not user_id or not value:
            return
        mapping = {
            "category": ("Category", "PREFERS_CATEGORY"),
            "color": ("Color", "PREFERS_COLOR"),
            "style": ("StyleTag", "PREFERS_STYLE"),
        }
        node_label, rel_type = mapping.get(preference_type, (None, None))
        if not node_label:
            return

        query = f"""
        MERGE (u:User {{user_id: toString($user_id)}})
        MERGE (n:{node_label} {{name: $value}})
        MERGE (u)-[r:{rel_type}]->(n)
        SET r.weight = coalesce(r.weight, 0) + $weight,
            r.last_ts = $ts
        """
        self.client.execute_write(
            query,
            {
                "user_id": user_id,
                "value": value,
                "weight": float(weight),
                "ts": datetime.utcnow().isoformat(),
            },
        )
