"""User intelligence schemas for tracking preferences and interactions."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List


@dataclass
class UserProfile:
    """Represents a user profile with preferences and interaction history."""

    user_id: str
    preferences: Dict[str, Any] = field(default_factory=dict)
    interaction_counts: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "user_id": self.user_id,
            "preferences": self.preferences,
            "interaction_counts": self.interaction_counts,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class InteractionEvent:
    """Represents a single user interaction event."""

    user_id: str
    event_type: str  # search, view, like, add_to_cart, etc.
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "user_id": self.user_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }
