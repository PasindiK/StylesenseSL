import logging
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors

    SKLEARN_AVAILABLE = True
except Exception:
    TfidfVectorizer = None
    NearestNeighbors = None
    SKLEARN_AVAILABLE = False

from .client import Neo4jKGClient
from .schema import KG_SCHEMA_QUERIES

logger = logging.getLogger(__name__)


class KGBootstrapLoader:
    def __init__(self, client: Neo4jKGClient, data_root: Path):
        self.client = client
        self.data_root = data_root
        self.max_products = int(os.getenv("KG_BOOTSTRAP_MAX_PRODUCTS", "600"))
        self.max_interactions = int(os.getenv("KG_BOOTSTRAP_MAX_INTERACTIONS", "3000"))
        self.max_transactions = int(os.getenv("KG_BOOTSTRAP_MAX_TRANSACTIONS", "5000"))
        self.max_trends = int(os.getenv("KG_BOOTSTRAP_MAX_TRENDS", "500"))
        self.sim_top_k = int(os.getenv("KG_SIM_TOP_K", "10"))
        self.sim_threshold = float(os.getenv("KG_SIM_THRESHOLD", "0.45"))
        self.alternative_per_product = int(os.getenv("KG_ALTERNATIVE_TOP_K", "3"))

    @staticmethod
    def _safe_str(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and pd.isna(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return default
            return int(float(value))
        except Exception:
            return default

    @staticmethod
    def _parse_date(value: object) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return pd.to_datetime(text, errors="coerce").to_pydatetime()
        except Exception:
            return None

    @staticmethod
    def _season_from_date(value: object) -> Optional[str]:
        dt = KGBootstrapLoader._parse_date(value)
        if not dt:
            return None
        month = dt.month
        if month in {12, 1, 2}:
            return "Winter"
        if month in {3, 4, 5}:
            return "Spring"
        if month in {6, 7, 8}:
            return "Summer"
        return "Autumn"

    @staticmethod
    def _normalize_text(value: object) -> str:
        return " ".join(str(value or "").lower().replace("_", " ").split())

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
        if filename == "transactions_dataset.csv" and self.max_transactions > 0:
            df = df.head(self.max_transactions)
        if filename == "trends_dataset.csv" and self.max_trends > 0:
            df = df.head(self.max_trends)
        return df.to_dict(orient="records")

    def _load_df(self, filename: str, limit: int = 0) -> pd.DataFrame:
        path = self.data_root / filename
        if not path.exists():
            logger.warning("[KG] Missing bootstrap file: %s", path)
            return pd.DataFrame()
        df = pd.read_csv(path)
        if limit > 0:
            return df.head(limit).copy()
        return df.copy()

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

            shop_name = self._safe_str(shop.get("shop_name"))
            if shop_name:
                self.client.execute_write(
                    """
                    MERGE (sn:ShopName {name: $shop_name})
                    WITH sn
                    MATCH (s:Shop {shop_id: toString($shop_id)})
                    MERGE (s)-[:ALIASED_AS]->(sn)
                    """,
                    {
                        "shop_name": shop_name,
                        "shop_id": shop.get("shop_id"),
                    },
                )

        for row in self._iter_rows("final_products.csv"):
            product_id = row.get("product_id")
            shop_id = row.get("shop_id")
            category = self._safe_str(row.get("category"))
            color = self._safe_str(row.get("color"))
            fabric = self._safe_str(row.get("fabric"))
            style_tags = self._split_csv_values(self._safe_str(row.get("style_tags")))
            season = self._season_from_date(row.get("created_ts") or row.get("created_timestamp"))

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
                MERGE (p)-[:SOLD_BY]->(s)
                """,
                {
                    "product_id": product_id,
                    "name": row.get("name"),
                    "category": category,
                    "color": color,
                    "fabric": fabric,
                    "price_LKR": self._safe_float(row.get("price_LKR")),
                    "popularity_score": self._safe_float(row.get("popularity_score")),
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
                    MERGE (p)-[:BELONGS_TO]->(c)
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

            if fabric:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (f:Fabric {name: $fabric})
                    MERGE (p)-[:HAS_FABRIC]->(f)
                    """,
                    {"product_id": product_id, "fabric": fabric},
                )

            if season:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (s:Season {name: $season})
                    MERGE (p)-[:FITS_SEASON]->(s)
                    """,
                    {"product_id": product_id, "season": season},
                )

            for tag in style_tags[:6]:
                self.client.execute_write(
                    """
                    MATCH (p:Product {product_id: toString($product_id)})
                    MERGE (t:StyleTag {name: $tag})
                    MERGE (p)-[:HAS_TAG]->(t)
                    MERGE (p)-[:HAS_STYLE]->(t)
                    """,
                    {"product_id": product_id, "tag": tag},
                )

    def load_preferences(self) -> None:
        for row in self._iter_rows("user_preferences_dataset.csv"):
            user_id = row.get("user_id")
            categories = self._split_csv_values(row.get("preferred_categories"))
            colors = self._split_csv_values(row.get("preferred_colors"))
            styles = self._split_csv_values(row.get("preferred_styles"))
            fabrics = self._split_csv_values(row.get("preferred_fabrics"))
            brands = self._split_csv_values(row.get("preferred_brands"))
            shops = self._split_csv_values(row.get("preferred_shops"))

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

            for fabric in fabrics:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (f:Fabric {name: $fabric})
                    MERGE (u)-[r:PREFERS_FABRIC]->(f)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "fabric": fabric},
                )

            for brand in brands:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (b:Brand {name: $brand})
                    MERGE (u)-[r:PREFERS_BRAND]->(b)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "brand": brand},
                )

            for shop in shops:
                self.client.execute_write(
                    """
                    MATCH (u:User {user_id: toString($user_id)})
                    MERGE (sn:ShopName {name: $shop_name})
                    MERGE (u)-[r:PREFERS_SHOP]->(sn)
                    SET r.weight = coalesce(r.weight, 0) + 1
                    """,
                    {"user_id": user_id, "shop_name": shop},
                )

    def load_interactions(self) -> None:
        rel_map = {
            "view": "VIEWED",
            "wishlist": "LIKED",
            "add_to_cart": "ADDED_TO_CART",
            "purchase": "PURCHASED",
            "click": "CLICKED",
            "like": "LIKED",
        }
        for row in self._iter_rows("interactions_dataset.csv"):
            interaction_type = self._normalize_text(row.get("interaction_type"))
            rel = rel_map.get(interaction_type)
            if not rel:
                continue

            interaction_id = row.get("interaction_id")
            user_id = row.get("user_id")
            product_id = row.get("product_id")
            interaction_ts = row.get("interaction_ts")

            self.client.execute_write(
                """
                MERGE (i:Interaction {interaction_id: toString($interaction_id)})
                SET i.type = $interaction_type,
                    i.ts = $interaction_ts,
                    i.date = $interaction_date
                WITH i
                MATCH (u:User {user_id: toString($user_id)})
                MATCH (p:Product {product_id: toString($product_id)})
                MERGE (u)-[:PERFORMED_INTERACTION]->(i)
                MERGE (i)-[:ON_PRODUCT]->(p)
                """,
                {
                    "interaction_id": interaction_id,
                    "interaction_type": interaction_type,
                    "interaction_ts": interaction_ts,
                    "interaction_date": row.get("interaction_date"),
                    "user_id": user_id,
                    "product_id": product_id,
                },
            )

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
                    "user_id": user_id,
                    "product_id": product_id,
                    "interaction_ts": interaction_ts,
                },
            )

        # Approximate search intent from repeated category interactions.
        self.client.execute_write(
            """
            MATCH (u:User)-[:VIEWED|CLICKED|LIKED|ADDED_TO_CART|PURCHASED]->(p:Product)-[:BELONGS_TO]->(c:Category)
            WITH u, c, count(*) AS cnt
            WHERE cnt >= 2
            MERGE (u)-[r:SEARCHED]->(c)
            SET r.count = cnt
            """
        )

    def load_transactions(self) -> None:
        tx_df = self._load_df("transactions_dataset.csv", self.max_transactions)
        if tx_df.empty:
            return

        bought_with_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        for _, row in tx_df.iterrows():
            tx_id = row.get("transaction_id")
            user_id = row.get("user_id")
            product_id = row.get("product_id")
            shop_id = row.get("shop_id")
            final_amount = self._safe_float(row.get("final_amount") or row.get("total_amount"))
            quantity = self._safe_int(row.get("quantity"), default=1)

            self.client.execute_write(
                """
                MERGE (t:Transaction {transaction_id: toString($transaction_id)})
                SET t.transaction_date = $transaction_date,
                    t.transaction_ts = $transaction_ts,
                    t.payment_method = $payment_method,
                    t.status = $status,
                    t.final_amount = $final_amount,
                    t.quantity = $quantity
                WITH t
                MATCH (u:User {user_id: toString($user_id)})
                MATCH (p:Product {product_id: toString($product_id)})
                MATCH (s:Shop {shop_id: toString($shop_id)})
                MERGE (u)-[:MADE_TRANSACTION]->(t)
                MERGE (t)-[:INCLUDES_PRODUCT]->(p)
                MERGE (t)-[:AT_SHOP]->(s)
                MERGE (u)-[r:PURCHASED]->(p)
                SET r.count = coalesce(r.count, 0) + 1,
                    r.last_ts = coalesce($transaction_ts, r.last_ts)
                MERGE (s)-[sp:SOLD]->(p)
                SET sp.count = coalesce(sp.count, 0) + 1
                """,
                {
                    "transaction_id": tx_id,
                    "transaction_date": row.get("transaction_date"),
                    "transaction_ts": row.get("transaction_ts"),
                    "payment_method": row.get("payment_method"),
                    "status": row.get("transaction_status"),
                    "final_amount": final_amount,
                    "quantity": quantity,
                    "user_id": user_id,
                    "product_id": product_id,
                    "shop_id": shop_id,
                },
            )

        # Approximate basket co-purchase using same user and date.
        tx_df["user_id"] = tx_df["user_id"].astype(str)
        tx_df["transaction_date"] = tx_df["transaction_date"].astype(str)
        grouped = tx_df.groupby(["user_id", "transaction_date"], dropna=False)
        for _, group in grouped:
            products = [str(pid) for pid in group["product_id"].dropna().astype(str).tolist()]
            unique_products = sorted(set(products))
            if len(unique_products) < 2:
                continue
            for a, b in combinations(unique_products, 2):
                bought_with_counts[(a, b)] += 1

        for (a, b), cnt in bought_with_counts.items():
            self.client.execute_write(
                """
                MATCH (p1:Product {product_id: toString($a)})
                MATCH (p2:Product {product_id: toString($b)})
                MERGE (p1)-[r:BOUGHT_WITH]->(p2)
                SET r.count = coalesce(r.count, 0) + $count
                """,
                {"a": a, "b": b, "count": int(cnt)},
            )

    def load_trends(self) -> None:
        for row in self._iter_rows("trends_dataset.csv"):
            trend_id = self._safe_str(row.get("trend_id"))
            if not trend_id:
                continue
            trend_name = self._safe_str(row.get("trend_name"))
            trend_category = self._safe_str(row.get("trend_category"))
            tags = self._split_csv_values(self._safe_str(row.get("trend_tags")))

            self.client.execute_write(
                """
                MERGE (t:Trend {trend_id: $trend_id})
                SET t.name = $name,
                    t.category = $category,
                    t.score = $score,
                    t.week = $week,
                    t.year = $year,
                    t.emerging_designers = $emerging_designers
                """,
                {
                    "trend_id": trend_id,
                    "name": trend_name,
                    "category": trend_category,
                    "score": self._safe_float(row.get("trend_score")),
                    "week": self._safe_int(row.get("week")),
                    "year": self._safe_int(row.get("year")),
                    "emerging_designers": row.get("emerging_designers"),
                },
            )

            if trend_category:
                self.client.execute_write(
                    """
                    MATCH (t:Trend {trend_id: $trend_id})
                    MERGE (c:Category {name: $category})
                    MERGE (t)-[:INFLUENCES]->(c)
                    """,
                    {"trend_id": trend_id, "category": trend_category},
                )

            for tag in tags[:8]:
                self.client.execute_write(
                    """
                    MATCH (t:Trend {trend_id: $trend_id})
                    MERGE (s:StyleTag {name: $tag})
                    MERGE (t)-[:RELATES_TO]->(s)
                    """,
                    {"trend_id": trend_id, "tag": tag},
                )

            # Trend includes products using category + style overlap + popularity.
            self.client.execute_write(
                """
                MATCH (t:Trend {trend_id: $trend_id})
                MATCH (p:Product)-[:BELONGS_TO]->(c:Category)
                WHERE toLower(c.name) = toLower($category)
                OPTIONAL MATCH (p)-[:HAS_STYLE]->(st:StyleTag)
                WITH t, p, collect(toLower(st.name)) AS p_tags
                WITH t, p,
                     reduce(m = 0, tag IN $tags | m + CASE WHEN tag IN p_tags THEN 1 ELSE 0 END) AS overlap
                ORDER BY overlap DESC, coalesce(p.popularity_score, 0) DESC
                LIMIT $limit
                MERGE (t)-[:INCLUDES]->(p)
                MERGE (p)-[:TRENDING_IN]->(t)
                """,
                {
                    "trend_id": trend_id,
                    "category": trend_category,
                    "tags": [self._normalize_text(t) for t in tags if self._normalize_text(t)],
                    "limit": 12,
                },
            )

    def build_similarity_network(self) -> None:
        if not SKLEARN_AVAILABLE:
            logger.warning("[KG] sklearn unavailable. Skipping similarity graph build")
            return

        products_df = self._load_df("final_products.csv", self.max_products)
        if products_df.empty:
            return

        products_df = products_df.fillna("")
        products_df["text"] = (
            products_df["name"].astype(str)
            + " "
            + products_df["category"].astype(str)
            + " "
            + products_df["color"].astype(str)
            + " "
            + products_df["fabric"].astype(str)
            + " "
            + products_df["style_tags"].astype(str)
        ).str.lower()

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=0.95)
        X = vectorizer.fit_transform(products_df["text"].tolist())
        n_neighbors = min(max(2, self.sim_top_k + 1), X.shape[0])
        nn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine", algorithm="brute")
        nn.fit(X)
        distances, indices = nn.kneighbors(X)

        product_ids = products_df["product_id"].astype(str).tolist()
        categories = products_df["category"].astype(str).tolist()
        colors = products_df["color"].astype(str).tolist()
        prices = [self._safe_float(v) for v in products_df["price_LKR"].tolist()]

        seen_pairs = set()
        for i, nbrs in enumerate(indices):
            pid_i = product_ids[i]
            for pos, j in enumerate(nbrs[1:], start=1):
                pid_j = product_ids[int(j)]
                similarity = 1.0 - float(distances[i][pos])
                if similarity < self.sim_threshold:
                    continue
                key = tuple(sorted((pid_i, pid_j)))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                self.client.execute_write(
                    """
                    MATCH (p1:Product {product_id: toString($p1)})
                    MATCH (p2:Product {product_id: toString($p2)})
                    MERGE (p1)-[r:SIMILAR_TO]->(p2)
                    SET r.score = $score
                    """,
                    {"p1": pid_i, "p2": pid_j, "score": round(similarity, 4)},
                )

        # Alternatives: same category, different color, nearest by price.
        by_category: Dict[str, List[int]] = defaultdict(list)
        for idx, cat in enumerate(categories):
            by_category[self._normalize_text(cat)].append(idx)

        for idx, cat in enumerate(categories):
            members = by_category.get(self._normalize_text(cat), [])
            if len(members) < 2:
                continue
            candidates = []
            for j in members:
                if j == idx:
                    continue
                if self._normalize_text(colors[j]) == self._normalize_text(colors[idx]):
                    continue
                price_gap = abs(prices[idx] - prices[j])
                candidates.append((price_gap, j))
            candidates.sort(key=lambda x: x[0])
            for _, j in candidates[: self.alternative_per_product]:
                self.client.execute_write(
                    """
                    MATCH (p1:Product {product_id: toString($p1)})
                    MATCH (p2:Product {product_id: toString($p2)})
                    MERGE (p1)-[r:ALTERNATIVE_TO]->(p2)
                    SET r.score = coalesce(r.score, 1)
                    """,
                    {"p1": product_ids[idx], "p2": product_ids[j]},
                )

    def build_co_interaction_network(self) -> None:
        # Viewed together by same user.
        self.client.execute_write(
            """
            MATCH (u:User)-[:VIEWED]->(p:Product)
            WITH u, collect(DISTINCT p)[0..40] AS products
            UNWIND range(0, size(products)-2) AS i
            UNWIND range(i+1, size(products)-1) AS j
            WITH products[i] AS p1, products[j] AS p2
            MERGE (p1)-[r:VIEWED_WITH]->(p2)
            SET r.count = coalesce(r.count, 0) + 1
            """
        )

        # Clicked together (if CLICKED exists).
        self.client.execute_write(
            """
            MATCH (u:User)-[:CLICKED]->(p:Product)
            WITH u, collect(DISTINCT p)[0..40] AS products
            UNWIND range(0, size(products)-2) AS i
            UNWIND range(i+1, size(products)-1) AS j
            WITH products[i] AS p1, products[j] AS p2
            MERGE (p1)-[r:CLICKED_WITH]->(p2)
            SET r.count = coalesce(r.count, 0) + 1
            """
        )

        # Complementary products from co-purchase signals.
        self.client.execute_write(
            """
            MATCH (p1:Product)-[bw:BOUGHT_WITH]->(p2:Product)
            WHERE coalesce(p1.category, '') <> coalesce(p2.category, '')
            MERGE (p1)-[r:COMPLEMENTARY_TO]->(p2)
            SET r.score = coalesce(r.score, 0) + coalesce(bw.count, 1)
            """
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
        self.load_transactions()
        self.load_trends()
        self.build_similarity_network()
        self.build_co_interaction_network()
        logger.info("[KG] Bootstrap completed")
