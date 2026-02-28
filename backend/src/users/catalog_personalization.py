"""Catalog personalization: re-rank results based on user preferences with explainability."""
from typing import List, Dict, Any, Optional
from src.users.user_agent import UserAgent


class CatalogPersonalizer:
    """Re-ranks catalog results using user preferences.

    Applies deterministic boosting rules based on user preference history.
    """

    def __init__(self, user_agent: UserAgent):
        """Initialize with a user agent."""
        self.user_agent = user_agent

    def personalize_results(
        self,
        user_id: Optional[str],
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Re-rank and enrich results with explainability.

        Args:
            user_id: user identifier (if None, return results unchanged).
            results: list of product dicts from CatalogAgent.

        Returns:
            list of results with added "why" explanation and re-ranked by match score.
        """
        if not user_id or not results:
            return results

        prefs = self.user_agent.get_preferences(user_id)
        if not prefs:
            return results

        # compute match score for each result
        scored = []
        for product in results:
            score = 0.0
            explanations = []

            # 1. category match
            if prefs.get("top_categories"):
                prod_cat = (product.get("category") or "").lower()
                if prod_cat in [c.lower() for c in prefs["top_categories"]]:
                    score += 3.0
                    explanations.append("Matches your frequently searched category")

            # 2. color match
            if prefs.get("top_colors"):
                prod_col = (product.get("color") or "").lower()
                if prod_col in [c.lower() for c in prefs["top_colors"]]:
                    score += 2.0
                    explanations.append("Matches your preferred color")

            # 3. price range match
            if prefs.get("price_range"):
                try:
                    price = float(product.get("price", 0))
                    price_min = prefs["price_range"].get("min", 0)
                    price_max = prefs["price_range"].get("max", float("inf"))
                    if price_min <= price <= price_max:
                        score += 2.0
                        explanations.append("Within your preferred price range")
                except (ValueError, TypeError):
                    pass

            # 4. style tag match
            if prefs.get("style_tag_frequency"):
                prod_tags = product.get("normalized_style_tags") or product.get("style_tags", [])
                tag_set = set(t.lower() for t in prod_tags if isinstance(t, str))
                pref_tags = set(t.lower() for t in prefs["style_tag_frequency"].keys())
                if tag_set & pref_tags:
                    score += 1.5
                    explanations.append("Matches your style preferences")

            # 5. shop preference
            if prefs.get("preferred_shops"):
                prod_shop = str(product.get("shop_id", ""))
                if prod_shop in prefs["preferred_shops"]:
                    score += 1.0
                    explanations.append("From a shop you frequently visit")

            scored.append((product, score, explanations))

        # sort by score descending, then by original order for stability
        scored.sort(key=lambda x: x[1], reverse=True)

        # return re-ranked results with explanations
        return [
            {
                **product,
                "personalization_score": score,
                "why": explanations if explanations else ["Popular item"],
            }
            for product, score, explanations in scored
        ]
