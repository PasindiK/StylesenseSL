import logging
import os
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from .client import Neo4jKGClient
from .schema import KG_SCHEMA_QUERIES

logger = logging.getLogger(__name__)


class KGBootstrapLoader:
    def __init__(self, client: Neo4jKGClient, data_root: Path):
        self.client = client
        self.data_root = data_root
        self.max_products = int(os.getenv("KG_BOOTSTRAP_MAX_PRODUCTS", "600"))
        self.max_interactions = int(os.getenv("KG_BOOTSTRAP_MAX_INTERACTIONS", "3000"))

    def _split_csv_values(self, value: str) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, str):
            value = str(value)
        parts = [v.strip() for v in value.split(",") if v and v.strip()]
        return parts

    def _iter_rows(self, filename: str) -> Iterable[dict]:
        path = self.data_root / filename
        if not path.exists():
            logger.warning("[KG] Missing bootstrap file: %s", path)
            return []
        df = pd.read_csv(path)
        if filename == "final_products.csv" and self.max_products > 0:
            df = df.head(self.max_products)
        if filename == "interactions_dataset.csv" and self.max_interactions > 0:
            df = df.head(self.max_interactions)
        return df.to_dict(orient="records")

    def create_schema(self) -> None:
        for stmt in KG_SCHEMA_QUERIES:
            self.client.execute_write(stmt)

    def load_users(self) -> None:
        for row in self._iter_rows("users_dataset.csv"):
            self.client.execute_write(
                """
                MERGE (u:User {user_id: toString($user_id)})
                SET u.name = $name,
                    u.email = $email,
                    u.signup_ts = $signup_ts,
                    u.is_active = $is_active
                """,
                {
                    "user_id": row.get("user_id"),
                    "name": row.get("name"),
                    "email": row.get("email"),
                    "signup_ts": row.get("signup_ts"),
                    "is_active": bool(row.get("is_active")),
                },
            )

    def load_products_and_shops(self) -> None:
        for shop in self._iter_rows("shops_dataset.csv"):
            self.client.execute_write(
                """
                MERGE (s:Shop {shop_id: toString($shop_id)})
                SET s.shop_name = $shop_name,
                    s.location = $location,
                    s.district = $district,
                    s.is_active = $is_active
                """,
                {
                    "shop_id": shop.get("shop_id"),
                    "shop_name": shop.get("shop_name"),
                    "location": shop.get("location"),
                    "district": shop.get("district"),
                    "is_active": bool(shop.get("is_active")),
                },
            )

        for row in self._iter_rows("final_products.csv"):
            product_id = row.get("product_id")
            shop_id = row.get("shop_id")
            category = str(row.get("category") or "").strip()
            color = str(row.get("color") or "").strip()
            style_tags = self._split_csv_values(str(row.get("style_tags") or ""))

            self.client.execute_write(
                """
                MERGE (p:Product {product_id: toString($product_id)})
                SET p.name = $name,
                    p.category = $category,
                    p.color = $color,
                    p.fabric = $fabric,
                    p.price_LKR = $price_LKR,
                    p.popularity_score = $popularity_score,
                    p.product_url = $product_url
                WITH p
                MATCH (s:Shop {shop_id: toString($shop_id)})
                MERGE (p)-[:FROM_SHOP]->(s)
                """,
                {
                    "product_id": product_id,
                    "name": row.get("name"),
                    "category": category,
                    "color": color,
                    "fabric": row.get("fabric"),
                    "price_LKR": float(row.get("price_LKR") or 0),
                    "popularity_score": float(row.get("popularity_score") or 0),
                    "product_url": row.get("product_url"),
                    "shop_id": shop_id,
                },
            )

            if category:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (c:Category {name: $category})
                    MERGE (p)-[:IN_CATEGORY]->(c)
                    """,
                    {"product_id": product_id, "category": category},
                )

            if color:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (c:Color {name: $color})
                    MERGE (p)-[:HAS_COLOR]->(c)
                    """,
                    {"product_id": product_id, "color": color},
                )

            for tag in style_tags[:6]:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (t:StyleTag {name: $tag})
                    MERGE (p)-[:HAS_TAG]->(t)
                    """,
                    {"product_id": product_id, "tag": tag},
                )

    def load_preferences(self) -> None:
        for row in self._iter_rows("user_preferences_dataset.csv"):
            user_id = row.get("user_id")
            categories = self._split_csv_values(row.get("preferred_categories"))
            colors = self._split_csv_values(row.get("preferred_colors"))
            styles = self._split_csv_values(row.get("preferred_styles"))

            for category in categories:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (c:Category {name: $category})
                    MERGE (u)-[r:PREFERS_CATEGORY]->(c)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "category": category},
                )

            for color in colors:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (c:Color {name: $color})
                    MERGE (u)-[r:PREFERS_COLOR]->(c)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "color": color},
                )

            for style in styles:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (s:StyleTag {name: $style})
                    MERGE (u)-[r:PREFERS_STYLE]->(s)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "style": style},
                )

    def load_interactions(self) -> None:
        rel_map = {
            "view": "VIEWED",
            "wishlist": "WISHLISTED",
            "add_to_cart": "ADDED_TO_CART",
            "purchase": "PURCHASED",
        }
        for row in self._iter_rows("interactions_dataset.csv"):
            rel = rel_map.get(str(row.get("interaction_type", "")).lower())
            if not rel:
                continue
            query = f"""
            MATCH (u:User {{user_id: toString($user_id)}})
            MATCH (p:Product {{product_id: toString($product_id)}})
            MERGE (u)-[r:{rel}]->(p)
            SET r.ts = coalesce($interaction_ts, r.ts),
                r.count = coalesce(r.count, 0) + 1
            """
            self.client.execute_write(
                query,
                {
                    "user_id": row.get("user_id"),
                    "product_id": row.get("product_id"),
                    "interaction_ts": row.get("interaction_ts"),
                },
            )

    def run_full_bootstrap(self) -> None:
        if not self.client.enabled:
            logger.info("[KG] Bootstrap skipped (client disabled)")
            return
        logger.info("[KG] Bootstrap started")
        self.create_schema()
        self.load_users()
        self.load_products_and_shops()
        self.load_preferences()
        self.load_interactions()
        logger.info("[KG] Bootstrap completed")
