"""Unit tests for user intelligence: profiles, preferences, and personalization."""
import pytest
from datetime import datetime
from src.users.schemas import UserProfile, InteractionEvent
from src.users.repository import UserRepository
from src.users.user_agent import UserAgent
from src.users.catalog_personalization import CatalogPersonalizer


class TestUserProfile:
    """Test UserProfile dataclass."""

    def test_user_profile_creation(self):
        """Test creating a user profile."""
        profile = UserProfile(user_id="user_123")
        assert profile.user_id == "user_123"
        assert profile.preferences == {}
        assert profile.interaction_counts == {}
        assert isinstance(profile.created_at, datetime)

    def test_user_profile_to_dict(self):
        """Test converting profile to dict."""
        profile = UserProfile(user_id="user_123", preferences={"pref": "value"})
        d = profile.to_dict()
        assert d["user_id"] == "user_123"
        assert d["preferences"] == {"pref": "value"}
        assert "created_at" in d


class TestInteractionEvent:
    """Test InteractionEvent dataclass."""

    def test_interaction_event_creation(self):
        """Test creating an interaction event."""
        event = InteractionEvent(
            user_id="user_123", event_type="search", payload={"query": "blue shirt"}
        )
        assert event.user_id == "user_123"
        assert event.event_type == "search"
        assert event.payload == {"query": "blue shirt"}

    def test_interaction_event_to_dict(self):
        """Test converting event to dict."""
        event = InteractionEvent(user_id="user_123", event_type="view", payload={"product_id": 42})
        d = event.to_dict()
        assert d["user_id"] == "user_123"
        assert d["event_type"] == "view"
        assert d["payload"] == {"product_id": 42}


class TestUserRepository:
    """Test user repository CRUD."""

    def test_create_user(self):
        """Test creating a new user."""
        repo = UserRepository()
        user = repo.create_user("user_1")
        assert user.user_id == "user_1"
        assert repo.get_user("user_1") == user

    def test_create_user_idempotent(self):
        """Test that creating same user twice returns same user."""
        repo = UserRepository()
        user1 = repo.create_user("user_1")
        user2 = repo.create_user("user_1")
        assert user1 is user2

    def test_get_nonexistent_user(self):
        """Test getting a user that doesn't exist."""
        repo = UserRepository()
        assert repo.get_user("nonexistent") is None

    def test_append_interaction(self):
        """Test appending an interaction."""
        repo = UserRepository()
        repo.create_user("user_1")
        event = InteractionEvent(user_id="user_1", event_type="search")
        repo.append_interaction(event)
        history = repo.get_interaction_history("user_1")
        assert len(history) == 1
        assert history[0].event_type == "search"

    def test_interaction_history_empty(self):
        """Test getting history for user with no interactions."""
        repo = UserRepository()
        history = repo.get_interaction_history("nonexistent")
        assert history == []

    def test_clear_user(self):
        """Test clearing a user."""
        repo = UserRepository()
        repo.create_user("user_1")
        repo.append_interaction(InteractionEvent(user_id="user_1", event_type="search"))
        repo.clear_user("user_1")
        assert repo.get_user("user_1") is None
        assert repo.get_interaction_history("user_1") == []


class TestUserAgent:
    """Test user agent preference extraction."""

    def test_get_or_create_user(self):
        """Test get-or-create semantics."""
        agent = UserAgent()
        user1 = agent.get_or_create_user("user_1")
        user2 = agent.get_or_create_user("user_1")
        assert user1.user_id == user2.user_id

    def test_record_interaction(self):
        """Test recording an interaction."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"query": "blue shirt"})
        user = agent.get_or_create_user("user_1")
        assert user.interaction_counts.get("search") == 1

    def test_multiple_interactions(self):
        """Test recording multiple interactions."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"query": "shirt"})
        agent.record_interaction("user_1", "view", {"product_id": 1})
        agent.record_interaction("user_1", "search", {"query": "pants"})
        user = agent.get_or_create_user("user_1")
        assert user.interaction_counts.get("search") == 2
        assert user.interaction_counts.get("view") == 1

    def test_preference_extraction_categories(self):
        """Test preference extraction: top categories."""
        agent = UserAgent()
        # record multiple search events with categories
        agent.record_interaction("user_1", "search", {"category": "shirt"})
        agent.record_interaction("user_1", "search", {"category": "shirt"})
        agent.record_interaction("user_1", "search", {"category": "pants"})
        agent.update_preferences("user_1")
        prefs = agent.get_preferences("user_1")
        assert "top_categories" in prefs
        assert "shirt" in prefs["top_categories"]

    def test_preference_extraction_colors(self):
        """Test preference extraction: top colors."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"color": "blue"})
        agent.record_interaction("user_1", "search", {"color": "blue"})
        agent.record_interaction("user_1", "search", {"color": "red"})
        agent.update_preferences("user_1")
        prefs = agent.get_preferences("user_1")
        assert "top_colors" in prefs
        assert "blue" in prefs["top_colors"]

    def test_preference_extraction_price_range(self):
        """Test preference extraction: price range."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"price": 1000})
        agent.record_interaction("user_1", "view", {"price": 5000})
        agent.record_interaction("user_1", "search", {"price": 3000})
        agent.update_preferences("user_1")
        prefs = agent.get_preferences("user_1")
        assert "price_range" in prefs
        assert prefs["price_range"]["min"] == 1000
        assert prefs["price_range"]["max"] == 5000
        assert 3000 <= prefs["price_range"]["median"] <= 5000

    def test_preference_extraction_shops(self):
        """Test preference extraction: preferred shops."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"shop_id": "shop_1"})
        agent.record_interaction("user_1", "view", {"shop_id": "shop_1"})
        agent.record_interaction("user_1", "search", {"shop_id": "shop_2"})
        agent.update_preferences("user_1")
        prefs = agent.get_preferences("user_1")
        assert "preferred_shops" in prefs
        assert "shop_1" in prefs["preferred_shops"]

    def test_preference_extraction_style_tags(self):
        """Test preference extraction: style tag frequency."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"style_tags": ["casual", "summer"]})
        agent.record_interaction("user_1", "view", {"style_tags": ["casual"]})
        agent.update_preferences("user_1")
        prefs = agent.get_preferences("user_1")
        assert "style_tag_frequency" in prefs
        assert "casual" in prefs["style_tag_frequency"]

    def test_empty_preferences(self):
        """Test preferences for user with no interactions."""
        agent = UserAgent()
        prefs = agent.get_preferences("user_1")
        assert prefs == {}

    def test_get_interaction_history(self):
        """Test retrieving interaction history."""
        agent = UserAgent()
        agent.record_interaction("user_1", "search", {"query": "shirt"})
        agent.record_interaction("user_1", "view", {"product_id": 1})
        history = agent.get_interaction_history("user_1")
        assert len(history) == 2
        assert history[0].event_type == "search"
        assert history[1].event_type == "view"


