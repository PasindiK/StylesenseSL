"""User intelligence agent with preference extraction and deterministic logic."""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import Counter

from src.users.schemas import UserProfile, InteractionEvent
from src.users.repository import UserRepository


class UserAgent:
    """Tracks user interactions and derives explainable preferences.

    Preference extraction is deterministic and decays older interactions.
    """

    def __init__(self, repository: UserRepository = None):
        """Initialize UserAgent with optional custom repository."""
        self.repo = repository or UserRepository()

    def get_or_create_user(self, user_id: str) -> UserProfile:
        """Get existing user or create new one."""
        user = self.repo.get_user(user_id)
        if not user:
            user = self.repo.create_user(user_id)
        return user

    def record_interaction(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Record a user interaction event.

        Args:
            user_id: unique identifier
            event_type: 'search', 'view', 'like', 'add_to_cart'
            payload: event-specific data (query, category, product_id, etc.)
        """
        self.get_or_create_user(user_id)
        event = InteractionEvent(user_id=user_id, event_type=event_type, payload=payload)
        self.repo.append_interaction(event)
        # update interaction counts
        user = self.repo.get_user(user_id)
        user.interaction_counts[event_type] = user.interaction_counts.get(event_type, 0) + 1
        user.updated_at = datetime.utcnow()
        self.repo.update_user(user)

    def update_preferences(self, user_id: str) -> None:
        """Extract and update user preferences from interaction history.

        Preferences include:
        - top_categories
        - top_colors
        - style_tag_frequency
        - price_range (min, median, max)
        - preferred_shops
        """
        user = self.get_or_create_user(user_id)
        history = self.repo.get_interaction_history(user_id)

        if not history:
            user.preferences = {}
            self.repo.update_user(user)
            return

        # decay factor: recent events weighted higher (within last 30 days)
        now = datetime.utcnow()
        cutoff = now - timedelta(days=30)

        categories = []
        colors = []
        style_tags = []
        prices = []
        shops = []

        for event in history:
            # weight: older events get lower weight
            age_days = (now - event.timestamp).days
            weight = max(0.1, 1.0 - (age_days / 30.0)) if age_days < 30 else 0.0

            payload = event.payload or {}

            # extract from search and view events
            if event.event_type in ("search", "view"):
                if "category" in payload:
                    categories.extend([payload["category"]] * max(1, int(weight * 2)))
                if "color" in payload:
                    colors.extend([payload["color"]] * max(1, int(weight * 2)))
                if "style_tags" in payload:
                    tags = payload["style_tags"]
                    if isinstance(tags, list):
                        style_tags.extend(tags * max(1, int(weight * 2)))
                    else:
                        style_tags.extend([tags] * max(1, int(weight * 2)))
                if "price" in payload:
                    try:
                        prices.append(float(payload["price"]))
                    except (ValueError, TypeError):
                        pass
                if "shop_id" in payload:
                    shops.extend([payload["shop_id"]] * max(1, int(weight * 2)))

        # aggregate into preferences
        prefs = {}

        if categories:
            top_cats = Counter(categories).most_common(3)
            prefs["top_categories"] = [c[0] for c in top_cats]

        if colors:
            top_cols = Counter(colors).most_common(3)
            prefs["top_colors"] = [c[0] for c in top_cols]

        if style_tags:
            tag_freq = Counter(style_tags)
            prefs["style_tag_frequency"] = dict(tag_freq.most_common(5))

        if prices:
            prices.sort()
            prefs["price_range"] = {
                "min": int(min(prices)),
                "median": int(prices[len(prices) // 2]),
                "max": int(max(prices)),
            }

        if shops:
            top_shops = Counter(shops).most_common(3)
            prefs["preferred_shops"] = [s[0] for s in top_shops]

        user.preferences = prefs
        user.updated_at = datetime.utcnow()
        self.repo.update_user(user)

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences (ensure preferences are up-to-date)."""
        user = self.get_or_create_user(user_id)
        # optionally update before returning
        self.update_preferences(user_id)
        return self.repo.get_user(user_id).preferences

    def get_interaction_history(self, user_id: str) -> List[InteractionEvent]:
        """Retrieve user's full interaction history."""
        return self.repo.get_interaction_history(user_id)
