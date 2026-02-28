"""In-memory user repository for CRUD operations and interaction storage."""
from typing import Dict, List, Optional
from src.users.schemas import UserProfile, InteractionEvent


class UserRepository:
    """In-memory repository for user profiles and interactions.

    Later swappable with DB storage via dependency injection.
    """

    def __init__(self):
        """Initialize empty user store and interaction log."""
        self._users: Dict[str, UserProfile] = {}
        self._interactions: Dict[str, List[InteractionEvent]] = {}

    def create_user(self, user_id: str) -> UserProfile:
        """Create a new user profile."""
        if user_id in self._users:
            return self._users[user_id]
        profile = UserProfile(user_id=user_id)
        self._users[user_id] = profile
        self._interactions[user_id] = []
        return profile

    def get_user(self, user_id: str) -> Optional[UserProfile]:
        """Retrieve a user profile by ID."""
        return self._users.get(user_id)

    def update_user(self, user_profile: UserProfile) -> None:
        """Update an existing user profile."""
        self._users[user_profile.user_id] = user_profile

    def append_interaction(self, event: InteractionEvent) -> None:
        """Append an interaction event to user history."""
        if event.user_id not in self._interactions:
            self._interactions[event.user_id] = []
        self._interactions[event.user_id].append(event)

    def get_interaction_history(self, user_id: str) -> List[InteractionEvent]:
        """Retrieve all interaction events for a user."""
        return self._interactions.get(user_id, [])

    def clear_user(self, user_id: str) -> None:
        """Delete a user and their interactions (for testing)."""
        self._users.pop(user_id, None)
        self._interactions.pop(user_id, None)

    def clear_all(self) -> None:
        """Clear all data (for testing)."""
        self._users.clear()
        self._interactions.clear()
