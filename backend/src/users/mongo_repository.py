# MongoDB repository for user profiles and interaction events
from pymongo import MongoClient
from src.users.schemas import UserProfile, InteractionEvent
from typing import Optional, Dict, Any, List
from datetime import datetime

class MongoUserRepository:
    def __init__(self, uri: str, db_name: str = "stylesensesl"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.user_profiles = self.db["user_profiles"]
        self.interaction_events = self.db["interaction_events"]

    def create_user(self, user_id: str) -> UserProfile:
        profile = UserProfile(user_id=user_id)
        self.user_profiles.insert_one(profile.to_dict())
        return profile

    def get_user(self, user_id: str) -> Optional[UserProfile]:
        doc = self.user_profiles.find_one({"user_id": user_id})
        if doc:
            return UserProfile(
                user_id=doc["user_id"],
                preferences=doc.get("preferences", {}),
                interaction_counts=doc.get("interaction_counts", {}),
                created_at=datetime.fromisoformat(doc["created_at"]),
                updated_at=datetime.fromisoformat(doc["updated_at"]),
            )
        return None

    def update_user(self, user_profile: UserProfile) -> None:
        self.user_profiles.update_one(
            {"user_id": user_profile.user_id},
            {"$set": user_profile.to_dict()},
        )

    def append_interaction(self, event: InteractionEvent) -> None:
        self.interaction_events.insert_one(event.to_dict())

    def get_interaction_history(self, user_id: str) -> List[InteractionEvent]:
        docs = self.interaction_events.find({"user_id": user_id})
        return [
            InteractionEvent(
                user_id=doc["user_id"],
                event_type=doc["event_type"],
                payload=doc.get("payload", {}),
                timestamp=datetime.fromisoformat(doc["timestamp"]),
            )
            for doc in docs
        ]

    def seed_synthetic_users(self, users: List[Dict[str, Any]]) -> None:
        self.user_profiles.insert_many(users)

    def seed_synthetic_interactions(self, events: List[Dict[str, Any]]) -> None:
        self.interaction_events.insert_many(events)

    def seed_dashboard_data(self, dashboard_data: List[Dict[str, Any]]) -> None:
        """
        Insert synthetic dashboard data into the 'dashboard_data' collection.
        """
        dashboard_collection = self.db["dashboard_data"]
        dashboard_collection.insert_many(dashboard_data)