class TestCatalogPersonalizer:
    """Test catalog result personalization."""

    def test_personalize_without_user(self):
        """Test that personalization is skipped when user_id is None."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        results = [{"product_id": 1, "category": "shirt", "price": 1000}]
        personalized = personalizer.personalize_results(None, results)
        # Should return results unchanged (no "why" or personalization_score)
        assert len(personalized) == 1
        assert personalized[0]["product_id"] == 1

    def test_personalize_category_match(self):
        """Test category matching in personalization."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        # build user preferences: shirt is preferred
        agent.record_interaction("user_1", "search", {"category": "shirt"})
        agent.record_interaction("user_1", "search", {"category": "shirt"})
        agent.update_preferences("user_1")
        # personalize results
        results = [
            {"product_id": 1, "category": "shirt", "price": 1000},
            {"product_id": 2, "category": "pants", "price": 1000},
        ]
        personalized = personalizer.personalize_results("user_1", results)
        # shirt should rank higher
        assert personalized[0]["product_id"] == 1
        assert "why" in personalized[0]

    def test_personalize_color_match(self):
        """Test color matching in personalization."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        agent.record_interaction("user_1", "search", {"color": "blue"})
        agent.record_interaction("user_1", "search", {"color": "blue"})
        agent.update_preferences("user_1")
        results = [
            {"product_id": 1, "color": "blue", "price": 1000},
            {"product_id": 2, "color": "red", "price": 1000},
        ]
        personalized = personalizer.personalize_results("user_1", results)
        assert personalized[0]["product_id"] == 1

    def test_personalize_price_range(self):
        """Test price range matching in personalization."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        agent.record_interaction("user_1", "search", {"price": 2000})
        agent.record_interaction("user_1", "search", {"price": 3000})
        agent.update_preferences("user_1")
        results = [
            {"product_id": 1, "price": 2500},  # within range
            {"product_id": 2, "price": 10000},  # outside range
        ]
        personalized = personalizer.personalize_results("user_1", results)
        assert personalized[0]["product_id"] == 1

    def test_personalize_with_explanation(self):
        """Test that personalization includes explanations."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        agent.record_interaction("user_1", "search", {"category": "shirt", "color": "blue"})
        agent.record_interaction("user_1", "search", {"category": "shirt", "color": "blue"})
        agent.update_preferences("user_1")
        results = [{"product_id": 1, "category": "shirt", "color": "blue", "price": 1000}]
        personalized = personalizer.personalize_results("user_1", results)
        assert "why" in personalized[0]
        assert isinstance(personalized[0]["why"], list)
        assert len(personalized[0]["why"]) > 0

    def test_personalize_empty_results(self):
        """Test personalization with empty results."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        agent.record_interaction("user_1", "search", {"category": "shirt"})
        personalized = personalizer.personalize_results("user_1", [])
        assert personalized == []

    def test_personalize_multiple_factors(self):
        """Test multi-factor personalization scoring."""
        agent = UserAgent()
        personalizer = CatalogPersonalizer(agent)
        # user prefers: shirts, blue color, 2000-4000 price range
        agent.record_interaction("user_1", "search", {"category": "shirt", "color": "blue", "price": 3000})
        agent.record_interaction("user_1", "search", {"category": "shirt", "color": "blue", "price": 2500})
        agent.update_preferences("user_1")
        # results: one matches all, one matches some, one matches none
        results = [
            {"product_id": 1, "category": "shirt", "color": "blue", "price": 3000},  # all match
            {"product_id": 2, "category": "shirt", "color": "red", "price": 3000},  # category + price
            {"product_id": 3, "category": "pants", "color": "red", "price": 10000},  # none
        ]
        personalized = personalizer.personalize_results("user_1", results)
        # product 1 should rank first
        assert personalized[0]["product_id"] == 1
        assert personalized[0]["personalization_score"] > personalized[1]["personalization_score"]
        assert personalized[1]["personalization_score"] > personalized[2]["personalization_score"]
