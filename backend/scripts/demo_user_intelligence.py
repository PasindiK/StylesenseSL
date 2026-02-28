"""Example: User Intelligence Foundation in action.

This demonstrates how the system tracks user interactions and personalizes results.
Run with: python scripts/demo_user_intelligence.py
"""
from src.users.user_agent import UserAgent
from src.users.catalog_personalization import CatalogPersonalizer
from src.agents.catalog_agent import CatalogAgent
from src.ingestion.data_loader import DataLoader


def demo():
    """Demonstrate user intelligence and personalization."""
    print("=" * 80)
    print("USER INTELLIGENCE FOUNDATION - DEMO")
    print("=" * 80)

    # Initialize
    loader = DataLoader()
    loader.load_products("data/raw/products.csv")
    loader.load_shops("data/raw/shops_dataset.csv")

    agent = CatalogAgent(loader=loader)
    user_agent = UserAgent()
    personalizer = CatalogPersonalizer(user_agent)

    user_id = "demo_user_123"

    # Step 1: Record some interactions
    print("\n[Step 1] Recording user interactions...")
    interactions = [
        ("search", {"query": "blue shirt", "category": "shirt", "color": "blue", "price": 2500}),
        ("view", {"product_id": 5, "category": "shirt", "color": "blue"}),
        ("search", {"query": "casual wear", "category": "shirt", "color": "blue", "price": 3000, "style_tags": ["casual"]}),
        ("search", {"query": "summer collection", "style_tags": ["summer"], "price": 2000}),
        ("view", {"product_id": 12, "shop_id": "shop_5"}),
    ]

    for event_type, payload in interactions:
        user_agent.record_interaction(user_id, event_type, payload)
        print(f"  - Recorded {event_type}: {payload}")

    # Step 2: Extract preferences
    print("\n[Step 2] Extracting user preferences...")
    user_agent.update_preferences(user_id)
    prefs = user_agent.get_preferences(user_id)
    print(f"  Preferences extracted: {prefs}")

    # Step 3: Perform a search
    print("\n[Step 3] Performing a catalog search (without personalization)...")
    results = agent.search_by_text("shirt", limit=5)
    print(f"  Found {len(results)} results (unpersonalized)")

    # Step 4: Personalize results
    print("\n[Step 4] Personalizing results for the user...")
    personalized = personalizer.personalize_results(user_id, results)
    print(f"  Personalized {len(personalized)} results")
    print("\n  Top personalized result:")
    if personalized:
        top = personalized[0]
        print(f"    - Product ID: {top.get('product_id')}")
        print(f"    - Name: {top.get('name', 'N/A')}")
        print(f"    - Category: {top.get('category')}")
        print(f"    - Color: {top.get('color')}")
        print(f"    - Price: {top.get('price')}")
        print(f"    - Personalization Score: {top.get('personalization_score', 0):.2f}")
        print(f"    - Why Recommended: {top.get('why', [])}")

    # Step 5: Show interaction history
    print("\n[Step 5] User interaction history:")
    history = user_agent.get_interaction_history(user_id)
    print(f"  Total interactions: {len(history)}")
    for i, event in enumerate(history, 1):
        print(f"    {i}. {event.event_type}: {event.payload}")

    # Step 6: Multiple user test
    print("\n[Step 6] Testing multiple users with different preferences...")
    user_2 = "demo_user_456"
    # User 2 prefers pants and red color
    user_agent.record_interaction(user_2, "search", {"category": "pants", "color": "red", "price": 4000})
    user_agent.record_interaction(user_2, "search", {"category": "pants", "color": "red", "price": 3500})
    user_agent.update_preferences(user_2)
    prefs_2 = user_agent.get_preferences(user_2)
    print(f"  User 2 preferences: {prefs_2}")

    # Same search, different personalization
    personalized_user_2 = personalizer.personalize_results(user_2, results)
    print(f"  User 1 top result: Product {personalized[0].get('product_id')}")
    print(f"  User 2 top result: Product {personalized_user_2[0].get('product_id')}")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    demo()
